
#include "scaler/io/ymq/message_connection_tcp.h"

#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <memory>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/io_socket.h"

static bool isCompleteMessage(const std::vector<char>& vec) {
    if (vec.size() < 4)
        return false;
    uint64_t size = *(uint64_t*)vec.data();
    return vec.size() == size + vec.size() - 4;
}

MessageConnectionTCP::MessageConnectionTCP(
    std::shared_ptr<EventLoopThread> eventLoopThread,
    int connFd,
    sockaddr localAddr,
    sockaddr remoteAddr,
    std::string localIOSocketIdentity,
    bool responsibleForRetry,
    std::shared_ptr<std::queue<TcpReadOperation>> pendingReadOperations)
    : _eventLoopThread(eventLoopThread)
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _connFd(std::move(connFd))
    , _localAddr(localAddr)
    , _remoteAddr(remoteAddr)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _remoteIOSocketIdentity(std::nullopt)
    , _sendLocalIdentity(false)
    , _responsibleForRetry(responsibleForRetry)
    , _pendingReadOperations(pendingReadOperations) {
    _eventManager->onRead  = [this] { this->onRead(); };
    _eventManager->onWrite = [this] { this->onWrite(); };
    _eventManager->onClose = [this] { this->onClose(); };
    _eventManager->onError = [this] { this->onError(); };
}

void MessageConnectionTCP::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    this->_eventLoopThread->_eventLoop.addFdToLoop(_connFd, EPOLLIN | EPOLLOUT | EPOLLET, this->_eventManager.get());
}

void MessageConnectionTCP::onRead() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // TODO: do not assume the identity to be less than 128bytes
    if (!_remoteIOSocketIdentity) {
        // Other sizes are possible, but the size needs to be >= 8, in order for idBuf
        // to be aligned with 8 bytes boundary because of strict aliasing
        char idBuf[128] {};
        int n         = read(_connFd, &idBuf, 128);
        uint64_t size = *(uint64_t*)idBuf;
        char* first   = idBuf + sizeof(uint64_t);
        std::string remoteID(first, first + size);
        _remoteIOSocketIdentity.emplace(std::move(remoteID));

        auto& sock = this->_eventLoopThread->_identityToIOSocket[_localIOSocketIdentity];

        sock->onConnectionIdentityReceived(this);

        return;
    }

    assert(_remoteIOSocketIdentity);
    printf("Got a remote socket, identity = %s\n", _remoteIOSocketIdentity->c_str());

    while (true) {
        const size_t headerSize = 4;
        size_t leftOver         = 0;
        size_t first            = 0;

        // Good case
        if (_receivedMessages.empty() || isCompleteMessage(_receivedMessages.back())) {
            _receivedMessages.push({});
            _receivedMessages.back().resize(1024);
            leftOver = 4;
            first    = 0;
        } else {
            // Bad case, we currently have an incomplete message
            auto& message = _receivedMessages.back();
            if (message.size() < headerSize) {
                leftOver = headerSize - message.size();
                first    = message.size();
                message.resize(1024);
            } else {
                size_t payloadSize = *(uint64_t*)message.data();
                leftOver           = payloadSize - (message.size() - headerSize);
                first              = message.size();
                message.resize(payloadSize + headerSize);
            }
        }

        auto& message = _receivedMessages.back();

        while (leftOver) {
            assert(first + leftOver <= message.size());
            int res = read(_connFd, message.data() + first, leftOver);

            if (res == 0) {
                onClose();
                return;
            }

            if (res == -1 && errno == EAGAIN) {
                message.resize(first);
                // Reviewer: To jump out of double loop, reconsider when you say no. - gxu
                goto ReadExhuasted;
            }
            leftOver -= res;
            first += res;
            if (first == 4) {
                // reading the payload
                leftOver = *(uint64_t*)message.data();
                message.resize(leftOver + 4);
            }
        }
        assert(isCompleteMessage(_receivedMessages.back()));
    }

ReadExhuasted:
    while (_pendingReadOperations->size() && _receivedMessages.size()) {
        if (isCompleteMessage(_receivedMessages.front())) {
            *_pendingReadOperations->front()._buf = std::move(_receivedMessages.front());
            _receivedMessages.pop();

            Bytes address(_remoteIOSocketIdentity->data(), _remoteIOSocketIdentity->size());
            Bytes payload(_pendingReadOperations->front()._buf->data(), _pendingReadOperations->front()._buf->size());

            _pendingReadOperations->front()._callbackAfterCompleteRead(Message(std::move(address), std::move(payload)));

            _pendingReadOperations->pop();
        } else {
            assert(_pendingReadOperations->size());
            _pendingReadOperations->front()._callbackAfterCompleteRead(Message({}, {}));
        }
    }
}

void MessageConnectionTCP::onWrite() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // TODO: do not assume the identity to be less than 128bytes
    if (!_sendLocalIdentity) {
        // Other sizes are possible, but the size needs to be >= 8, in order for idBuf
        // to be aligned with 8 bytes boundary because of strict aliasing
        char idBuf[128] {};
        *(uint64_t*)idBuf  = _localIOSocketIdentity.size();
        auto identityBegin = idBuf + sizeof(uint64_t);
        auto [_, last]     = std::ranges::copy(_localIOSocketIdentity, identityBegin);
        write(_connFd, idBuf, std::distance(idBuf, last));
        _sendLocalIdentity = true;
    }

    assert(_sendLocalIdentity);
    printf("Have sent out the local Identity\n");

    while (!_writeOperations.empty()) {
        auto& writeOp       = _writeOperations.front();
        const size_t bufLen = writeOp._buf->size();
        while (writeOp._cursor != bufLen) {
            const int leftOver = writeOp._buf->size() - writeOp._cursor;
            const char* begin  = writeOp._buf->data() + writeOp._cursor;
            auto bytes         = write(_connFd, begin, leftOver);

            if (bytes == -1) {
                if (errno == EAGAIN)
                    break;
                else  // TODO:
                    writeOp._callbackAfterCompleteWrite(errno);
            }

            writeOp._cursor += bytes;
        }

        if (writeOp._cursor == bufLen) {
            writeOp._callbackAfterCompleteWrite(0);
            _writeOperations.pop();
        } else {
            break;
        }
    }
}

// TODO: Maybe change this to message_t
void MessageConnectionTCP::sendMessage(std::shared_ptr<std::vector<char>> msg, std::function<void(int)> callback) {
    // detect if the write operations queue is empty, if it is, simply write to exhaustion
    // if it is not, queue write operations to the end of the queue
    TcpWriteOperation writeOp;
    writeOp._buf                        = msg;
    writeOp._cursor                     = 0;
    writeOp._callbackAfterCompleteWrite = std::move(callback);

    if (_writeOperations.empty()) {
        const size_t bufLen = writeOp._buf->size();
        while (writeOp._cursor != bufLen) {
            const int leftOver = writeOp._buf->size() - writeOp._cursor;
            const char* begin  = writeOp._buf->data() + writeOp._cursor;
            auto bytes         = write(_connFd, begin, leftOver);

            if (bytes == -1) {
                if (errno == EAGAIN) {
                    _writeOperations.push(std::move(writeOp));
                } else {
                    writeOp._callbackAfterCompleteWrite(errno);
                }
                break;
            }

            writeOp._cursor += bytes;
        }

        if (writeOp._cursor == bufLen) {
            writeOp._callbackAfterCompleteWrite(0);
        }

    } else {
        _writeOperations.push(std::move(writeOp));
    }
}

bool MessageConnectionTCP::recvMessage() {
    if (_receivedMessages.size() && _pendingReadOperations->size() && isCompleteMessage(_receivedMessages.back())) {
        auto readOp = std::move(_pendingReadOperations->front());
        _pendingReadOperations->pop();
        auto msg = std::move(_receivedMessages.front());
        Bytes address(_remoteIOSocketIdentity->data(), _remoteIOSocketIdentity->size());
        Bytes payload(msg.data(), msg.size());
        readOp._callbackAfterCompleteRead(Message(std::move(address), std::move(payload)));
        _receivedMessages.pop();
        return true;
    }
    return false;
}

void MessageConnectionTCP::onClose() {
    _eventLoopThread->_eventLoop.removeFdFromLoop(_connFd);
    close(_connFd);
    auto& sock = _eventLoopThread->_identityToIOSocket.at(*_remoteIOSocketIdentity);
    sock->onConnectionDisconnected(this);
};

MessageConnectionTCP::~MessageConnectionTCP() {
    _eventLoopThread->_eventLoop.removeFdFromLoop(_connFd);
    close(_connFd);
}
