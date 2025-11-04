#include <unistd.h>

#include <cerrno>
#include <system_error>

#include "pipe.h"

static std::error_code last_error()
{
    return std::error_code(errno, std::system_category());
}

struct PipeReader::Impl {
    int fd = -1;

    int read(void* buffer, size_t size)
    {
        ssize_t n = ::read(fd, buffer, size);
        if (n < 0)
            throw std::system_error(last_error(), "read");
        return n;
    }

    void close()
    {
        if (fd >= 0) {
            ::close(fd);
            fd = -1;
        }
    }

    bool valid() const noexcept { return fd >= 0; }
    ~Impl() { close(); }
};

struct PipeWriter::Impl {
    int fd = -1;

    int write(const void* data, size_t size)
    {
        ssize_t n = ::write(fd, data, size);
        if (n < 0)
            throw std::system_error(last_error(), "write");
        return n;
    }

    void close()
    {
        if (fd >= 0) {
            ::close(fd);
            fd = -1;
        }
    }

    bool valid() const noexcept { return fd >= 0; }
    ~Impl() { close(); }
};

struct Pipe::Impl {
    static std::pair<PipeReader, PipeWriter> create()
    {
        int fds[2];
        if (::pipe(fds) < 0)
            throw std::system_error(last_error(), "pipe");

        PipeReader reader;
        PipeWriter writer;

        reader.impl->fd = fds[0];
        writer.impl->fd = fds[1];

        return std::make_pair(std::move(reader), std::move(writer));
    }
};
