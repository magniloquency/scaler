#include <windows.h>

#include <system_error>

#include "pipe.h"

static std::error_code last_error()
{
    return std::error_code(GetLastError(), std::system_category());
}

struct PipeReader::Impl {
    HANDLE h = INVALID_HANDLE_VALUE;

    int read(void* buffer, size_t size)
    {
        DWORD bytesRead = 0;
        if (!ReadFile(h, buffer, (DWORD)size, &bytesRead, nullptr))
            throw std::system_error(last_error(), "failed to read");
        return bytesRead;
    }

    void close()
    {
        if (h != INVALID_HANDLE_VALUE) {
            CloseHandle(h);
            h = INVALID_HANDLE_VALUE;
        }
    }

    bool valid() const noexcept { return h != INVALID_HANDLE_VALUE; }
    ~Impl() { close(); }
};

struct PipeWriter::Impl {
    HANDLE h = INVALID_HANDLE_VALUE;

    int write(const void* data, size_t size)
    {
        DWORD bytesWritten = 0;
        if (!WriteFile(h, data, (DWORD)size, &bytesWritten, nullptr))
            throw std::system_error(last_error(), "failed to write to pipe");
        return bytesWritten;
    }

    void close()
    {
        if (h != INVALID_HANDLE_VALUE) {
            CloseHandle(h);
            h = INVALID_HANDLE_VALUE;
        }
    }

    bool valid() const noexcept { return h != INVALID_HANDLE_VALUE; }
    ~Impl() { close(); }
};

struct Pipe::Impl {
    static std::pair<PipeReader, PipeWriter> create()
    {
        Impl p;
        SECURITY_ATTRIBUTES sa {};
        sa.nLength        = sizeof(sa);
        sa.bInheritHandle = TRUE;

        PipeReader reader;
        PipeWriter writer;
        if (!CreatePipe(&reader.impl->h, &writer.impl->h, &sa, 0))
            throw std::system_error(last_error(), "failed to create pipe");

        return std::make_pair(std::move(reader), std::move(writer));
    }
};
