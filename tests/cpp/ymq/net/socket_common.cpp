#include <system_error>
#include <thread>
#include <utility>
#include <vector>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/net/socket.h"

Socket::Socket(bool nodelay): _impl(nullptr)
{
    this->_impl = create_socket(nodelay);
}

Socket::~Socket() = default;

Socket::Socket(Socket&& s) noexcept
{
    this->_impl = std::move(s._impl);
}

Socket& Socket::operator=(Socket&& s) noexcept
{
    this->_impl = std::move(s._impl);
    return *this;
}

void Socket::connect(const std::string& host, uint16_t port, int tries)
{
    auto host_checked = check_localhost(host.c_str());

    for (int i = 0; i < tries || tries < 0; i++) {
        try {
            return _impl->connect(host_checked, port);
        } catch (const ConnectionRefusedException& e) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }

    throw std::runtime_error("connect failed after multiple tries");
}

void Socket::bind(uint16_t port)
{
    _impl->bind(port);
}

void Socket::listen(int backlog)
{
    _impl->listen(backlog);
}

Socket Socket::accept()
{
    auto clientImpl = _impl->accept();
    Socket s;
    s._impl = std::move(clientImpl);
    return s;
}

int Socket::send(const void* data, size_t size)
{
    return _impl->send(data, size);
}

int Socket::recv(void* buffer, size_t size)
{
    return _impl->recv(buffer, size);
}

void Socket::flush()
{
    return _impl->flush();
}

void Socket::close()
{
    _impl->close();
}

void Socket::write_all(const void* data, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += this->send((const char*)data + cursor, size - cursor);
}

void Socket::write_all(std::string message)
{
    size_t cursor = 0;
    while (cursor < message.size())
        cursor += this->send(message.data() + cursor, message.size() - cursor);
}

void Socket::read_exact(void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += this->recv((char*)buffer + cursor, size - cursor);
}

void Socket::write_message(std::string msg)
{
    uint64_t header = msg.length();
    this->write_all((void*)&header, 8);
    this->write_all(msg.data(), msg.length());
}

std::string Socket::read_message()
{
    uint64_t header = 0;
    this->read_exact((void*)&header, 8);
    std::vector<char> buffer(header);
    this->read_exact(buffer.data(), header);
    return std::string(buffer.data(), header);
}
