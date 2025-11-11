#include <arpa/inet.h>
#include <netinet/tcp.h>
#include <sys/socket.h>
#include <unistd.h>

#include <memory>
#include <optional>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/net/socket.h"

struct SocketImpl: public Socket::Impl {
    int fd = -1;
    bool nodelay;

    SocketImpl(bool nodelay, std::optional<int> fd = std::nullopt)
    {
        this->nodelay = nodelay;

        if (fd) {
            this->fd = *fd;
        } else {
            this->fd = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
            if (this->fd < 0)
                raise_socket_error("failed to create socket");
        }

        int on = 1;
        if (this->nodelay && setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            raise_socket_error("failed to set nodelay");

        if (setsockopt(this->fd, SOL_SOCKET, SO_REUSEADDR, (char*)&on, sizeof(on)) < 0)
            raise_socket_error("failed to set reuseaddr");
    }

    ~SocketImpl() override { close(); }

    void connect(const std::string& host, uint16_t port) override
    {
        sockaddr_in addr {};
        addr.sin_family = AF_INET;
        addr.sin_port   = htons(port);
        inet_pton(AF_INET, host.c_str(), &addr.sin_addr);
        if (::connect(fd, (sockaddr*)&addr, sizeof(addr)) < 0) {
            if (errno == ECONNREFUSED)
                throw ConnectionRefusedException();
            else
                raise_socket_error("failed to connect");
        }
    }

    void bind(uint16_t port) override
    {
        sockaddr_in addr {};
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(port);
        addr.sin_addr.s_addr = INADDR_ANY;
        if (::bind(fd, (sockaddr*)&addr, sizeof(addr)) < 0)
            raise_socket_error("failed to bind");
    }

    void listen(int backlog) override
    {
        if (::listen(fd, backlog) < 0)
            raise_socket_error("failed to listen");
    }

    std::unique_ptr<Socket::Impl> accept() override
    {
        int client = ::accept(fd, nullptr, nullptr);
        if (client < 0)
            raise_socket_error("failed to accept");

        return std::make_unique<SocketImpl>(this->nodelay, client);
    }

    int send(const void* data, size_t size) override
    {
        ssize_t n = ::write(fd, data, size);
        if (n < 0)
            raise_socket_error("failed to send");
        return n;
    }

    int recv(void* buffer, size_t size) override
    {
        ssize_t n = ::read(fd, buffer, size);
        if (n < 0)
            raise_socket_error("failed to recv");
        return n;
    }

    void flush() override
    {
        int on  = 1;
        int off = 0;

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&off, sizeof(off)) < 0)
            raise_socket_error("failed to disable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            raise_socket_error("failed to enable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&off, sizeof(off)) < 0)
            raise_socket_error("failed to disable nodelay");

        if (setsockopt(this->fd, IPPROTO_TCP, TCP_NODELAY, (char*)&on, sizeof(on)) < 0)
            raise_socket_error("failed to enable nodelay");
    }

    void close() override
    {
        if (fd > 0) {
            ::close(fd);
            fd = -1;
        }
    }
};

std::unique_ptr<Socket::Impl> create_socket(bool nodelay)
{
    return std::make_unique<SocketImpl>(nodelay);
}
