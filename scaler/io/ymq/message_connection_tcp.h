#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <queue>
#include <vector>

#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/event_loop.h"
#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection.h"

class EventLoopThread;
class EventManager;

struct TcpWriteOperation {
    using SendMessageCallback = Configuration::SendMessageCallback;
    std::shared_ptr<std::vector<char>> _buf;
    size_t _cursor = 0;
    SendMessageCallback _callbackAfterCompleteWrite;
};

struct TcpReadOperation {
    using RecvMessageCallback = Configuration::RecvMessageCallback;
    std::shared_ptr<std::vector<char>> _buf;
    size_t _cursor = 0;
    RecvMessageCallback _callbackAfterCompleteRead;
};

class MessageConnectionTCP: public MessageConnection {
    // TODO: Make the connfd private again
public:
    int _connFd;  // Maybe just -1
    sockaddr _localAddr;
    sockaddr _remoteAddr;  // TODO: make it an optional
    std::string _localIOSocketIdentity;
    std::optional<std::string> _remoteIOSocketIdentity;
    bool _sendLocalIdentity;
    bool _responsibleForRetry;
    using SendMessageCallback = Configuration::SendMessageCallback;
    using RecvMessageCallback = Configuration::RecvMessageCallback;

public:
    std::queue<TcpWriteOperation> _writeOperations;
    std::shared_ptr<std::queue<TcpReadOperation>> _pendingReadOperations;
    std::queue<std::vector<char>> _receivedMessages;

    std::shared_ptr<EventLoopThread> _eventLoopThread;
    std::unique_ptr<EventManager> _eventManager;

    void onRead();
    void onWrite();
    void onClose();

    void onError() { printf("onError (for debug don't remove)\n"); };

public:
    ~MessageConnectionTCP();
    MessageConnectionTCP(
        std::shared_ptr<EventLoopThread> eventLoopThread,
        int connFd,
        sockaddr localAddr,
        sockaddr remoteAddr,
        std::string localIOSocketIdentity,
        bool responsibleForRetry,
        std::shared_ptr<std::queue<TcpReadOperation>> _pendingReadOperations);

    void send(Bytes data, SendMessageContinuation k) { todo(); }
    void recv(RecvMessageContinuation k) { todo(); }

    // NODO: Think about writeOps and readOps in general
    void send(std::shared_ptr<std::vector<char>> msg) {
        // if (!_writeOps.size()) {
        //     int n = write(_connFd, msg->data(), msg->size());
        // } else {
        //     TcpWriteOperation writeOp;
        //     // writeOp._callback = [msg] {write() }
        // }
    }

    void sendMessage(std::shared_ptr<std::vector<char>> msg, SendMessageCallback callback);
    bool recvMessage();

    void recv(std::vector<char>& buf) {}

    void onCreated();
};
