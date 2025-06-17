
#include <netinet/in.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <memory>
#include <system_error>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_server.h"

TcpServer::TcpServer(std::shared_ptr<IOSocket> ioSocket): _socket(ioSocket) {
    auto fd = FileDescriptor::socket(AF_INET, SOCK_STREAM, 0);

    if (!fd) {
        throw std::system_error(fd.error(), std::system_category(), "Failed to create socket");
    }

    const sockaddr_in addr {
        .sin_family = AF_INET,
        .sin_port   = htons(8080),
        .sin_addr   = {.s_addr = INADDR_ANY},
    };

    if (auto err = fd->bind((const sockaddr&)addr, sizeof(addr)); err) {
        throw std::system_error(*err, std::system_category(), "Failed to bind socket");
    }

    if (auto err = fd->listen(SOMAXCONN); err) {
        throw std::system_error(*err, std::system_category(), "Failed to listen on socket");
    }

    _eventManager = std::make_unique<EventManager>(
        _socket->eventLoopThread(), *fd, [this](FileDescriptor& fd, Events events) { this->onCreated(); });
}

void TcpServer::onCreated() {
    printf("TcpServer::onAdded()\n");
    _socket->eventLoopThread()->registerEventManager(*this->_eventManager.get());
}

void TcpServer::onEvent(FileDescriptor& fd, Events events) {
    if (events.readable) {
        sockaddr_storage addr;
        socklen_t addr_len;

        auto newFd = fd.accept((sockaddr*)&addr, &addr_len, SOCK_NONBLOCK | SOCK_CLOEXEC);

        if (!newFd) {
            // todo: error handling
            panic("accept failed");
        }

        std::shared_ptr<IOSocket>& ioSocket = _socket;
        FileDescriptor& fd2                 = *newFd;
        sockaddr_storage& remoteAddress     = addr;

        _socket->addConnection(std::make_unique<MessageConnectionTCP>(ioSocket, fd2, remoteAddress));
    }
}

TcpServer::~TcpServer() {}
