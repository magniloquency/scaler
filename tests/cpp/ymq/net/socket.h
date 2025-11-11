#pragma once
#include <cstdint>
#include <exception>
#include <memory>
#include <string>

class ConnectionRefusedException: public std::exception {
public:
    const char* what() const noexcept override { return "Socket connection was refused"; }
};

class Socket {
public:
    struct Impl {
        virtual void connect(const std::string& host, uint16_t port) = 0;
        virtual void bind(uint16_t port)                             = 0;
        virtual void listen(int backlog)                             = 0;
        virtual std::unique_ptr<Impl> accept()                       = 0;
        virtual int send(const void* data, size_t size)              = 0;
        virtual int recv(void* buffer, size_t size)                  = 0;
        virtual void flush()                                         = 0;
        virtual void close()                                         = 0;
        virtual ~Impl()                                              = default;
    };

    Socket(bool nodelay = false);
    ~Socket();

    // move-only
    Socket(Socket&&) noexcept;
    Socket& operator=(Socket&&) noexcept;
    Socket(const Socket&)            = delete;
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
    std::unique_ptr<Impl> _impl;  // Pointer to platform-specific implementation
};

std::unique_ptr<Socket::Impl> create_socket(bool nodelay);
