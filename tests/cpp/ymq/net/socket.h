#pragma once
#include <cstdint>
#include <memory>
#include <string>

class Socket {
public:
    Socket(bool nodelay = false);
    ~Socket();

    // move-only
    Socket(Socket&&) noexcept;
    Socket& operator=(Socket&&) noexcept;
    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;

    void connect(const std::string& host, uint16_t port, int tries = 10);
    void bind(uint16_t port);
    void listen(int backlog = 5);
    Socket accept();

    int send(const void* data, size_t size);
    int recv(void* buffer, size_t size);
    void flush();
    void close();

    void write_all(const void* data, size_t size);
    void write_all(std::string msg);
    void read_exact(void* buffer, size_t size);

    void write_message(std::string msg);
    std::string read_message();

private:
    struct Impl;                 // Forward declaration
    std::unique_ptr<Impl> impl;  // Pointer to platform-specific implementation
};
