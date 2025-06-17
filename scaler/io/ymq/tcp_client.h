#pragma once

// C++
#include <sys/socket.h>

#include <functional>
#include <memory>

// First-party
#include "scaler/io/ymq/file_descriptor.h"

class EventLoopThread;
class EventManager;

class TcpClient {
    std::shared_ptr<EventLoopThread> _eventLoopThread; /* shared ownership */
    std::unique_ptr<EventManager> _eventManager;
    int _connFd;
    std::string _localIOSocketIdentity;
    sockaddr _remoteAddr;

    // Implementation defined method. connect(3) should happen here.
    // This function will call user defined onConnectReturn()
    // It will handle error it can handle. If it is unreasonable to
    // handle the error here, pass it to onConnectReturn()
    void onRead();
    void onWrite();
    void onClose() {}
    void onError() {}
    size_t _retryTimes = 0;

public:
    bool _connected;

    TcpClient(const TcpClient&)            = delete;
    TcpClient& operator=(const TcpClient&) = delete;
    TcpClient(std::shared_ptr<EventLoopThread> eventLoopThread, std::string localIOSocketIdentity, sockaddr remoteAddr);

    using ConnectReturnCallback = std::function<void(FileDescriptor, sockaddr, int)>;
    ConnectReturnCallback onConnectReturn;

    void onCreated();

    void retry(/* Arguments */);
    ~TcpClient();
};
