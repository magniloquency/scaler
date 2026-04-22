#include "scaler/ymq/internal/websocket_stream.h"

#include <bit>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <memory>
#include <optional>
#include <random>
#include <span>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace scaler {
namespace ymq {
namespace internal {

// ─── Crypto / encoding utilities ────────────────────────────────────────────

namespace {

// RFC 3174 SHA-1 — used solely for the Sec-WebSocket-Accept header computation.
std::array<uint8_t, 20> sha1(std::string_view input) noexcept
{
    uint32_t h[5] = {0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0};

    std::vector<uint8_t> msg(input.begin(), input.end());
    const uint64_t bitLen = msg.size() * 8;
    msg.push_back(0x80);
    while (msg.size() % 64 != 56)
        msg.push_back(0x00);
    for (int i = 7; i >= 0; --i)
        msg.push_back(static_cast<uint8_t>(bitLen >> (i * 8)));

    for (size_t offset = 0; offset < msg.size(); offset += 64) {
        uint32_t w[80];
        for (int i = 0; i < 16; ++i) {
            w[i] = (uint32_t(msg[offset + i * 4]) << 24) | (uint32_t(msg[offset + i * 4 + 1]) << 16) |
                   (uint32_t(msg[offset + i * 4 + 2]) << 8) | uint32_t(msg[offset + i * 4 + 3]);
        }
        for (int i = 16; i < 80; ++i)
            w[i] = std::rotl(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);

        uint32_t a = h[0], b = h[1], c = h[2], d = h[3], e = h[4];
        for (int i = 0; i < 80; ++i) {
            uint32_t f, k;
            if (i < 20) {
                f = (b & c) | (~b & d);
                k = 0x5A827999;
            } else if (i < 40) {
                f = b ^ c ^ d;
                k = 0x6ED9EBA1;
            } else if (i < 60) {
                f = (b & c) | (b & d) | (c & d);
                k = 0x8F1BBCDC;
            } else {
                f = b ^ c ^ d;
                k = 0xCA62C1D6;
            }
            const uint32_t temp = std::rotl(a, 5) + f + e + k + w[i];
            e                   = d;
            d                   = c;
            c                   = std::rotl(b, 30);
            b                   = a;
            a                   = temp;
        }
        h[0] += a;
        h[1] += b;
        h[2] += c;
        h[3] += d;
        h[4] += e;
    }

    std::array<uint8_t, 20> digest;
    for (int i = 0; i < 5; ++i) {
        digest[i * 4]     = (h[i] >> 24) & 0xFF;
        digest[i * 4 + 1] = (h[i] >> 16) & 0xFF;
        digest[i * 4 + 2] = (h[i] >> 8) & 0xFF;
        digest[i * 4 + 3] = h[i] & 0xFF;
    }
    return digest;
}

std::string base64Encode(std::span<const uint8_t> data) noexcept
{
    static constexpr std::string_view kAlphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string result;
    result.reserve(((data.size() + 2) / 3) * 4);
    int val = 0, valb = -6;
    for (uint8_t c: data) {
        val = (val << 8) | c;
        valb += 8;
        while (valb >= 0) {
            result += kAlphabet[(val >> valb) & 0x3F];
            valb -= 6;
        }
    }
    if (valb > -6)
        result += kAlphabet[((val << 8) >> (valb + 8)) & 0x3F];
    while (result.size() % 4)
        result += '=';
    return result;
}

std::string generateWebSocketKey() noexcept
{
    static thread_local std::mt19937 rng(std::random_device {}());
    std::uniform_int_distribution<uint32_t> dist;
    std::array<uint8_t, 16> keyBytes;
    for (size_t i = 0; i < keyBytes.size(); i += 4) {
        const uint32_t v = dist(rng);
        std::memcpy(&keyBytes[i], &v, 4);
    }
    return base64Encode(std::span<const uint8_t>(keyBytes));
}

std::string computeWebSocketAccept(const std::string& key) noexcept
{
    const std::string_view magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    const std::string input      = key + std::string(magic);
    const auto digest            = sha1(input);
    return base64Encode(std::span<const uint8_t>(digest));
}

std::string buildClientUpgradeRequest(
    const std::string& host, uint16_t port, const std::string& path, const std::string& key) noexcept
{
    return "GET " + path +
           " HTTP/1.1\r\n"
           "Host: " +
           host + ":" + std::to_string(port) +
           "\r\n"
           "Upgrade: websocket\r\n"
           "Connection: Upgrade\r\n"
           "Sec-WebSocket-Key: " +
           key +
           "\r\n"
           "Sec-WebSocket-Version: 13\r\n"
           "\r\n";
}

std::string buildServerUpgradeResponse(const std::string& key) noexcept
{
    return "HTTP/1.1 101 Switching Protocols\r\n"
           "Upgrade: websocket\r\n"
           "Connection: Upgrade\r\n"
           "Sec-WebSocket-Accept: " +
           computeWebSocketAccept(key) +
           "\r\n"
           "\r\n";
}

// Case-insensitive header value extraction.
std::optional<std::string> extractHeader(std::string_view headers, std::string_view name) noexcept
{
    std::string lowerHeaders(headers);
    std::string lowerName(name);
    for (char& c: lowerHeaders)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    for (char& c: lowerName)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    lowerName += ": ";

    const size_t pos = lowerHeaders.find(lowerName);
    if (pos == std::string::npos)
        return std::nullopt;

    const size_t valueStart = pos + lowerName.size();
    const size_t lineEnd    = headers.find("\r\n", valueStart);
    return std::string(headers.substr(valueStart, lineEnd - valueStart));
}

// ─── WebSocket frame encoding ────────────────────────────────────────────────

// Returns the frame header bytes for a server-side frame (unmasked).
std::vector<uint8_t> buildServerFrameHeader(size_t payloadSize) noexcept
{
    std::vector<uint8_t> header;
    header.push_back(0x82);  // FIN | opcode=binary
    if (payloadSize < 126) {
        header.push_back(static_cast<uint8_t>(payloadSize));
    } else if (payloadSize < 65536) {
        header.push_back(126);
        header.push_back(static_cast<uint8_t>((payloadSize >> 8) & 0xFF));
        header.push_back(static_cast<uint8_t>(payloadSize & 0xFF));
    } else {
        header.push_back(127);
        for (int i = 7; i >= 0; --i)
            header.push_back(static_cast<uint8_t>((payloadSize >> (i * 8)) & 0xFF));
    }
    return header;
}

// Returns {header+mask, masked-payload-copy} for a client-side frame (masked, RFC 6455 §5.3).
std::pair<std::vector<uint8_t>, std::vector<uint8_t>> buildClientFrame(
    std::span<const std::span<const uint8_t>> buffers, size_t totalSize) noexcept
{
    static thread_local std::mt19937 rng(std::random_device {}());
    std::uniform_int_distribution<uint32_t> dist;
    std::array<uint8_t, 4> maskKey;
    const uint32_t maskInt = dist(rng);
    std::memcpy(maskKey.data(), &maskInt, 4);

    std::vector<uint8_t> header;
    header.push_back(0x82);  // FIN | binary
    if (totalSize < 126) {
        header.push_back(0x80 | static_cast<uint8_t>(totalSize));
    } else if (totalSize < 65536) {
        header.push_back(0x80 | 126);
        header.push_back(static_cast<uint8_t>((totalSize >> 8) & 0xFF));
        header.push_back(static_cast<uint8_t>(totalSize & 0xFF));
    } else {
        header.push_back(0x80 | 127);
        for (int i = 7; i >= 0; --i)
            header.push_back(static_cast<uint8_t>((totalSize >> (i * 8)) & 0xFF));
    }
    header.insert(header.end(), maskKey.begin(), maskKey.end());

    std::vector<uint8_t> masked;
    masked.reserve(totalSize);
    size_t pos = 0;
    for (const auto& buf: buffers) {
        for (uint8_t byte: buf)
            masked.push_back(byte ^ maskKey[pos++ % 4]);
    }
    return {std::move(header), std::move(masked)};
}

// Tries to parse one complete WebSocket frame from buffer, consuming it in-place.
// Returns nullopt if the buffer does not yet contain a full frame.
// Returns an empty vector for control/unknown frames (frame consumed, no payload to deliver).
std::optional<std::vector<uint8_t>> tryDecodeFrame(std::vector<uint8_t>& buffer) noexcept
{
    if (buffer.size() < 2)
        return std::nullopt;

    const uint8_t byte0  = buffer[0];
    const uint8_t byte1  = buffer[1];
    const uint8_t opcode = byte0 & 0x0F;
    const bool masked    = (byte1 & 0x80) != 0;
    uint64_t payloadLen  = byte1 & 0x7F;
    size_t headerSize    = 2;

    if (payloadLen == 126) {
        if (buffer.size() < 4)
            return std::nullopt;
        payloadLen = (uint64_t(buffer[2]) << 8) | buffer[3];
        headerSize = 4;
    } else if (payloadLen == 127) {
        if (buffer.size() < 10)
            return std::nullopt;
        payloadLen = 0;
        for (int i = 0; i < 8; ++i)
            payloadLen = (payloadLen << 8) | buffer[2 + i];
        headerSize = 10;
    }

    if (masked)
        headerSize += 4;

    if (buffer.size() < headerSize + payloadLen)
        return std::nullopt;

    // Control frames (close=0x8, ping=0x9, pong=0xA) and reserved opcodes: consume silently.
    if (opcode != 0x0 && opcode != 0x1 && opcode != 0x2) {
        buffer.erase(buffer.begin(), buffer.begin() + headerSize + static_cast<size_t>(payloadLen));
        return std::vector<uint8_t> {};
    }

    std::vector<uint8_t> payload(static_cast<size_t>(payloadLen));
    if (masked) {
        const uint8_t* maskKey = buffer.data() + headerSize - 4;
        for (size_t i = 0; i < static_cast<size_t>(payloadLen); ++i)
            payload[i] = buffer[headerSize + i] ^ maskKey[i % 4];
    } else {
        std::copy(
            buffer.begin() + static_cast<std::ptrdiff_t>(headerSize),
            buffer.begin() + static_cast<std::ptrdiff_t>(headerSize + payloadLen),
            payload.begin());
    }

    buffer.erase(
        buffer.begin(), buffer.begin() + static_cast<std::ptrdiff_t>(headerSize + static_cast<size_t>(payloadLen)));
    return payload;
}

}  // anonymous namespace

// ─── Upgrade state ───────────────────────────────────────────────────────────

// Shared state used during the async HTTP upgrade phase on the client side.
// TCPSocket has no public default constructor, so we wrap it in optional.
struct ClientUpgradeContext {
    std::optional<scaler::wrapper::uv::TCPSocket> socket {};
    std::string key {};
    std::vector<uint8_t> recvBuffer {};
    scaler::utility::MoveOnlyFunction<void(std::expected<WebSocketStream, scaler::wrapper::uv::Error>)> callback {};
};

// Shared state used during the async HTTP upgrade phase on the server side.
struct ServerUpgradeContext {
    std::optional<scaler::wrapper::uv::TCPSocket> socket {};
    std::vector<uint8_t> recvBuffer {};
    scaler::utility::MoveOnlyFunction<void(std::expected<WebSocketStream, scaler::wrapper::uv::Error>)> callback {};
};

// ─── WebSocketStream implementation ─────────────────────────────────────────

WebSocketStream::State::State(scaler::wrapper::uv::TCPSocket socket, bool isServer) noexcept
    : _socket(std::move(socket)), _isServer(isServer)
{
}

WebSocketStream::WebSocketStream(std::shared_ptr<State> state) noexcept: _state(std::move(state))
{
}

WebSocketStream WebSocketStream::fromUpgradedSocket(
    scaler::wrapper::uv::TCPSocket socket, bool isServer, std::vector<uint8_t> leftover) noexcept
{
    auto state         = std::make_shared<State>(std::move(socket), isServer);
    state->_recvBuffer = std::move(leftover);
    return WebSocketStream(std::move(state));
}

// Called when a complete HTTP response has been assembled in the client upgrade context.
static void finishClientUpgrade(std::shared_ptr<ClientUpgradeContext> ctx) noexcept
{
    ctx->socket->readStop();

    const std::string_view response(reinterpret_cast<const char*>(ctx->recvBuffer.data()), ctx->recvBuffer.size());

    const size_t headersEnd = response.find("\r\n\r\n");
    assert(headersEnd != std::string_view::npos);

    const std::string_view headers = response.substr(0, headersEnd);

    if (!headers.starts_with("HTTP/1.1 101")) {
        ctx->callback(std::unexpected(scaler::wrapper::uv::Error {UV_EPROTO}));
        return;
    }

    const auto acceptHeader = extractHeader(headers, "Sec-WebSocket-Accept");
    if (!acceptHeader.has_value() || *acceptHeader != computeWebSocketAccept(ctx->key)) {
        ctx->callback(std::unexpected(scaler::wrapper::uv::Error {UV_EPROTO}));
        return;
    }

    // Preserve any data that arrived after the HTTP headers (should be empty in practice).
    std::vector<uint8_t> leftover(
        ctx->recvBuffer.begin() + static_cast<std::ptrdiff_t>(headersEnd + 4), ctx->recvBuffer.end());

    ctx->callback(
        WebSocketStream::fromUpgradedSocket(std::move(ctx->socket.value()), false /* client */, std::move(leftover)));
}

// Called when a complete HTTP request has been assembled in the server upgrade context.
static void finishServerUpgrade(std::shared_ptr<ServerUpgradeContext> ctx) noexcept
{
    ctx->socket->readStop();

    const std::string_view request(reinterpret_cast<const char*>(ctx->recvBuffer.data()), ctx->recvBuffer.size());

    const size_t headersEnd = request.find("\r\n\r\n");
    assert(headersEnd != std::string_view::npos);

    const std::string_view headers = request.substr(0, headersEnd);

    const auto upgradeHeader = extractHeader(headers, "Upgrade");
    const auto keyHeader     = extractHeader(headers, "Sec-WebSocket-Key");

    if (!upgradeHeader.has_value() || !keyHeader.has_value()) {
        ctx->callback(std::unexpected(scaler::wrapper::uv::Error {UV_EPROTO}));
        return;
    }

    // Verify it's a WebSocket upgrade (case-insensitive)
    std::string upgradeValue = *upgradeHeader;
    for (char& c: upgradeValue)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    if (upgradeValue != "websocket") {
        ctx->callback(std::unexpected(scaler::wrapper::uv::Error {UV_EPROTO}));
        return;
    }

    const std::string response = buildServerUpgradeResponse(*keyHeader);
    auto responseData          = std::make_shared<std::string>(response);
    const std::span<const uint8_t> responseSpan(
        reinterpret_cast<const uint8_t*>(responseData->data()), responseData->size());

    auto writeResult = ctx->socket->write(
        std::span<const std::span<const uint8_t>>(&responseSpan, 1),
        [ctx, responseData = std::move(responseData)](std::expected<void, scaler::wrapper::uv::Error> result) mutable {
            if (!result.has_value()) {
                ctx->callback(std::unexpected(result.error()));
                return;
            }

            // Any data that arrived before the response write isn't expected but preserve it.
            ctx->callback(WebSocketStream::fromUpgradedSocket(std::move(ctx->socket.value()), true /* server */));
        });

    if (!writeResult.has_value()) {
        ctx->callback(std::unexpected(writeResult.error()));
    }
}

void WebSocketStream::upgradeAsClient(
    scaler::wrapper::uv::TCPSocket socket,
    const WebSocketAddress& address,
    scaler::utility::MoveOnlyFunction<void(std::expected<WebSocketStream, scaler::wrapper::uv::Error>)>
        callback) noexcept
{
    auto ctx      = std::make_shared<ClientUpgradeContext>();
    ctx->socket   = std::move(socket);
    ctx->key      = generateWebSocketKey();
    ctx->callback = std::move(callback);

    const std::string request = buildClientUpgradeRequest(address.host, address.port, address.path, ctx->key);
    auto requestData          = std::make_shared<std::string>(request);
    const std::span<const uint8_t> requestSpan(
        reinterpret_cast<const uint8_t*>(requestData->data()), requestData->size());

    auto writeResult = ctx->socket->write(
        std::span<const std::span<const uint8_t>>(&requestSpan, 1),
        [ctx, requestData = std::move(requestData)](std::expected<void, scaler::wrapper::uv::Error> result) mutable {
            if (!result.has_value()) {
                ctx->callback(std::unexpected(result.error()));
                return;
            }

            auto readStartResult = ctx->socket->readStart(
                [ctx](std::expected<std::span<const uint8_t>, scaler::wrapper::uv::Error> readResult) mutable {
                    if (!readResult.has_value()) {
                        ctx->socket->readStop();
                        ctx->callback(std::unexpected(readResult.error()));
                        return;
                    }

                    const auto& data = readResult.value();
                    ctx->recvBuffer.insert(ctx->recvBuffer.end(), data.begin(), data.end());

                    const std::string_view view(
                        reinterpret_cast<const char*>(ctx->recvBuffer.data()), ctx->recvBuffer.size());
                    if (view.find("\r\n\r\n") != std::string_view::npos) {
                        finishClientUpgrade(std::move(ctx));
                    }
                });

            if (!readStartResult.has_value()) {
                ctx->callback(std::unexpected(readStartResult.error()));
            }
        });

    if (!writeResult.has_value()) {
        auto cb = std::move(ctx->callback);
        cb(std::unexpected(writeResult.error()));
    }
}

void WebSocketStream::upgradeAsServer(
    scaler::wrapper::uv::TCPSocket socket,
    scaler::utility::MoveOnlyFunction<void(std::expected<WebSocketStream, scaler::wrapper::uv::Error>)>
        callback) noexcept
{
    auto ctx      = std::make_shared<ServerUpgradeContext>();
    ctx->socket   = std::move(socket);
    ctx->callback = std::move(callback);

    auto readStartResult = ctx->socket->readStart(
        [ctx](std::expected<std::span<const uint8_t>, scaler::wrapper::uv::Error> readResult) mutable {
            if (!readResult.has_value()) {
                ctx->socket->readStop();
                ctx->callback(std::unexpected(readResult.error()));
                return;
            }

            const auto& data = readResult.value();
            ctx->recvBuffer.insert(ctx->recvBuffer.end(), data.begin(), data.end());

            const std::string_view view(reinterpret_cast<const char*>(ctx->recvBuffer.data()), ctx->recvBuffer.size());
            if (view.find("\r\n\r\n") != std::string_view::npos) {
                finishServerUpgrade(std::move(ctx));
            }
        });

    if (!readStartResult.has_value()) {
        auto cb = std::move(ctx->callback);
        cb(std::unexpected(readStartResult.error()));
    }
}

// ─── Data path ───────────────────────────────────────────────────────────────

std::expected<void, scaler::wrapper::uv::Error> WebSocketStream::write(
    std::span<const std::span<const uint8_t>> buffers, scaler::wrapper::uv::WriteCallback callback) noexcept
{
    size_t totalSize = 0;
    for (const auto& buf: buffers)
        totalSize += buf.size();

    if (_state->_isServer) {
        auto header     = std::make_shared<std::vector<uint8_t>>(buildServerFrameHeader(totalSize));
        auto headerSpan = std::span<const uint8_t>(*header);

        std::vector<std::span<const uint8_t>> writeBuffers;
        writeBuffers.reserve(buffers.size() + 1);
        writeBuffers.push_back(headerSpan);
        for (const auto& buf: buffers)
            writeBuffers.push_back(buf);

        auto result = _state->_socket.write(
            std::span<const std::span<const uint8_t>>(writeBuffers),
            [header = std::move(header), callback = std::move(callback)](
                std::expected<void, scaler::wrapper::uv::Error> err) mutable { callback(err); });

        if (!result.has_value())
            return std::unexpected(result.error());
        return {};
    }

    auto [header, masked] = buildClientFrame(buffers, totalSize);
    auto headerData       = std::make_shared<std::vector<uint8_t>>(std::move(header));
    auto maskedData       = std::make_shared<std::vector<uint8_t>>(std::move(masked));

    const std::span<const uint8_t> headerSpan(*headerData);
    const std::span<const uint8_t> maskedSpan(*maskedData);
    const std::array<std::span<const uint8_t>, 2> writeBuffers {headerSpan, maskedSpan};

    auto result = _state->_socket.write(
        std::span<const std::span<const uint8_t>>(writeBuffers),
        [headerData = std::move(headerData), maskedData = std::move(maskedData), callback = std::move(callback)](
            std::expected<void, scaler::wrapper::uv::Error> err) mutable { callback(err); });

    if (!result.has_value())
        return std::unexpected(result.error());
    return {};
}

std::expected<void, scaler::wrapper::uv::Error> WebSocketStream::readStart(
    scaler::wrapper::uv::ReadCallback callback) noexcept
{
    auto state           = _state;
    state->_readCallback = std::move(callback);
    state->_readActive   = true;

    return state->_socket.readStart(
        [state](std::expected<std::span<const uint8_t>, scaler::wrapper::uv::Error> result) mutable {
            if (!result.has_value()) {
                if (state->_readActive && state->_readCallback) {
                    state->_readCallback(std::unexpected(result.error()));
                }
                return;
            }

            const auto& data = result.value();
            state->_recvBuffer.insert(state->_recvBuffer.end(), data.begin(), data.end());

            while (state->_readActive && !state->_recvBuffer.empty()) {
                auto frame = tryDecodeFrame(state->_recvBuffer);
                if (!frame.has_value())
                    break;  // need more data
                if (frame->empty())
                    continue;  // control frame, skip

                state->_readCallback(std::span<const uint8_t>(frame->data(), frame->size()));
            }
        });
}

void WebSocketStream::readStop() noexcept
{
    _state->_readActive = false;
    _state->_socket.readStop();
    _state->_readCallback = {};
}

std::expected<void, scaler::wrapper::uv::Error> WebSocketStream::shutdown(
    scaler::wrapper::uv::ShutdownCallback callback) noexcept
{
    auto result = _state->_socket.shutdown(std::move(callback));
    if (!result.has_value())
        return std::unexpected(result.error());
    return {};
}

std::expected<void, scaler::wrapper::uv::Error> WebSocketStream::closeReset() noexcept
{
    return _state->_socket.closeReset();
}

}  // namespace internal
}  // namespace ymq
}  // namespace scaler
