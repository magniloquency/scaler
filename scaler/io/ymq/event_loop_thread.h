#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <thread>

#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/event_loop.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/typedefs.h"

class IOSocket;
class EventManager;

template <typename EventLoopBackend>
class EventLoop;

class EventLoopThread: public std::enable_shared_from_this<EventLoopThread> {
    using PollingContext = Configuration::PollingContext;
    using Identity       = Configuration::Identity;
    std::jthread _thread;
    std::map<Identity, std::shared_ptr<IOSocket>> _identityToIOSocket;

public:
    EventLoop<PollingContext>* _eventLoop;
    void addIOSocket(std::shared_ptr<IOSocket>);
    void removeIOSocket(std::shared_ptr<IOSocket>);
    void registerEventManager(EventManager& em);
    void removeEventManager(EventManager& em);
    std::shared_ptr<IOSocket> getIOSocketByIdentity(size_t identity);
    std::jthread thread;

public:
    EventLoopThread(const EventLoopThread&)            = delete;
    EventLoopThread& operator=(const EventLoopThread&) = delete;
    EventLoopThread()                                  = default;
};
