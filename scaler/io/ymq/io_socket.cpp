#include "scaler/io/ymq/io_socket.h"

#include <algorithm>
#include <cstdint>
#include <expected>
#include <memory>
#include <ranges>
#include <utility>
#include <vector>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"
#include "scaler/io/ymq/utils.h"

void IOSocket::removeConnectedTcpClient() {
    if (this->_tcpClient && this->_tcpClient->_connected) {
        printf("ONE TCP CLIENT WAS REMOVED\n");
        this->_tcpClient.reset();
    }
}

// TODO: IOSocket::onCreated should initialize component(s) based on its type.
// THIS THING DIES
void IOSocket::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    assert(_pendingReadOperations);

    _eventLoopThread->_eventLoop.runAfterEachLoop([this] { this->removeConnectedTcpClient(); });
}

IOSocket::IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType)
    : _eventLoopThread(eventLoopThread)
    , _identity(identity)
    , _socketType(socketType)
    , _pendingReadOperations(std::make_shared<std::queue<TcpReadOperation>>()) {}

void IOSocket::connectTo(sockaddr addr, ConnectReturnCallback callback) {
    printf("%s\n", __PRETTY_FUNCTION__);
    printf("this->identity() = %s\n", this->identity().c_str());
    _eventLoopThread->_eventLoop.executeNow([this, addr = std::move(addr), callback = std::move(callback)] {
        _tcpClient.emplace(_eventLoopThread, this->identity(), std::move(addr), std::move(callback));
        _tcpClient->onCreated();
    });
}

void IOSocket::connectTo(std::string networkAddress, ConnectReturnCallback callback) {
    auto res = stringToSockaddr(std::move(networkAddress));
    assert(res);
    connectTo(std::move(res.value()), std::move(callback));
}

void IOSocket::bindTo(std::string networkAddress, BindReturnCallback callback) {
    if (_tcpServer) {
        callback(-1);
        return;
    }
    auto res = stringToSockaddr(std::move(networkAddress));
    assert(res);

    printf("server should be created now\n");
    _tcpServer.emplace(_eventLoopThread, this->identity(), std::move(res.value()), std::move(callback));
    _tcpServer->onCreated();
}

void IOSocket::onConnectionDisconnected(MessageConnectionTCP* conn) {
    int fd       = conn->_connFd;
    auto connPtr = std::move(this->_fdToConnection[fd]);
    this->_identityToConnection.erase(*connPtr->_remoteIOSocketIdentity);
    if (connPtr->_responsibleForRetry) {
        connectTo(conn->_remoteAddr, [](int) {});  // as the user callback is one-shot
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

void IOSocket::sendMessage(Message message, SendMessageCallback callback) {
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
                ;
                callback(-1);
            }
        });
}

void IOSocket::recvMessage(RecvMessageCallback callback) {
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
