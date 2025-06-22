#include "scaler/io/ymq/tcp_server.h"

#include <netinet/in.h>
#include <netinet/tcp.h>
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
        callback(errno);
        return -1;
    }

    int optval = 1;
    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &optval, sizeof(optval)) == -1) {
        perror("setsockopt");
        close(server_fd);
        callback(errno);
        return -1;
    }

    if (bind(server_fd, &addr, sizeof(addr)) == -1) {
        perror("bind");
        close(server_fd);
        callback(errno);
        return -1;
    }

    if (listen(server_fd, SOMAXCONN) == -1) {
        perror("listen");
        close(server_fd);
        callback(errno);
        return -1;
    }

    callback(0);
    return server_fd;
}

TcpServer::TcpServer(
    std::shared_ptr<EventLoopThread> eventLoopThread,
    std::string localIOSocketIdentity,
    sockaddr addr,
    BindReturnCallback onBindReturn)
    : _eventLoopThread(eventLoopThread)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _addr(std::move(addr))
    , _onBindReturn(std::move(onBindReturn))
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
    std::string id = this->_localIOSocketIdentity;
    auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);

    while (true) {
        sockaddr remoteAddr {};
        socklen_t remoteAddrLen = sizeof(remoteAddr);

        int fd = accept4(_serverFd, &remoteAddr, &remoteAddrLen, SOCK_NONBLOCK | SOCK_CLOEXEC);
        if (fd < 0) {
            int localErrno = errno;
            switch (localErrno) {
                // case EWOULDBLOCK: // same as EAGAIN
                case EAGAIN:
                case ENETDOWN:
                case EPROTO:
                case ENOPROTOOPT:
                case EHOSTDOWN:
                case ENONET:
                case EHOSTUNREACH:
                case EOPNOTSUPP:
                case ENETUNREACH: return;

                default:
                    fprintf(stderr, "accept4 failed with errno %d: %s\n", localErrno, strerror(localErrno));
                    // TODO: Change this to a user callback
                    exit(-1);
            }
        }

        if (remoteAddrLen > sizeof(remoteAddr)) {
            fprintf(stderr, "Are you using IPv6? This is probably not supported as of now.\n");
        }

        int optval = 1;
        if (setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &optval, sizeof(optval)) == -1) {
            perror("setsockopt");
            fprintf(stderr, "TCP_NODELAY cannot be set\n");
            close(fd);
            exit(-1);
        }

        sock->_unconnectedConnection.push_back(
            std::make_unique<MessageConnectionTCP>(
                _eventLoopThread,
                fd,
                _addr,       // local (listening) address
                remoteAddr,  // remote (peer) address
                sock->identity(),
                false,
                sock->_pendingReadOperations));

        sock->_unconnectedConnection.back()->onCreated();
    }
}

TcpServer::~TcpServer() {
    if (_serverFd != 0) {
        _eventLoopThread->_eventLoop.removeFdFromLoop(_serverFd);
        close(_serverFd);
    }
}
