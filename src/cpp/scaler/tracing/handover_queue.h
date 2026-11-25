#pragma once

#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>

namespace scaler {
namespace tracing {

// A bounded queue that its own thread drains, handing each record to `consume`: the producer never runs it.
template <typename Record>
class HandoverQueue {
public:
    HandoverQueue(size_t maxSize, std::function<void(Record&)> consume)
        : _maxSize {maxSize}, _consume {std::move(consume)}, _thread {&HandoverQueue::run, this}
    {
    }

    ~HandoverQueue()
    {
        stop();
    }

    HandoverQueue(const HandoverQueue&)            = delete;
    HandoverQueue& operator=(const HandoverQueue&) = delete;
    HandoverQueue(HandoverQueue&&)                 = delete;
    HandoverQueue& operator=(HandoverQueue&&)      = delete;

    // False, dropping the record, when `maxSize` records already wait or the queue is stopped.
    bool push(Record&& record)
    {
        std::lock_guard lock {_mutex};
        if (_stopping || _queue.size() >= _maxSize) {
            return false;
        }
        _queue.push_back(std::move(record));
        ++_pushedCount;
        _recordPushed.notify_one();
        return true;
    }

    // True once every record pushed before the call is consumed, false when `deadline` passes first.
    bool waitUntilConsumed(std::chrono::steady_clock::time_point deadline)
    {
        std::unique_lock lock {_mutex};
        const uint64_t target = _pushedCount;
        return _recordsConsumed.wait_until(lock, deadline, [this, target] { return _consumedCount >= target; });
    }

    // Consumes every queued record, then stops the thread; later pushes are dropped.
    void stop()
    {
        {
            std::lock_guard lock {_mutex};
            _stopping = true;
            _recordPushed.notify_one();
        }
        if (_thread.joinable()) {
            _thread.join();
        }
    }

private:
    const size_t _maxSize;
    const std::function<void(Record&)> _consume;

    std::mutex _mutex;
    std::condition_variable _recordPushed;
    std::condition_variable _recordsConsumed;
    std::deque<Record> _queue;
    uint64_t _pushedCount {0};
    uint64_t _consumedCount {0};
    bool _stopping {false};

    std::thread _thread;  // last: it starts in the constructor, once every other field is ready

    void run()
    {
        std::unique_lock lock {_mutex};
        while (true) {
            _recordPushed.wait(lock, [this] { return !_queue.empty() || _stopping; });
            if (_queue.empty()) {
                return;
            }

            std::deque<Record> records {};
            records.swap(_queue);
            lock.unlock();

            for (auto& record: records) {
                _consume(record);
            }

            lock.lock();
            _consumedCount += records.size();
            _recordsConsumed.notify_all();
        }
    }
};

}  // namespace tracing
}  // namespace scaler
