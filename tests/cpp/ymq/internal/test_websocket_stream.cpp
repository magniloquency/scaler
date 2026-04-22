#include <gtest/gtest.h>

#include <chrono>
#include <cstdint>
#include <vector>

#include "scaler/wrapper/uv/error.h"
#include "scaler/wrapper/uv/loop.h"
#include "scaler/ymq/address.h"
#include "scaler/ymq/internal/accept_server.h"
#include "scaler/ymq/internal/connect_client.h"

class WebSocketStreamTest: public ::testing::Test {};

// Verify that a WebSocket address round-trips through toString() / fromString().
TEST_F(WebSocketStreamTest, AddressRoundTrip)
{
    const auto addr = scaler::ymq::Address::fromString("ws://127.0.0.1:8765/");
    ASSERT_TRUE(addr.has_value());
    ASSERT_EQ(addr->type(), scaler::ymq::Address::Type::WebSocket);

    const auto& ws = addr->asWebSocket();
    EXPECT_EQ(ws.host, "127.0.0.1");
    EXPECT_EQ(ws.port, 8765);
    EXPECT_EQ(ws.path, "/");
    EXPECT_FALSE(ws.secure);

    const auto str = addr->toString();
    ASSERT_TRUE(str.has_value());
    EXPECT_EQ(*str, "ws://127.0.0.1:8765/");
}

TEST_F(WebSocketStreamTest, AddressWithPath)
{
    const auto addr = scaler::ymq::Address::fromString("ws://127.0.0.1:9000/ymq/v1");
    ASSERT_TRUE(addr.has_value());
    ASSERT_EQ(addr->asWebSocket().path, "/ymq/v1");
    ASSERT_FALSE(addr->asWebSocket().secure);
}

TEST_F(WebSocketStreamTest, WSSAddress)
{
    const auto addr = scaler::ymq::Address::fromString("wss://127.0.0.1:443/");
    ASSERT_TRUE(addr.has_value());
    ASSERT_EQ(addr->type(), scaler::ymq::Address::Type::WebSocket);
    ASSERT_TRUE(addr->asWebSocket().secure);

    const auto str = addr->toString();
    ASSERT_TRUE(str.has_value());
    ASSERT_TRUE(str->starts_with("wss://"));
}

TEST_F(WebSocketStreamTest, InvalidAddresses)
{
    EXPECT_FALSE(scaler::ymq::Address::fromString("ws://127.0.0.1").has_value());  // missing port
    EXPECT_FALSE(scaler::ymq::Address::fromString("ws://127.0.0.1:abc/").has_value());  // bad port
}

// End-to-end: a WebSocket AcceptServer receives a connection.
// Verifies that the full upgrade path runs without error and that the server's
// connection callback is invoked with an isWebSocket() client.
TEST_F(WebSocketStreamTest, ClientServerHandshake)
{
    scaler::wrapper::uv::Loop loop = UV_EXIT_ON_ERROR(scaler::wrapper::uv::Loop::init());

    const auto listenAddress = scaler::ymq::Address::fromString("ws://127.0.0.1:0/").value();

    std::vector<uint8_t> serverReceived {};
    // Keep the server-side client alive across the callback boundary.
    std::optional<scaler::ymq::internal::Client> serverClient {};

    // ── Server ──────────────────────────────────────────────────────────────
    scaler::ymq::internal::AcceptServer server(
        loop,
        listenAddress,
        [&](scaler::ymq::internal::Client client) {
            ASSERT_TRUE(client.isWebSocket());
            serverClient.emplace(std::move(client));
            UV_EXIT_ON_ERROR(serverClient->readStart(
                [&serverReceived](
                    std::expected<std::span<const uint8_t>, scaler::wrapper::uv::Error> result) {
                    if (!result.has_value())
                        return;
                    serverReceived.insert(serverReceived.end(), result->begin(), result->end());
                }));
        });

    const scaler::ymq::Address boundAddress = server.address();
    ASSERT_EQ(boundAddress.type(), scaler::ymq::Address::Type::WebSocket);

    // ── Client ──────────────────────────────────────────────────────────────
    bool clientConnected = false;
    // Keep the client-side client alive so the socket stays open for writing.
    std::optional<scaler::ymq::internal::Client> clientClient {};
    const std::vector<uint8_t> msg {'H', 'e', 'l', 'l', 'o'};

    scaler::ymq::internal::ConnectClient connector(
        loop,
        boundAddress,
        [&](std::expected<scaler::ymq::internal::Client, scaler::ymq::Error> result) {
            ASSERT_TRUE(result.has_value());
            ASSERT_TRUE(result->isWebSocket());
            clientConnected = true;

            clientClient.emplace(std::move(*result));
            const std::span<const uint8_t> msgSpan(msg.data(), msg.size());
            UV_EXIT_ON_ERROR(clientClient->write(std::span<const std::span<const uint8_t>>(&msgSpan, 1), [](auto) {}));
        });

    // Run the event loop until the server receives the message (or timeout after 2 s).
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (serverReceived.empty() && std::chrono::steady_clock::now() < deadline) {
        loop.run(UV_RUN_ONCE);
    }

    EXPECT_TRUE(clientConnected);
    EXPECT_EQ(serverReceived, (std::vector<uint8_t> {'H', 'e', 'l', 'l', 'o'}));

    // Clean up before the loop is destroyed: readStop breaks the shared_ptr cycle inside
    // WebSocketStream::readStart, then closeReset closes the TCP connection.
    if (serverClient) {
        serverClient->readStop();
        UV_EXIT_ON_ERROR(serverClient->closeReset());
        serverClient.reset();
    }
    if (clientClient) {
        clientClient->readStop();
        UV_EXIT_ON_ERROR(clientClient->closeReset());
        clientClient.reset();
    }
    server.disconnect();
    connector.disconnect();
    loop.run(UV_RUN_DEFAULT);
}
