#pragma once
#include <cstddef>
#include <memory>

struct Pipe;

class PipeReader {
public:
    PipeReader();
    ~PipeReader();

    // Move-only
    PipeReader(PipeReader&&) noexcept;
    PipeReader& operator=(PipeReader&&) noexcept;
    PipeReader(const PipeReader&)            = delete;
    PipeReader& operator=(const PipeReader&) = delete;

    int read(void* buffer, size_t size);
    void read_exact(void* buffer, size_t size);
    void close();

    bool valid() const noexcept;

#ifdef __linux__
    int fd() const noexcept;
#endif  // __linux__

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
    friend struct Pipe;
};

class PipeWriter {
public:
    PipeWriter();
    ~PipeWriter();

    // Move-only
    PipeWriter(PipeWriter&&) noexcept;
    PipeWriter& operator=(PipeWriter&&) noexcept;
    PipeWriter(const PipeWriter&)            = delete;
    PipeWriter& operator=(const PipeWriter&) = delete;

    int write(const void* data, size_t size);
    void write_all(const void* data, size_t size);
    void close();

    bool valid() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
    friend struct Pipe;
};

struct Pipe {
public:
    Pipe();
    ~Pipe();

    // Move-only
    Pipe(Pipe&&) noexcept;
    Pipe& operator=(Pipe&&) noexcept;
    Pipe(const Pipe&)            = delete;
    Pipe& operator=(const Pipe&) = delete;

    PipeReader reader;
    PipeWriter writer;

private:
    struct Impl;
};
