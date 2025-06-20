#include "scaler/io/ymq/tcp_server.h"

#include <netinet/in.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <memory>

#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection_tcp.h"

static int create_and_bind_socket(const sockaddr& addr, Configuration::BindReturnCallback callback) {
    int server_fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    if (server_fd == -1) {
        perror("socket");
        callback(-1);
        return -1;
    }

    int optval = 1;
    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval)) == -1) {
        perror("setsockopt");
        close(server_fd);
        callback(-1);
        return -1;
    }

    if (bind(server_fd, &addr, sizeof(addr)) == -1) {
        perror("bind");
        close(server_fd);
        callback(-1);
        return -1;
    }

    if (listen(server_fd, SOMAXCONN) == -1) {
        perror("listen");
        close(server_fd);
        callback(-1);
        return -1;
    }

    callback(0);
    return server_fd;
}

// TODO: Allow user to specify port/addr
TcpServer::TcpServer(
    std::shared_ptr<EventLoopThread> eventLoopThread,
    std::string localIOSocketIdentity,
    sockaddr addr,
    BindReturnCallback onBindReturn)
    : _eventLoopThread(eventLoopThread)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _addr(std::move(addr))
    , _addrLen(sizeof(sockaddr))
    , _onBindReturn(onBindReturn)
    , _serverFd {} {
    _eventManager->onRead  = [this] { this->onRead(); };
    _eventManager->onWrite = [this] { this->onWrite(); };
    _eventManager->onClose = [this] { this->onClose(); };
    _eventManager->onError = [this] { this->onError(); };
}

void TcpServer::onCreated() {
    _serverFd = create_and_bind_socket(this->_addr, std::move(this->_onBindReturn));
    if (_serverFd != -1)
        _eventLoopThread->_eventLoop.addFdToLoop(_serverFd, EPOLLIN | EPOLLET, this->_eventManager.get());
    else
        _serverFd = 0;
}

void TcpServer::onRead() {
    printf("%s\n", __PRETTY_FUNCTION__);
    printf("Got a new connection, local iosocket identity = %s\n", _localIOSocketIdentity.c_str());

    int fd = accept4(_serverFd, &_addr, &_addrLen, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (fd < 0) {
        perror("accept4");
        exit(-1);
    }

    std::string id = this->_localIOSocketIdentity;
    auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);
    // FIXME: the second _addr is not real
    sock->_unconnectedConnection.push_back(
        std::make_unique<MessageConnectionTCP>(
            _eventLoopThread, fd, _addr, _addr, sock->identity(), false, sock->_pendingReadOperations));
    sock->_unconnectedConnection.back()->onCreated();
}

TcpServer::~TcpServer() {
    if (_serverFd != 0) {
        _eventLoopThread->_eventLoop.removeFdFromLoop(_serverFd);
        close(_serverFd);
    }
}
