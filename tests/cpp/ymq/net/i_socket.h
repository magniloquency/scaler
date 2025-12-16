#pragma once
#include <memory>
#include <string>

class ISocket {
public:
    virtual ~ISocket() = default;

    virtual void tryConnect(const std::string& address, int tries = 10) const = 0;
    virtual void bind(const std::string& address) const                       = 0;
    virtual void listen(int backlog = 5) const                                = 0;
    virtual std::unique_ptr<ISocket> accept() const                           = 0;

    virtual void writeAll(const void* data, size_t size) const = 0;
    virtual void writeAll(std::string msg) const               = 0;

    virtual void readExact(void* buffer, size_t size) const = 0;

    virtual void writeMessage(std::string msg) const = 0;

    virtual std::string readMessage() const = 0;
};
