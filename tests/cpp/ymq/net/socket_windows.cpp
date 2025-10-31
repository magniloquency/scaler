#include <optional>
#include <stdexcept>
#include <system_error>

#include <winsock2.h>
#include <ws2tcpip.h>

#include "socket.h"
#include "../common/utils.h"

struct Socket::Impl {
    SOCKET s = INVALID_SOCKET;
    bool nodelay;

    Impl(bool nodelay, std::optional<SOCKET> socket = std::nullopt) {
        this->nodelay = nodelay;
        s = *socket.or_else([] -> std::optional<SOCKET> { return ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP); });
        if (s == INVALID_SOCKET)
            throw std::system_error(last_socket_error(), "failed to create socket");

        int on = 1;
        if (this->nodelay && setsockopt(this->s, IPPROTO_TCP, TCP_NODELAY, (const char*)&on, sizeof(on)) == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to set nodelay");

        if (setsockopt(this->s, SOL_SOCKET, SO_REUSEADDR, (const char*)&on, sizeof(on)) == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to set reuseaddr");
    }

    ~Impl() { close(); }

    void connect(const std::string& host, uint16_t port)
    {
        sockaddr_in addr;
        addr.sin_family = AF_INET;
        addr.sin_port   = htons(port);
        inet_pton(AF_INET, host.c_str(), &addr.sin_addr);
        if (::connect(s, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to connect");
    }

    void bind(uint16_t port)
    {
        sockaddr_in addr {};
        addr.sin_family      = AF_INET;
        addr.sin_port        = htons(port);
        addr.sin_addr.s_addr = INADDR_ANY;
        if (::bind(s, (sockaddr*)&addr, sizeof(addr)) == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to bind");
    }

    void listen(int backlog)
    {
        if (::listen(s, backlog) == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to listen");
    }

    std::unique_ptr<Impl> accept()
    {
        SOCKET client = ::accept(s, nullptr, nullptr);
        if (client == INVALID_SOCKET)
            throw std::system_error(last_socket_error(), "failed to accept connection");
        return std::make_unique<Impl>(this->nodelay, client);
    }

    int send(const void* data, size_t size)
    {
        auto n = ::send(s, static_cast<const char*>(data), (int)size, 0);
        if (n == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to send data");
        return n;
    }

    int recv(void* buffer, size_t size)
    {
        auto n = ::recv(s, static_cast<char*>(buffer), (int)size, 0);
        if (n == SOCKET_ERROR)
            throw std::system_error(last_socket_error(), "failed to receive data");
        return n;
    }

    void flush() { throw std::runtime_error("flush not implemented on Windows"); }

    void close()
    {
        if (s != INVALID_SOCKET) {
            ::closesocket(s);
            s = INVALID_SOCKET;
        }
    }
};
