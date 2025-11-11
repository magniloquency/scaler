#pragma once
#include <cstddef>
#include <memory>

struct Pipe;

class PipeReader {
public:
    struct Impl {
        virtual int read(void* buffer, size_t size) = 0;
        virtual const void* handle() const noexcept = 0;
        virtual bool valid() const noexcept         = 0;
        virtual void close()                        = 0;
        virtual ~Impl()                             = default;
    };

    PipeReader(std::unique_ptr<Impl> impl);
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

    // returns the native handle for this pipe reader
    // on linux, this is a pointer to the file descriptor
    // on windows, this is the HANDLE
    const void* handle() const noexcept;

private:
    std::unique_ptr<Impl> _impl;
    friend struct Pipe;
};

class PipeWriter {
public:
    struct Impl {
        virtual int write(const void* data, size_t size) = 0;
        virtual bool valid() const noexcept              = 0;
        virtual void close()                             = 0;
        virtual ~Impl()                                  = default;
    };

    PipeWriter(std::unique_ptr<Impl> impl);
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
    std::unique_ptr<Impl> _impl;
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
};

std::pair<PipeReader, PipeWriter> create_pipe();
