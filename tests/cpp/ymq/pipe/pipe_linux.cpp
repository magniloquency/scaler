#include <unistd.h>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/pipe/pipe.h"

struct PipeReaderImpl: public PipeReader::Impl {
    int fd = -1;

    int read(void* buffer, size_t size) override
    {
        ssize_t n = ::read(fd, buffer, size);
        if (n < 0)
            raise_system_error("read");
        return n;
    }

    void close() override
    {
        if (fd >= 0) {
            ::close(fd);
            fd = -1;
        }
    }

    const void* handle() const noexcept override { return &this->fd; }

    bool valid() const noexcept override { return fd >= 0; }
    ~PipeReaderImpl() override { close(); }
};

struct PipeWriterImpl: public PipeWriter::Impl {
    int fd = -1;

    int write(const void* data, size_t size) override
    {
        ssize_t n = ::write(fd, data, size);
        if (n < 0)
            raise_system_error("write");
        return n;
    }

    void close() override
    {
        if (fd >= 0) {
            ::close(fd);
            fd = -1;
        }
    }

    bool valid() const noexcept override { return fd >= 0; }
    ~PipeWriterImpl() override { close(); }
};

std::pair<PipeReader, PipeWriter> create_pipe()
{
    int fds[2];
    if (::pipe(fds) < 0)
        raise_system_error("pipe");

    auto reader_impl = std::make_unique<PipeReaderImpl>();
    auto writer_impl = std::make_unique<PipeWriterImpl>();

    reader_impl->fd = fds[0];
    writer_impl->fd = fds[1];

    PipeReader reader(std::move(reader_impl));
    PipeWriter writer(std::move(writer_impl));

    return std::make_pair(std::move(reader), std::move(writer));
}
