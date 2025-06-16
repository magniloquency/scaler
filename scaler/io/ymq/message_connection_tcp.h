#pragma once

#include <functional>
#include <memory>
#include <optional>
#include <queue>
#include <tuple>
#include <vector>

#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/message_connection.h"

class EventLoopThread;
class EventManager;

struct TcpWriteOperation {
    std::shared_ptr<std::vector<char>> _buf;
    size_t _cursor = 0;
    std::function<void()> _callbackAfterCompleteWrite;
};

struct TcpReadOperation {
    std::shared_ptr<std::vector<char>> _buf;
    size_t _cursor = 0;
    std::function<void()> _callbackAfterCompleteRead;
};

class MessageConnectionTCP: public MessageConnection {
    int _connFd;
    sockaddr _localAddr;
    sockaddr _remoteAddr;
    std::string _localIOSocketIdentity;
    std::optional<std::string> _remoteIOSocketIdentity;
    bool _sendLocalIdentity;

    std::queue<TcpWriteOperation> _writeOperations;
    std::queue<TcpReadOperation> _pendingReadOperations;
    std::queue<std::vector<char>> _receivedMessages;

    std::vector<char> _recvBuf;
    size_t _readCursor = 0;

    std::shared_ptr<EventLoopThread> _eventLoopThread;
    std::unique_ptr<EventManager> _eventManager;

    void onRead();
    void onWrite();
    void onClose() { printf("onClose\n"); };
    void onError() {};

public:
    ~MessageConnectionTCP();
    MessageConnectionTCP(
        std::shared_ptr<EventLoopThread> eventLoopThread,
        int connFd,
        sockaddr localAddr,
        sockaddr remoteAddr,
        std::string localIOSocketIdentity);

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

    void sendMessage(std::shared_ptr<std::vector<char>> msg);
    void recvMessage(std::shared_ptr<std::vector<char>> msg);

    void recv(std::vector<char>& buf) {}

    void onCreated();
};
