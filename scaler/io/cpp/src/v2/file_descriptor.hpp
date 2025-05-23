// System
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/timerfd.h>

// C
#include <unistd.h>

// C++
#include <cerrno>
#include <expected>
#include <optional>

class FileDescriptor {
    int fd;

    FileDescriptor(int fd): fd(fd) {}
    ~FileDescriptor() {
        close(fd);
        this->fd = -1;
    }

public:
    using Errno = int;

    static FileDescriptor socket(int domain, int type, int protocol) {
        int fd = ::socket(domain, type, protocol);
        if (fd < 0) {
            throw errno;
        }

        return {fd};
    }

    static FileDescriptor eventfd(int initval, int flags) {
        int fd = ::eventfd(initval, flags);
        if (fd < 0) {
            throw errno;
        }

        return {fd};
    }

    static FileDescriptor timerfd(int flags) {
        int fd = ::timerfd_create(CLOCK_MONOTONIC, flags);
        if (fd < 0) {
            throw errno;
        }

        return {fd};
    }

    [[nodiscard]] std::optional<Errno> accept(struct sockaddr* addr, socklen_t* addrlen) {
        if (::accept(fd, addr, addrlen) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }

    [[nodiscard]] std::optional<Errno> bind(const struct sockaddr* addr, socklen_t addrlen) {
        if (::bind(fd, addr, addrlen) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }

    [[nodiscard]] std::optional<Errno> eventfd_signal() {
        uint64_t u = 1;
        if (::eventfd_write(fd, u) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }

    [[nodiscard]] std::optional<Errno> eventfd_wait() {
        uint64_t u;
        if (::eventfd_read(fd, &u) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }

    [[nodiscard]] std::optional<Errno> timerfd_set(
        const struct itimerspec* new_value, struct itimerspec* old_value = nullptr) {
        if (::timerfd_settime(fd, 0, new_value, old_value) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }

    [[nodiscard]] std::optional<Errno> timerfd_wait() {
        uint64_t u;
        if (::read(fd, &u, sizeof(u)) < 0) {
            return errno;
        } else {
            return std::nullopt;
        }
    }
};
