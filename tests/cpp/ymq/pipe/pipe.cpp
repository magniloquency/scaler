#include "tests/cpp/ymq/pipe/pipe.h"

#include <utility>

#ifdef __linux__
#include "tests/cpp/ymq/pipe/pipe_linux.cpp"
#endif  // __linux__
#ifdef _WIN32
#include "tests/cpp/ymq/pipe/pipe_windows.cpp"
#endif  // _WIN32

Pipe::Pipe()
{
    std::pair<PipeReader, PipeWriter> pair = Impl::create();
    this->reader                           = std::move(pair.first);
    this->writer                           = std::move(pair.second);
}

Pipe::~Pipe() = default;

Pipe::Pipe(Pipe&& p) noexcept
{
    this->reader = std::move(p.reader);
    this->writer = std::move(p.writer);
}

Pipe& Pipe::operator=(Pipe&& p) noexcept
{
    this->reader = std::move(p.reader);
    this->writer = std::move(p.writer);
    return *this;
}

PipeReader::PipeReader(): impl(std::make_unique<Impl>())
{
}

PipeReader::~PipeReader() = default;

PipeReader::PipeReader(PipeReader&&) noexcept            = default;
PipeReader& PipeReader::operator=(PipeReader&&) noexcept = default;

int PipeReader::read(void* buffer, size_t size)
{
    return impl->read(buffer, size);
}

void PipeReader::read_exact(void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += this->read((char*)buffer + cursor, size - cursor);
}

void PipeReader::close()
{
    impl->close();
}

bool PipeReader::valid() const noexcept
{
    return impl && impl->valid();
}

#ifdef __linux__
int PipeReader::fd() const noexcept
{
    return impl->fd;
}
#endif  // __linux__

PipeWriter::PipeWriter(): impl(std::make_unique<Impl>())
{
}

PipeWriter::~PipeWriter() = default;

PipeWriter::PipeWriter(PipeWriter&&) noexcept            = default;
PipeWriter& PipeWriter::operator=(PipeWriter&&) noexcept = default;

int PipeWriter::write(const void* data, size_t size)
{
    return impl->write((const char*)data, size);
}

void PipeWriter::write_all(const void* data, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += this->write((char*)data + cursor, size - cursor);
}

void PipeWriter::close()
{
    impl->close();
}

bool PipeWriter::valid() const noexcept
{
    return impl && impl->valid();
}
