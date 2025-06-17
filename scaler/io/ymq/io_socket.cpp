#include "scaler/io/ymq/io_socket.h"

#include <algorithm>
#include <memory>
#include <ranges>
#include <vector>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"

void IOSocket::removeConnectedTcpClient() {
    printf("%s\n", __PRETTY_FUNCTION__);
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

    _eventLoopThread->_eventLoop.runAfterEachLoop([this] { this->removeConnectedTcpClient(); });
}

IOSocket::IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType)
    : _eventLoopThread(eventLoopThread), _identity(identity), _socketType(socketType) {}

IOSocket::IOSocket() {}

void IOSocket::sendMessage(
    std::shared_ptr<std::vector<char>> buf, std::function<void()> callback, std::string remoteIdentity) {
    if (_socketType == IOSocketType::Router) {
        this->_eventLoopThread->_eventLoop.executeNow([this, buf, remoteIdentity] {
            auto connection = this->_identityToConnection[remoteIdentity];
            connection->send(buf);
        });
    }
}

void IOSocket::recvMessage(std::vector<char>& buf) {}

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

    if (c == _deadConnection.end())
        return;

    int fd                                      = conn->_connFd;
    _fdToConnection[fd]->_writeOperations       = (*c)->_writeOperations;
    _fdToConnection[fd]->_receivedMessages      = (*c)->_receivedMessages;
    _fdToConnection[fd]->_pendingReadOperations = (*c)->_pendingReadOperations;
    _identityToConnection[*s]                   = _fdToConnection[fd].get();
    _deadConnection.erase(c);
}

void IOSocket::sendMessageTo(std::string remoteIdentity, std::shared_ptr<std::vector<char>> buf) {
    _eventLoopThread->_eventLoop.executeNow([this, buf] {
        // TODO: What should we do when we cannot find the connection? We cannot
        // check whether the identity presents outside the eventloop.
        auto* conn = this->_identityToConnection.at(this->identity());
        conn->sendMessage(buf);
    });
}

void IOSocket::recvMessageFrom(std::string remoteIdentity, std::shared_ptr<std::vector<char>> buf) {
    _eventLoopThread->_eventLoop.executeNow([this, buf] {
        // TODO: What should we do when we cannot find the connection? We cannot
        // check whether the identity presents outside the eventloop.
        auto* conn = this->_identityToConnection.at(this->identity());
        conn->recvMessage(buf);
    });
}
