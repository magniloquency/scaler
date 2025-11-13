#pragma once
#include <cstddef>
#include <memory>

struct Pipe;

class PipeReader {
public:
    PipeReader(long long fd);
    ~PipeReader();

    // Move-only
    PipeReader(PipeReader&&) noexcept;
    PipeReader& operator=(PipeReader&&) noexcept;
    PipeReader(const PipeReader&)            = delete;
    PipeReader& operator=(const PipeReader&) = delete;

    // read exactly `size` bytes
    void read_exact(void* buffer, size_t size);

    // returns the native handle for this pipe reader
    // on linux, this is a pointer to the file descriptor
    // on windows, this is the HANDLE
    const long long fd() const noexcept;

private:
    // the native handle for this pipe reader
    // on Linux, this is a file descriptor
    // on Windows, this is a HANDLE
    long long _fd;

    // read up to `size` bytes
    int read(void* buffer, size_t size);
};

class PipeWriter {
public:
    PipeWriter(long long fd);
    ~PipeWriter();

    // Move-only
    PipeWriter(PipeWriter&&) noexcept;
    PipeWriter& operator=(PipeWriter&&) noexcept;
    PipeWriter(const PipeWriter&)            = delete;
    PipeWriter& operator=(const PipeWriter&) = delete;

    // write `size` bytes
    void write_all(const void* data, size_t size);

private:
    // the native handle for this pipe reader
    // on Linux, this is a file descriptor
    // on Windows, this is a HANDLE
    long long _fd;

    // write up to `size` bytes
    int write(const void* buffer, size_t size);
};

struct Pipe {
public:
    Pipe();
    ~Pipe() = default;

    // Move-only
    Pipe(Pipe&&) noexcept;
    Pipe& operator=(Pipe&&) noexcept;
    Pipe(const Pipe&)            = delete;
    Pipe& operator=(const Pipe&) = delete;

    PipeReader reader;
    PipeWriter writer;
};

// create platform-specific pipe handles
// the first handle is read, the second handle is write
std::pair<long long, long long> create_pipe();
