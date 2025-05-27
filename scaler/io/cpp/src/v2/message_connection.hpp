#pragma once

#include <functional>

#include "bytes.hpp"

class MessageConnection {
    public:
    using SendMessageContinuation = std::function<void()>;
    using RecvMessageContinuation = std::function<void(Bytes)>;

    void send(Bytes data, SendMessageContinuation k);
    void recv(RecvMessageContinuation k);
};
