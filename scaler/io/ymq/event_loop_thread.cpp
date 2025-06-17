#include <cassert>
#include <memory>

#include "scaler/io/ymq/common.h"
#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/io_socket.h"

void EventLoopThread::addIOSocket(std::shared_ptr<IOSocket> socket) {
    _identityToIOSocket.emplace(socket->identity(), socket);

    todo();
}

// TODO: Think about non null pointer
void EventLoopThread::removeIOSocket(std::shared_ptr<IOSocket> socket) {
    // TODO: Something happen with the running thread
    _identityToIOSocket.erase(socket->identity());

    todo();
}

void EventLoopThread::registerEventManager(EventManager& em) {
    _eventLoop->registerEventManager(em);
}
void EventLoopThread::removeEventManager(EventManager& em) {
    // todo
}

// #include "scaler/io/ymq/event_manager.h"
// #include "scaler/io/ymq/io_socket.h"

// std::shared_ptr<IOSocket> EventLoopThread::createIOSocket(std::string identity, IOSocketType socketType) {
//     if (thread.get_id() == std::thread::id()) {
//         thread = std::jthread([this](std::stop_token token) {
//             while (!token.stop_requested()) {
//                 this->_eventLoop.loop();
//             }
//         });
//     }

//     auto [iterator, inserted] =
//         _identityToIOSocket.try_emplace(identity, std::make_shared<IOSocket>(shared_from_this(), identity, socketType));
//     assert(inserted);
//     auto ptr = iterator->second;

//     _eventLoop.executeNow([ptr] { ptr->onCreated(); });
//     return ptr;
// }

// // TODO: Something happen with the running thread; Think about non null pointer.
// void EventLoopThread::removeIOSocket(IOSocket* target) {
//     _identityToIOSocket.erase(target->identity());
// }
