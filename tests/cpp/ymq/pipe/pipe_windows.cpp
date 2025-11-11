#include <windows.h>

#include "tests/cpp/ymq/common/utils.h"
#include "tests/cpp/ymq/pipe/pipe.h"

struct PipeReaderImpl: PipeReader::Impl {
    HANDLE h = INVALID_HANDLE_VALUE;

    int read(void* buffer, size_t size) override
    {
        DWORD bytesRead = 0;
        if (!ReadFile(h, buffer, (DWORD)size, &bytesRead, nullptr))
            raise_system_error("failed to read");
        return bytesRead;
    }

    void close() override
    {
        if (h != INVALID_HANDLE_VALUE)
            CloseHandle(h);
        h = INVALID_HANDLE_VALUE;
    }

    void* handle() override { return this->h; }

    bool valid() const noexcept override { return h != INVALID_HANDLE_VALUE; }
    ~PipeReaderImpl() override { close(); }
};

struct PipeWriterImpl: public PipeWriter::Impl {
    HANDLE h = INVALID_HANDLE_VALUE;

    int write(const void* data, size_t size) override
    {
        DWORD bytesWritten = 0;
        if (!WriteFile(h, data, (DWORD)size, &bytesWritten, nullptr))
            raise_system_error("failed to write to pipe");
        return bytesWritten;
    }

    void close() override
    {
        if (h != INVALID_HANDLE_VALUE) {
            CloseHandle(h);
            h = INVALID_HANDLE_VALUE;
        }
    }

    bool valid() const noexcept override { return h != INVALID_HANDLE_VALUE; }
    ~PipeWriterImpl() override { close(); }
};

std::pair<PipeReader, PipeWriter> create_pipe()
{
    SECURITY_ATTRIBUTES sa {};
    sa.nLength        = sizeof(sa);
    sa.bInheritHandle = TRUE;

    auto reader_impl = std::make_unique<PipeReaderImpl>();
    auto writer_impl = std::make_unique<PipeWriterImpl>();

    if (!CreatePipe(&reader_impl->h, &writer_impl->h, &sa, 0))
        raise_system_error("failed to create pipe");

    PipeReader reader(std::move(reader_impl));
    PipeWriter writer(std::move(writer_impl));

    return std::make_pair(std::move(reader), std::move(writer));
}
