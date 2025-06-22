#pragma once

// C++
#include <cstdint>  // uint64_t
#include <functional>

// First-party
#include "scaler/io/ymq/epoll_context.h"

struct Timestamp;
class EventManager;

template <class EventLoopBackend = EpollContext>
struct EventLoop {
    using Function   = std::function<void()>;  // TBD
    using Identifier = int;                    // TBD
    void loop() { eventLoopBackend.loop(); }
    void stop();

    void executeNow(Function func) { eventLoopBackend.executeNow(std::move(func)); }
    void executeLater(Function func) { eventLoopBackend.executeLater(std::move(func)); }

    Identifier executeAt(Timestamp timestamp, Function func) {
        return eventLoopBackend.executeAt(timestamp, std::move(func));
    }
    void cancelExecution(Identifier identifier) { eventLoopBackend.cancelExecution(identifier); }

    void registerCallbackBeforeLoop(EventManager*);

    void registerEventManager(EventManager& em) { eventLoopBackend.registerEventManager(em); }

    void addFdToLoop(int fd, uint64_t events, EventManager* manager) {
        eventLoopBackend.addFdToLoop(fd, events, manager);
    }

    void removeFdFromLoop(int fd) { eventLoopBackend.removeFdFromLoop(fd); }

    void runAfterEachLoop(Function func) { eventLoopBackend.runAfterEachLoop(std::move(func)); };

    EventLoopBackend eventLoopBackend;
};
