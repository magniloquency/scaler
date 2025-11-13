#include <utility>

#include "tests/cpp/ymq/pipe/pipe.h"

Pipe::Pipe(): reader(-1), writer(-1)
{
    std::pair<long long, long long> pair = create_pipe();
    this->reader                         = PipeReader(pair.first);
    this->writer                         = PipeWriter(pair.second);
}

Pipe::Pipe(Pipe&& other) noexcept: reader(-1), writer(-1)
{
    this->reader = std::move(other.reader);
    this->writer = std::move(other.writer);
}

Pipe& Pipe::operator=(Pipe&& other) noexcept
{
    this->reader = std::move(other.reader);
    this->writer = std::move(other.writer);
    return *this;
}
