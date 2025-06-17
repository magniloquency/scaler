#include "scaler/io/ymq/tcp_client.h"

#include <sys/socket.h>

#include <memory>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection_tcp.h"

void TcpClient::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    int sockfd    = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    this->_connFd = sockfd;
    int ret       = connect(sockfd, (sockaddr*)&_remoteAddr, sizeof(_remoteAddr));
    // if (ret < 0) {
    //     if (errno != EINPROGRESS) {
    //         perror("connect");
    //         close(sockfd);
    //         return;
    //     } else {
    //         // TODO: Think about the lifetime of _eventManager.
    //         printf("Connecting (EINPROGRESS), adding fd to loop\n");
    //         _eventLoopThread->_eventLoop.addFdToLoop(sockfd, EPOLLOUT, this->_eventManager.get());
    //     }
    // } else {
    //     printf("client SUCCESS\n");
    //     std::string id = this->_localIOSocketIdentity;
    //     auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);
    //     // FIXME: the second _addr is not real
    //     sock->_fdToConnection[sockfd] =
    //         std::make_unique<MessageConnectionTCP>(_eventLoopThread, sockfd, _remoteAddr, _remoteAddr, id);
    //     sock->_fdToConnection[sockfd]->onCreated();
    //     // The idea is, this tcpClient needs to be reset
    // }
}

// TcpClient::TcpClient(
//     std::shared_ptr<EventLoopThread> eventLoopThread, std::string localIOSocketIdentity, sockaddr remoteAddr)
//     : _eventLoopThread(eventLoopThread)
//     , _localIOSocketIdentity(std::move(localIOSocketIdentity))
//     , _remoteAddr(std::move(remoteAddr))
//     , _eventManager(std::make_shared<EventManager>(_eventLoopThread))
//     , _connected(false) {
//     _eventManager->onRead  = [this] { this->onRead(); };
//     _eventManager->onWrite = [this] { this->onWrite(); };
//     _eventManager->onClose = [this] { this->onClose(); };
//     _eventManager->onError = [this] { this->onError(); };
// }

void TcpClient::onWrite() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // assuming success
    sockaddr addr;
    int ret = connect(_connFd, (sockaddr*)&addr, sizeof(addr));
    // TODO: -^ what if this connect failed?
    std::string id = this->_localIOSocketIdentity;
    // auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);
    // FIXME: the second _addr is not real
    // sock->_fdToConnection[_connFd] = std::make_unique<MessageConnectionTCP>(_eventLoopThread, _connFd, addr, addr, id);
    // sock->_fdToConnection[_connFd]->onCreated();
    _connected = true;
}

void TcpClient::onRead() {
    printf("TcpClient::onRead()\n");
}

TcpClient::~TcpClient() {}
