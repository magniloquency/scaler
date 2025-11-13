#include <unistd.h>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/pipe/pipe.h"

PipeReader::PipeReader(long long fd): _fd(fd)
{
}

PipeReader::~PipeReader()
{
    close(this->_fd);
}

PipeReader::PipeReader(PipeReader&& other) noexcept
{
    this->_fd = other._fd;
    other._fd = -1;
}

PipeReader& PipeReader::operator=(PipeReader&& other) noexcept
{
    this->_fd = other._fd;
    other._fd = -1;
    return *this;
}

const long long PipeReader::fd() const noexcept
{
    return this->_fd;
}

int PipeReader::read(void* buffer, size_t size)
{
    ssize_t n = ::read(this->_fd, buffer, size);
    if (n < 0)
        raise_system_error("read");
    return n;
}

void PipeReader::read_exact(void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += (size_t)this->read((char*)buffer + cursor, size - cursor);
}

PipeWriter::PipeWriter(long long fd): _fd(fd)
{
}

PipeWriter::~PipeWriter()
{
    close(this->_fd);
}

PipeWriter::PipeWriter(PipeWriter&& other) noexcept
{
    this->_fd = other._fd;
    other._fd = -1;
}

PipeWriter& PipeWriter::operator=(PipeWriter&& other) noexcept
{
    this->_fd = other._fd;
    other._fd = -1;
    return *this;
}

int PipeWriter::write(const void* buffer, size_t size)
{
    ssize_t n = ::write(this->_fd, buffer, size);
    if (n < 0)
        raise_system_error("write");
    return n;
}

void PipeWriter::write_all(const void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += (size_t)this->write((char*)buffer + cursor, size - cursor);
}

std::pair<long long, long long> create_pipe()
{
    int fds[2];
    if (::pipe(fds) < 0)
        raise_system_error("pipe");

    return std::make_pair(fds[0], fds[1]);
}
