#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <expected>
#include <functional>
#include <vector>

#include "bytes.hpp"
#include "common.hpp"
#include "file_descriptor.hpp"

class Buffer {
    uint8_t* data;
    size_t capacity, size;

    // a pointer to the end of the buffer where new data can be written or read from
    uint8_t* end() { return data + size; }

public:
    Buffer(size_t capacity): data(new uint8_t[capacity]), capacity(capacity), size(0) {}

    // move-only type
    Buffer(const Buffer&)            = delete;
    Buffer& operator=(const Buffer&) = delete;
    Buffer(Buffer&& other) noexcept: data(other.data), capacity(other.capacity), size(other.size) {
        other.data     = nullptr;
        other.capacity = 0;
        other.size     = 0;
    }
    Buffer& operator=(Buffer&& other) noexcept {
        if (this != &other) {
            delete[] data;  // free current data
            data     = other.data;
            capacity = other.capacity;
            size     = other.size;

            other.data     = nullptr;
            other.capacity = 0;
            other.size     = 0;
        }
        return *this;
    }

    ~Buffer() {
        if (data != nullptr)
            delete[] data;  // free the buffer if it was allocated
        data = nullptr;     // prevent double free
    }

    // consume the buffer
    // true -> ok
    // false -> not enough space in the buffer
    // E -> mutator error passthrough
    template <typename E>
    std::expected<bool, E> consume(
        std::function<std::expected<size_t, E>(uint8_t*, size_t)> const& consumer,
        std::optional<size_t> n = std::nullopt) {
        if (n && *n > remaining()) {
            return false;  // not enough space
        }

        auto result = consumer(end(), n.value_or(remaining());
        if (result) {
            size += *result;
            return true;  // consumer success
        } else {
            return std::unexpected {result.error()};  // consumer failed
        }
    }

    std::expected<bool, int> read_into(FileDescriptor& fd, std::optional<size_t> n = std::nullopt) {
        return consume<int>([&fd](uint8_t* buf, size_t n) { return fd.read(buf, n); }, n);
    }

    std::expected<bool, int> write_from(FileDescriptor& fd, std::optional<size_t> n = std::nullopt) {
        return consume<int>([&fd](uint8_t* buf, size_t n) { return fd.write(buf, n); }, n);
    }

    size_t remaining() const { return capacity - size; }

    size_t capacity() const { return capacity; }

    size_t size() const { return size; }

    bool is_empty() const { return size == 0; }

    bool is_full() const { return size == capacity; }

    // consume the buffer and return a Bytes object
    Bytes into_bytes() {
        auto bytes = Bytes(data, size, Bytes::Owned);
        data       = nullptr;  // prevent deletion in destructor
        size       = 0;
        capacity   = 0;
        return bytes;
    }
};
