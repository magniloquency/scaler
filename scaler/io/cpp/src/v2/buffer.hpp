#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <expected>
#include <functional>

#include "bytes.hpp"
#include "common.hpp"
#include "file_descriptor.hpp"

class Buffer {
    uint8_t* _data;
    size_t _capacity, _size;

    // a pointer to the end of the buffer where new _data can be written or read from
    uint8_t* end() { return _data + _size; }

    Buffer(uint8_t* data, size_t capacity, size_t size): _data(data), _capacity(capacity), _size(size) {
        if (_data == nullptr || _capacity == 0) {
            panic("Buffer created with null _data or zero _capacity");
        }
    }

public:
    Buffer(): _data(nullptr), _capacity(0), _size(0) {
        // default constructor for empty buffer
    }
    Buffer(size_t capacity): _data(new uint8_t[capacity]), _capacity(capacity), _size(0) {}

    // move-only type
    Buffer(const Buffer&)            = delete;
    Buffer& operator=(const Buffer&) = delete;
    Buffer(Buffer&& other) noexcept: _data(other._data), _capacity(other._capacity), _size(other._size) {
        other._data     = nullptr;
        other._capacity = 0;
        other._size     = 0;
    }
    Buffer& operator=(Buffer&& other) noexcept {
        if (this != &other) {
            delete[] _data;  // free current _data
            _data     = other._data;
            _capacity = other._capacity;
            _size     = other._size;

            other._data     = nullptr;
            other._capacity = 0;
            other._size     = 0;
        }
        return *this;
    }

    ~Buffer() {
        if (_data != nullptr)
            delete[] _data;  // free the buffer if it was allocated
        _data = nullptr;     // prevent double free
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
            _size += *result;
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

    size_t remaining() const { return _capacity - _size; }

    size_t capacity() const { return _capacity; }

    size_t size() const { return _size; }

    bool is_empty() const { return _size == 0; }

    bool is_full() const { return _size == _capacity; }

    // consume this buffer and return a Bytes object
    Bytes into_bytes() {
        auto bytes = Bytes(_data, _size, Bytes::Owned);
        _data      = nullptr;  // prevent deletion in destructor
        _size      = 0;
        _capacity  = 0;
        return bytes;
    }

    static Buffer from_bytes(Bytes& bytes) { return bytes.into_buffer(); }

    friend class Bytes;
};
