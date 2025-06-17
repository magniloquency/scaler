#pragma once

#include <sys/socket.h>

#include <functional>
#include <memory>
#include <optional>
#include <queue>

#include "scaler/io/ymq/common.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection.h"

class EventLoopThread;
class EventManager;
class IOSocket;

enum class IOProgress { Header, Payload };

struct IOOperation {
    IOProgress progress;
    uint8_t header[4], *payload;
    size_t cursor = 0;

    uint32_t len() const {
        uint32_t len;
        deserialize_u32(header, &len);
        return len;
    }

    bool is_stage_complete() const {
        if (progress == IOProgress::Header)
            return cursor == 4;

        if (progress == IOProgress::Payload)
            return cursor == len();

        unreachable();
    }

    bool is_complete() const { return progress == IOProgress::Payload && cursor == len(); }
    bool is_empty() const { return progress == IOProgress::Header && cursor == 0; }

    void reset() {
        this->progress = IOProgress::Header;
        this->cursor   = 0;
    }
};

struct WriteRequest {
    Bytes payload;
    std::function<void()> callback;
};

enum class ConnectionStage { IdentityExchange, Stable };

class MessageConnectionTCP: public MessageConnection {
    sockaddr_storage _remoteAddress;
    std::shared_ptr<IOSocket> _socket;

    ConnectionStage _stage = ConnectionStage::IdentityExchange;
    std::optional<Bytes> _remoteIdentity;

    std::queue<WriteRequest> _writeQueue;
    std::queue<std::function<void(Bytes)>> _readQueue;
    std::queue<Bytes> _receivedMessages;

    IOOperation _readOp;
    IOOperation _writeOp;

    std::unique_ptr<EventManager> _eventManager;

    void onEvent(FileDescriptor& fd, Events events);

    void onRead(FileDescriptor& fd);
    void onWrite(FileDescriptor& fd);
    void onClose(FileDescriptor& fd) { printf("onClose\n"); };
    void onError(FileDescriptor& fd) {};

    void onReadMessage();
    void onWroteMessage();

public:
    ~MessageConnectionTCP();
    MessageConnectionTCP(std::shared_ptr<IOSocket> ioSocket, FileDescriptor fd, sockaddr_storage remoteAddress);

    void send(Bytes data, std::function<void()> k);
    void recv(std::function<void(Bytes)> k);

    void onCreated();

    friend class IOSocket;
};
