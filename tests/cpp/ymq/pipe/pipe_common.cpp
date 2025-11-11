#include <utility>

#include "tests/cpp/ymq/pipe/pipe.h"

Pipe::Pipe(): reader(nullptr), writer(nullptr)
{
    std::pair<PipeReader, PipeWriter> pair = create_pipe();
    this->reader                           = std::move(pair.first);
    this->writer                           = std::move(pair.second);
}

Pipe::~Pipe() = default;

Pipe::Pipe(Pipe&& p) noexcept: reader(nullptr), writer(nullptr)
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

PipeReader::PipeReader(std::unique_ptr<Impl> impl): _impl(std::move(impl))
{
}

PipeReader::~PipeReader() = default;

PipeReader::PipeReader(PipeReader&&) noexcept            = default;
PipeReader& PipeReader::operator=(PipeReader&&) noexcept = default;

int PipeReader::read(void* buffer, size_t size)
{
    return _impl->read(buffer, size);
}

void PipeReader::read_exact(void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += this->read((char*)buffer + cursor, size - cursor);
}

void PipeReader::close()
{
    _impl->close();
}

bool PipeReader::valid() const noexcept
{
    return _impl && _impl->valid();
}

const void* PipeReader::handle() const noexcept
{
    return _impl->handle();
}

PipeWriter::PipeWriter(std::unique_ptr<Impl> impl): _impl(std::move(impl))
{
}

PipeWriter::~PipeWriter() = default;

PipeWriter::PipeWriter(PipeWriter&&) noexcept            = default;
PipeWriter& PipeWriter::operator=(PipeWriter&&) noexcept = default;

int PipeWriter::write(const void* data, size_t size)
{
    return _impl->write((const char*)data, size);
}

void PipeWriter::write_all(const void* data, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += (size_t)this->write((char*)data + cursor, size - cursor);
}

void PipeWriter::close()
{
    _impl->close();
}

bool PipeWriter::valid() const noexcept
{
    return _impl && _impl->valid();
}
