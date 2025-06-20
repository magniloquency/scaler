#pragma once

#include <sys/timerfd.h>
#include <unistd.h>

#include <cassert>
#include <cstdio>
#include <functional>
#include <iostream>
#include <queue>

#include "scaler/io/ymq/timestamp.h"

inline int createTimerfd() {
    int timerfd = ::timerfd_create(CLOCK_MONOTONIC, TFD_NONBLOCK | TFD_CLOEXEC);
    if (timerfd < 0) {
        exit(1);
    }
    return timerfd;
}

// TODO: HANDLE ERRS
struct TimedQueue {
    int timer_fd;
    using callback_t = std::function<void()>;
    using timed_fn   = std::pair<Timestamp, callback_t>;
    using cmp        = decltype([](const auto& x, const auto& y) { return x.first < y.first; });

    std::priority_queue<timed_fn, std::vector<timed_fn>, cmp> pq;

    TimedQueue();

    void push(Timestamp timestamp, callback_t cb);

    void onRead() {
        uint64_t numItems;
        ssize_t n = read(timer_fd, &numItems, sizeof numItems);
        if (n != sizeof numItems) {
            assert(false);
            // Handle read error or spurious wakeup
            return;
        }

        Timestamp now;
        while (pq.size()) {
            if (pq.top().first < now) {
                auto [ts, cb] = std::move(pq.top());
                pq.pop();
                cb();
            } else
                break;
        }

        if (!pq.empty()) {
            auto nextTs = pq.top().first;
            auto ts     = convertToItimerspec(nextTs);
            int ret     = timerfd_settime(timer_fd, 0, &ts, nullptr);
            if (ret == -1) {
                assert(false);
                // handle error
            }
        }
    }

    void onCreated();

    int timingFd() const { return timer_fd; }
};
