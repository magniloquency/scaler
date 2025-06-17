#include "scaler/io/ymq/io_socket.h"

#include <memory>
#include <vector>

#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"
// NOTE: We need it after we put impl
#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/message_connection_tcp.h"

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
        _tcpServer = std::make_unique<TcpServer>(shared_from_this());
        _tcpServer->onCreated();
    }

    _eventLoopThread->_eventLoop->runAfterEachLoop([this] { this->removeConnectedTcpClient(); });
}

IOSocket::IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType)
    : _eventLoopThread(eventLoopThread), _identity(identity), _socketType(socketType) {}

IOSocket::IOSocket() {}

void IOSocket::sendMessage(Bytes buf, std::function<void()> callback, std::string remoteIdentity) {
    if (_socketType == IOSocketType::Router) {
        this->_eventLoopThread->_eventLoop->executeNow([this, buf = std::move(buf), remoteIdentity, callback] mutable {
            auto connection = this->_identityToConnection[remoteIdentity];
            connection->send(std::move(buf), callback);
        });
    }
}

void IOSocket::recvMessage(std::vector<char>& buf) {}

void IOSocket::connectTo(sockaddr addr) {
    printf("%s\n", __PRETTY_FUNCTION__);
    printf("this->identity() = %s\n", this->identity().c_str());
    _eventLoopThread->_eventLoop->executeNow([this, addr] {
        _tcpClient = std::make_unique<TcpClient>(_eventLoopThread, this->identity(), addr);
        _tcpClient->onCreated();
    });
}
