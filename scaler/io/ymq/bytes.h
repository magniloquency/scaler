#pragma once

// C
#include <string.h>  // memcmp

#include <algorithm>
#include <compare>
#include <cstddef>
#include <cstdint>
#include <cstring>

// C++
#include <string>

// First-party
#include "scaler/io/ymq/common.h"
#include "scaler/io/ymq/typedefs.h"

struct Bytes {
    uint8_t* data;
    size_t len;
    Ownership tag;

    void free() {
        if (tag != Owned)
            return;

        if (is_empty())
            return;

        delete[] data;
        this->data = NULL;
    }

    // move-only
    // TODO: make copyable
    Bytes(uint8_t* data, size_t len, Ownership tag): data(data), len(len), tag(tag) {}
    Bytes(const Bytes&)            = delete;
    Bytes& operator=(const Bytes&) = delete;
    Bytes(Bytes&& other) noexcept: data(other.data), len(other.len), tag(other.tag) {
        other.data = NULL;
        other.len  = 0;
    }

    friend std::strong_ordering operator<=>(const Bytes& x, const Bytes& y) {
        return std::lexicographical_compare_three_way(x.data, x.data + x.len, y.data, y.data + y.len);
    }

    Bytes& operator=(Bytes&& other) noexcept {
        if (this != &other) {
            this->free();  // free current data

            data = other.data;
            len  = other.len;
            tag  = other.tag;

            other.data = NULL;
            other.len  = 0;
        }
        return *this;
    }

    ~Bytes() { this->free(); }

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

    static Bytes alloc(size_t m_len) {
        if (m_len == 0)
            return empty();

        return Bytes {new uint8_t[m_len], m_len, Owned};
    }

    static Bytes empty() { return Bytes {(uint8_t*)nullptr, 0, Owned}; }

    static Bytes copy(const uint8_t* m_data, size_t m_len) {
        if (m_len == 0)
            return empty();

        return Bytes {datadup(m_data, m_len), m_len, Owned};
    }

    static Bytes clone(const Bytes& bytes) {
        if (bytes.is_empty())
            panic("tried to clone empty bytes");

        return Bytes {datadup(bytes.data, bytes.len), bytes.len, Owned};
    }

    // static Bytes from_buffer(Buffer& buffer) { return buffer.into_bytes(); }

    // // consume this Bytes and return a Buffer object
    // Buffer into_buffer() {
    //     if (tag != Owned) {
    //         // if the m_data is borrowed, we need to copy it
    //         auto new_m_data = new uint8_t[m_len];
    //         std::memcpy(new_m_data, m_data, m_len);
    //         m_data = new_m_data;
    //         tag    = Owned;  // now we own the m_data
    //     }

    //     Buffer buffer {m_data, m_len, m_len};
    //     m_data = NULL;  // prevent double free
    //     m_len  = 0;     // prevent double free
    //     return buffer;
    // }

    // Do not remove this
    std::pair<char*, size_t> release() {
        std::pair<char*, size_t> res {(char*)data, len};
        data = nullptr;
        len  = 0;
        return res;
    }

    friend class Buffer;
};
