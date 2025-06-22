
#include "scaler/io/ymq/timed_queue.h"

#include <sys/epoll.h>

#include <cassert>

#include "scaler/io/ymq/timestamp.h"

TimedQueue::TimedQueue(): timer_fd(createTimerfd()), _currentId {} {
    assert(timer_fd);
}

TimedQueue::Identifier TimedQueue::push(Timestamp timestamp, callback_t cb) {
    printf("%s\n", __PRETTY_FUNCTION__);
    auto ts = convertToItimerspec(timestamp);
    if (pq.empty() || timestamp < std::get<0>(pq.top())) {
        int ret = timerfd_settime(timer_fd, 0, &ts, nullptr);
        assert(ret == 0);
    }
    pq.push({timestamp, cb, _currentId});
    return _currentId++;
}

void TimedQueue::onCreated() {}
