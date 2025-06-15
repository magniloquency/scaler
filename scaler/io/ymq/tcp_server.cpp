#include "scaler/io/ymq/tcp_server.h"

#include <netinet/in.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <memory>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection_tcp.h"

static int create_and_bind_socket() {
    int server_fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    if (server_fd == -1) {
        perror("socket");
        return -1;
    }

    sockaddr_in addr {};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(8080);
    addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) == -1) {
        perror("bind");
        close(server_fd);
        return -1;
    }

    if (listen(server_fd, SOMAXCONN) == -1) {
        perror("listen");
        close(server_fd);
        return -1;
    }

    return server_fd;
}

// TODO: Allow user to specify port/addr
TcpServer::TcpServer(std::shared_ptr<EventLoopThread> eventLoopThread, std::string localIOSocketIdentity)
    : _eventLoopThread(eventLoopThread)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _addr()
    , _addr_len(sizeof(sockaddr)) {
    _serverFd = create_and_bind_socket();

    _eventManager->onRead  = [this] { this->onRead(); };
    _eventManager->onWrite = [this] { this->onWrite(); };
    _eventManager->onClose = [this] { this->onClose(); };
    _eventManager->onError = [this] { this->onError(); };
}

void TcpServer::onCreated() {
    // _eventLoopThread->eventLoop.registerEventManager(*this->_eventManager.get());
    _eventLoopThread->_eventLoop.addFdToLoop(_serverFd, EPOLLIN | EPOLLET, this->_eventManager.get());
}

void TcpServer::onRead() {
    printf("%s\n", __PRETTY_FUNCTION__);
    printf("Got a new connection, local iosocket identity = %s\n", _localIOSocketIdentity.c_str());

    int fd         = accept4(_serverFd, &_addr, &_addr_len, SOCK_NONBLOCK | SOCK_CLOEXEC);
    std::string id = this->_localIOSocketIdentity;
    auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);
    // FIXME: the second _addr is not real
    sock->_fdToConnection[fd] =
        std::make_unique<MessageConnectionTCP>(_eventLoopThread, fd, _addr, _addr, sock->identity());
    sock->_fdToConnection[fd]->onCreated();
}

TcpServer::~TcpServer() {}
