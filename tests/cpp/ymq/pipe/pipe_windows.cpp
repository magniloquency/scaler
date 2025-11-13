#include <windows.h>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/pipe/pipe.h"

PipeReader::PipeReader(long long fd): _fd(fd)
{
}

PipeReader::~PipeReader()
{
    CloseHandle((HANDLE)this->_fd);
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
    DWORD bytes_read = 0;
    if (!ReadFile((HANDLE)this->_fd, buffer, (DWORD)size, &bytes_read, nullptr))
        raise_system_error("failed to read");
    return bytes_read;
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
    CloseHandle((HANDLE)this->_fd);
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
    DWORD bytes_written = 0;
    if (!WriteFile((HANDLE)this->_fd, buffer, (DWORD)size, &bytes_written, nullptr))
        raise_system_error("failed to write to pipe");
    return bytes_written;
}

void PipeWriter::write_all(const void* buffer, size_t size)
{
    size_t cursor = 0;
    while (cursor < size)
        cursor += (size_t)this->write((char*)buffer + cursor, size - cursor);
}

std::pair<long long, long long> create_pipe()
{
    SECURITY_ATTRIBUTES sa {};
    sa.nLength        = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE reader = INVALID_HANDLE_VALUE;
    HANDLE writer = INVALID_HANDLE_VALUE;

    if (!CreatePipe(&reader, &writer, &sa, 0))
        raise_system_error("failed to create pipe");

    return std::make_pair((long long)reader, (long long)writer);
}
