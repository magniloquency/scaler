#include "scaler/io/ymq/io_socket.h"

#include <algorithm>
#include <cstdint>
#include <memory>
#include <ranges>
#include <utility>
#include <vector>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"

void IOSocket::removeConnectedTcpClient() {
    if (this->_tcpClient && this->_tcpClient->_connected) {
        printf("ONE TCP CLIENT WAS REMOVED\n");
        this->_tcpClient.reset();
    }
}

// TODO: IOSocket::onCreated should initialize component(s) based on its type.
void IOSocket::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // Different SocketType might have different rules
    if (_socketType == IOSocketType::Dealer) {
        printf("server should be created now\n");
        _tcpServer.emplace(_eventLoopThread, this->identity());
        _tcpServer->onCreated();
    }
    assert(_pendingReadOperations);

    _eventLoopThread->_eventLoop.runAfterEachLoop([this] { this->removeConnectedTcpClient(); });
}

IOSocket::IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType)
    : _eventLoopThread(eventLoopThread)
    , _identity(identity)
    , _socketType(socketType)
    , _pendingReadOperations(std::make_shared<std::queue<TcpReadOperation>>()) {}

void IOSocket::connectTo(sockaddr addr) {
    printf("%s\n", __PRETTY_FUNCTION__);
    printf("this->identity() = %s\n", this->identity().c_str());
    _eventLoopThread->_eventLoop.executeNow([this, addr] {
        _tcpClient.emplace(_eventLoopThread, this->identity(), addr);
        _tcpClient->onCreated();
    });
}

void IOSocket::onConnectionDisconnected(MessageConnectionTCP* conn) {
    int fd       = conn->_connFd;
    auto connPtr = std::move(this->_fdToConnection[fd]);
    this->_identityToConnection.erase(*connPtr->_remoteIOSocketIdentity);
    if (connPtr->_responsibleForRetry) {
        connectTo(conn->_remoteAddr);
    }
    _deadConnection.push_back(std::move(connPtr));
}

void IOSocket::onConnectionIdentityReceived(MessageConnectionTCP* conn) {
    const auto& s = conn->_remoteIOSocketIdentity;
    auto c        = std::ranges::find(_deadConnection, s, &MessageConnectionTCP::_remoteIOSocketIdentity);

    int fd                    = conn->_connFd;
    _identityToConnection[*s] = _fdToConnection[fd].get();

    if (c == _deadConnection.end())
        return;
    _fdToConnection[fd]->_writeOperations       = (*c)->_writeOperations;
    _fdToConnection[fd]->_receivedMessages      = (*c)->_receivedMessages;
    _fdToConnection[fd]->_pendingReadOperations = (*c)->_pendingReadOperations;
    _deadConnection.erase(c);
}

void IOSocket::sendMessage(Message message, std::function<void(int)> callback) {
    auto [addressPtr, addressLen] = message.address.release();
    auto [payloadPtr, payloadLen] = message.payload.release();
    _eventLoopThread->_eventLoop.executeNow(
        [this, addressPtr, addressLen, payloadPtr, payloadLen, callback = std::move(callback)] {
            // TODO: What should we do when we cannot find the connection? We cannot
            // check whether the identity presents outside the eventloop.
            try {
                auto* conn = this->_identityToConnection.at(std::string(addressPtr, addressLen));

                auto payload = std::make_shared<std::vector<char>>(8);
                payload->insert(payload->end(), payloadPtr, payloadPtr + payloadLen);
                *(uint64_t*)payload->data() = payloadLen;

                conn->sendMessage(std::move(payload), std::move(callback));
            } catch (...) {
                // TODO: Cannot find the identity, call callback here
            }
        });
}

void IOSocket::recvMessage(std::function<void(Message)> callback) {
    _eventLoopThread->_eventLoop.executeNow([this, callback = std::move(callback)] {
        TcpReadOperation readOp {std::make_shared<std::vector<char>>(), 0, std::move(callback)};
        this->_pendingReadOperations->push(std::move(readOp));
        if (_pendingReadOperations->size() == 1) {
            for (const auto& [fd, conn]: _fdToConnection) {
                if (conn->recvMessage())
                    return;
            }
        }
    });
}
