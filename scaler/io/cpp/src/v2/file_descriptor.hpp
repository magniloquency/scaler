// System
#include <sys/eventfd.h>
#include <sys/socket.h>
#include <sys/timerfd.h>

// C
#include <unistd.h>

// C++
#include <cerrno>
#include <expected>

class FileDescriptor {
    int fd;

    explicit FileDescriptor(int fd): fd(fd) {}
    ~FileDescriptor() {
        close(fd);
        this->fd = -1;
    }

public:
    static FileDescriptor socket(int domain, int type, int protocol) {
        int fd = ::socket(domain, type, protocol);
        if (fd < 0) {
            throw errno;
        }

        return FileDescriptor(fd);
    }

    static FileDescriptor eventfd(int initval, int flags) {
        int fd = ::eventfd(initval, flags);
        if (fd < 0) {
            throw errno;
        }

        return FileDescriptor(fd);
    }

    static FileDescriptor timerfd(int flags) {
        int fd = ::timerfd_create(CLOCK_MONOTONIC, flags);
        if (fd < 0) {
            throw errno;
        }

        return FileDescriptor(fd);
    }

    int accept(struct sockaddr* addr, socklen_t* addrlen) {
        int new_fd = ::accept(fd, addr, addrlen);
        if (new_fd < 0) {
            throw errno;
        }

        return new_fd;
    }

    void bind(const struct sockaddr* addr, socklen_t addrlen) {
        if (::bind(fd, addr, addrlen) < 0) {
            throw errno;
        }
    }

    void efd_signal() {
        if (::eventfd_write(fd, 1) < 0) {
            throw errno;
        }
    }

    void efd_wait() {
        uint64_t u;
        if (::eventfd_read(fd, &u) < 0) {
            throw errno;
        }
    }

    void tfd_set(const struct itimerspec* new_value, struct itimerspec* old_value = nullptr) {
        if (::timerfd_settime(fd, 0, new_value, old_value) < 0) {
            throw errno;
        }
    }

    void tfd_wait() {
        uint64_t u;
        if (::read(fd, &u, sizeof(u)) < 0) {
            throw errno;
        }
    }
};
