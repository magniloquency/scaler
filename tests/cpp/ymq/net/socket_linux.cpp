#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>

#include <system_error>

#include "../common/utils.h"
#include "socket.h"

struct Socket::Impl {
    int fd = -1;
    bool nodelay;

    Impl(bool nodelay)
    {
        this->nodelay = nodelay;

        fd = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (fd < 0)
            throw std::system_error(last_socket_error(), "failed to create socket");

        int on = 1;
        if (this->nodelay && setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            throw std::system_error(last_socket_error(), "failed to set nodelay");

        if (setsockopt(this->fd, SOL_SOCKET, SO_REUSEADDR, (char*)&on, sizeof(on)) < 0)
            throw std::system_error(last_socket_error(), "failed to set reuseaddr");
    }

    ~Impl() { close(); }

    void connect(const std::string& host, uint16_t port)
    {
        sockaddr_in addr {};
        addr.sin_family = AF_INET;
        addr.sin_port   = htons(port);
        inet_pton(AF_INET, host.c_str(), &addr.sin_addr);
        if (::connect(fd, (sockaddr*)&addr, sizeof(addr)) < 0)
            throw std::system_error(last_socket_error(), "failed to connect");
    }

    void bind(uint16_t port)
    {
        sockaddr_in addr {};
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(port);
        addr.sin_addr.s_addr = INADDR_ANY;
        if (::bind(fd, (sockaddr*)&addr, sizeof(addr)) < 0)
            throw std::system_error(last_socket_error(), "failed to bind");
    }

    void listen(int backlog)
    {
        if (::listen(fd, backlog) < 0)
            throw std::system_error(last_socket_error(), "failed to listen");
    }

    std::unique_ptr<Impl> accept()
    {
        int client = ::accept(fd, nullptr, nullptr);
        if (client < 0)
            throw std::system_error(last_socket_error(), "failed to accept");

        auto impl = std::make_unique<Impl>(this->nodelay);
        impl->fd  = client;
        return impl;
    }

    int send(const void* data, size_t size)
    {
        ssize_t n = ::write(fd, data, size);
        if (n < 0)
            throw std::system_error(last_socket_error(), "failed to send");
        return n;
    }

    int recv(void* buffer, size_t size)
    {
        ssize_t n = ::read(fd, buffer, size);
        if (n < 0)
            throw std::system_error(last_socket_error(), "failed to recv");
        return n;
    }

    void flush()
    {
        int on  = 1;
        int off = 0;

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&off, sizeof(off)) < 0)
            throw std::system_error(last_socket_error(), "failed to disable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            throw std::system_error(last_socket_error(), "failed to enable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&off, sizeof(off)) < 0)
            throw std::system_error(last_socket_error(), "failed to disable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            throw std::system_error(last_socket_error(), "failed to enable nodelay");
    }

    void close()
    {
        if (fd > 0) {
            ::close(fd);
            fd = -1;
        }
    }
};
