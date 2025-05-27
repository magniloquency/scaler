#pragma once

#include <arpa/inet.h>  // for htonl, ntohl

#include <functional>

#include "bytes.hpp"
#include "common.hpp"
#include "message.hpp"

class MessageIoOperation {
    enum class Progress { Header, Payload } progress;

    size_t cursor;
    uint8_t header[4];

    Buffer payload;

    MessageIoOperation(Progress progress, uint8_t* header, Buffer&& payload)
        : progress(progress), payload(std::move(payload)), cursor(0) {
        std::memcpy(this->header, header, HEADER_SIZE);
    }

public:
    MessageIoOperation(Message&& msg): progress(Progress::Header), cursor(0) {
        this->payload = Buffer::from_bytes(msg.payload);
        serialize_u32(htonl((uint32_t)payload.size()), header);
    }

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

    bool is_done() const { return progress == Progress::Payload && cursor == payload.size(); }
};
