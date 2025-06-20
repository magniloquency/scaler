
#include "scaler/io/ymq/timed_queue.h"

#include <sys/epoll.h>

#include <cassert>

#include "scaler/io/ymq/timestamp.h"

TimedQueue::TimedQueue(): timer_fd(createTimerfd()) {
    assert(timer_fd);
}

void TimedQueue::push(Timestamp timestamp, callback_t cb) {
    auto ts = convertToItimerspec(timestamp);
    if (pq.empty() || timestamp < pq.top().first) {
        int ret = timerfd_settime(timer_fd, 0, &ts, nullptr);
        assert(ret == 0);
    }

    pq.push({timestamp, cb});
}

void TimedQueue::onCreated() {}
