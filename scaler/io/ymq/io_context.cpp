
#include "scaler/io/ymq/io_context.h"

#include <algorithm>  // std::ranges::generate
#include <cassert>    // assert
#include <memory>     // std::make_shared

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/typedefs.h"

IOContext::IOContext(size_t threadCount): _threads(threadCount) {
    assert(threadCount > 0);
    std::ranges::generate(_threads, std::make_shared<EventLoopThread>);
}

// NOTE: this is not thread safe, technically race condition can happen. But it's highly unlikely.
std::shared_ptr<IOSocket> IOContext::createIOSocket(
    Identity identity, IOSocketType socketType, std::function<void()> callback) {
    static size_t threadsRoundRobin = 0;
    auto& thread                    = _threads[threadsRoundRobin];
    ++threadsRoundRobin %= _threads.size();
    return thread->createIOSocket(std::move(identity), socketType, std::move(callback));
}

bool IOContext::removeIOSocket(std::shared_ptr<IOSocket>& socket) {
    auto* rawSocket = socket.get();
    socket.reset();

    rawSocket->_eventLoopThread->_eventLoop.executeNow([rawSocket] {
        rawSocket->_eventLoopThread->_eventLoop.executeLater(
            [rawSocket] { rawSocket->_eventLoopThread->removeIOSocket(rawSocket); });
    });
    return true;
}
