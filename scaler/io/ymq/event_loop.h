#pragma once

// C++
#include <functional>

// First-party
#include "scaler/io/ymq/common.h"
#include "scaler/io/ymq/epoll_context.h"

struct Timestamp;
class EventManager;

template <typename EventLoopBackend = EpollContext>
struct EventLoop {
    using Function   = std::function<void()>;  // TBD
    using Identifier = int;                    // TBD
    void loop() { eventLoopBackend.loop(); }
    void stop();

    void executeNow(Function func) { eventLoopBackend.executeNow(std::move(func)); }
    void executeLater(Function func, Identifier identifier) {
        eventLoopBackend.executeLater(std::move(func), identifier);
    }
    void executeAt(Timestamp timestamp, Function func) { eventLoopBackend.executeAt(timestamp, std::move(func)); }
    void cancelExecution(Identifier identifier);

    void registerEventManager(EventManager& em) { eventLoopBackend.registerEventManager(em); }
    void removeEventManager(EventManager& em) { eventLoopBackend.removeEventManager(em); }

    void runAfterEachLoop(Function func) { 
        // eventLoopBackend.runAfterEachLoop(std::move(func));
        todo();
     };

    EventLoopBackend eventLoopBackend;
};
