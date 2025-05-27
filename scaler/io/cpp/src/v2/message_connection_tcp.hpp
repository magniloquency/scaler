#pragma once

#include <optional>
#include <tuple>

#include "file_descriptor.hpp"
#include "io_operation.hpp"
#include "message_connection.hpp"

class MessageConnectionTCP: public MessageConnection {
    FileDescriptor fd;

    MessageIoOperation read_op, write_op;

public:
    void send(Bytes data, SendMessageContinuation k) {}
    void recv(RecvMessageContinuation k) {}
};

int main() {
    for (;;) {
        int n = epoll_wait(event);

        event->onEvent();
    }
}

void onEvent() {
    co_await socket.read(...); // <-- does this block the epoll thread???
    // thought: fundamentally: co_await cannot happen on the thread doing the io work
}
