#pragma once

// C++
#include <sys/epoll.h>

#include <concepts>
#include <cstdint>  // uint64_t
#include <functional>
#include <memory>

// First-party
#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/file_descriptor.h"

struct EventLoopThread;

// an io-facility-agnostic representation of event types
struct Events {
    bool readable : 1 = false;
    bool writable : 1 = false;

    static Events fromEpollEvents(uint32_t epollEvents) {
        return Events {
            .readable = (epollEvents & EPOLLIN) > 0,
            .writable = (epollEvents & EPOLLOUT) > 0,
        };
    }
};

// TODO: Add the _fd back
class EventManager {
    using Callback = std::function<void(FileDescriptor&, Events)>;

    std::shared_ptr<EventLoopThread> _eventLoopThread;
    FileDescriptor _fd;
    Callback _callback;

    // must happen on io thread
    void removeFromEventLoop();

public:
    EventManager(std::shared_ptr<EventLoopThread> thread, FileDescriptor fd, Callback callback)
        : _eventLoopThread(thread), _fd(std::move(fd)), _callback(std::move(callback)) {}

    ~EventManager() { removeFromEventLoop(); }

    // must happen on io thread
    void addToEventLoop();

    bool operator==(const EventManager& other) const { return this->_fd == other._fd; }

    void onEvent(Events events) { this->_callback(_fd, events); }

    friend class EpollContext;

    // void onEvents(uint64_t events) {
    //     if constexpr (std::same_as<Configuration::PollingContext, EpollContext>) {
    //         int realEvents = (int)events;
    //         if ((realEvents & EPOLLHUP) && !(realEvents & EPOLLIN)) {
    //             onClose();
    //         }
    //         if (realEvents & EPOLLERR) {
    //             onError();
    //         }
    //         if (realEvents & (EPOLLIN | EPOLLRDHUP)) {
    //             onRead();
    //         }
    //         if (realEvents & EPOLLOUT) {
    //             onWrite();
    //         }
    //     }
    // }

    // // User that registered them should have everything they need
    // // In the future, we might add more onXX() methods, for now these are all we need.
    // using OnEventCallback = std::function<void()>;
    // OnEventCallback onRead;
    // OnEventCallback onWrite;
    // OnEventCallback onClose;
    // OnEventCallback onError;
    // // EventManager(): _fd {} {}
    // EventManager(std::shared_ptr<EventLoopThread> eventLoopThread, FileDescriptor fd, Callback callback)
    //     : _eventLoopThread(eventLoopThread), _fd(fd), _callback(callback) {}
};
