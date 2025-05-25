#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

#include "buffer.hpp"
#include "common.hpp"

class Bytes {
    uint8_t* data;
    size_t len;

    enum Ownership { Owned, Borrowed } tag;

    Bytes(uint8_t* data, size_t len, Ownership tag): data(data), len(len), tag(tag) {
        if (tag == Owned && data == NULL)
            panic("tried to create owned bytes with NULL data");
    }

public:
    ~Bytes() {
        if (tag != Owned)
            return;

        if (is_empty())
            return;

        delete[] data;
        this->data = NULL;
    }

    bool operator==(const Bytes& other) const {
        if (len != other.len)
            return false;

        if (data == other.data)
            return true;

        return std::memcmp(data, other.data, len) == 0;
    }

    bool operator!() const { return is_empty(); }

    bool is_empty() const { return this->data == NULL; }

    // debugging utility
    std::string as_string() const {
        if (is_empty())
            return "[EMPTY]";

        return std::string((char*)data, len);
    }

    Bytes ref() { return Bytes {this->data, this->len, Borrowed}; }

    static Bytes alloc(size_t len) {
        if (len == 0)
            return empty();

        return Bytes {new uint8_t[len], len, Owned};
    }

    static Bytes empty() { return Bytes {NULL, 0, Owned}; }

    static Bytes copy(const uint8_t* data, size_t len) {
        if (len == 0)
            return empty();

        return Bytes {datadup(data, len), len, Owned};
    }

    static Bytes clone(const Bytes& bytes) {
        if (bytes.is_empty())
            panic("tried to clone empty bytes");

        return Bytes {datadup(bytes.data, bytes.len), bytes.len, Owned};
    }

    static Bytes from_buffer(Buffer& buffer) {
        return buffer.into_bytes();
    }

    friend class Buffer;
};
