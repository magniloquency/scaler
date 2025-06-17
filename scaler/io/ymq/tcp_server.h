#pragma once

// C++
#include <sys/socket.h>

#include <memory>

// First-party
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/io_socket.h"
// #include "event_loop_thread.hpp"
// #include "event_manager.hpp"

class EventLoopThread;
class EventManager;
class IOSocket;

// struct sockaddr *__restrict addr, socklen_t *__restrict addr_len

class TcpServer {
    std::shared_ptr<IOSocket> _socket;
    std::unique_ptr<EventManager> _eventManager;
    
    void onEvent(FileDescriptor &fd, Events events);

public:
    TcpServer(const TcpServer&)            = delete;
    TcpServer& operator=(const TcpServer&) = delete;

    TcpServer(std::shared_ptr<IOSocket> ioSocket);
    ~TcpServer();

    void onCreated();
};
