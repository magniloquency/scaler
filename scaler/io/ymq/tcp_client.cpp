#include "scaler/io/ymq/tcp_client.h"

#include <netinet/in.h>
#include <sys/socket.h>

#include <cerrno>
#include <chrono>
#include <functional>
#include <memory>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/timestamp.h"

void TcpClient::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    int sockfd    = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK, 0);
    this->_connFd = sockfd;
    int ret       = connect(sockfd, (sockaddr*)&_remoteAddr, sizeof(_remoteAddr));

    int passedBackValue = 0;
    if (ret < 0) {
        if (errno != EINPROGRESS) {
            perror("connect");
            close(sockfd);
            passedBackValue = errno;
        } else {
            // TODO: Think about the lifetime of _eventManager.
            printf("Connecting (EINPROGRESS), adding fd to loop\n");
            _eventLoopThread->_eventLoop.addFdToLoop(sockfd, EPOLLOUT | EPOLLET, this->_eventManager.get());
            passedBackValue = 0;
        }
    } else {
        printf("client SUCCESS\n");
        std::string id = this->_localIOSocketIdentity;
        auto& sock     = this->_eventLoopThread->_identityToIOSocket.at(id);
        // FIXME: the first _addr is not real
        sock->_unconnectedConnection.push_back(
            std::make_unique<MessageConnectionTCP>(
                _eventLoopThread, sockfd, _remoteAddr, _remoteAddr, id, true, sock->_pendingReadOperations));
        sock->_unconnectedConnection.back()->onCreated();

        passedBackValue = 0;
    }

    if (_retryTimes == 0) {
        _onConnectReturn(passedBackValue);
        return;
    }

    if (passedBackValue < 0) {
        printf("SOMETHING REALLY BAD\n");
        exit(-1);
    }
}

TcpClient::TcpClient(
    std::shared_ptr<EventLoopThread> eventLoopThread,
    std::string localIOSocketIdentity,
    sockaddr remoteAddr,
    ConnectReturnCallback onConnectReturn)
    : _eventLoopThread(eventLoopThread)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _remoteAddr(std::move(remoteAddr))
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _connected(false)
    , _onConnectReturn(std::move(onConnectReturn))
    , _retryTimes {}
    , _retryIdentifier {} {
    _eventManager->onRead  = [this] { this->onRead(); };
    _eventManager->onWrite = [this] { this->onWrite(); };
    _eventManager->onClose = [this] { this->onClose(); };
    _eventManager->onError = [this] { this->onError(); };
    printf("%s\n", __PRETTY_FUNCTION__);
}

void TcpClient::onWrite() {
    printf("%s\n", __PRETTY_FUNCTION__);

    _eventLoopThread->_eventLoop.removeFdFromLoop(_connFd);

    int err {};
    socklen_t errLen {sizeof(err)};
    if (getsockopt(_connFd, SOL_SOCKET, SO_ERROR, &err, &errLen) < 0) {
        perror("getsockopt");
        exit(-1);
    }

    if (err != 0) {
        fprintf(stderr, "Connect failed: %s\n", strerror(err));
        fflush(stderr);
        retry();
        return;
    }

    sockaddr localAddr;
    socklen_t localAddrLen = sizeof(localAddr);
    if (getsockname(_connFd, &localAddr, &localAddrLen) < 0) {
        perror("getsockname");
        exit(-1);
        return;
    }

    std::string id = this->_localIOSocketIdentity;
    auto sock      = this->_eventLoopThread->_identityToIOSocket.at(id);

    sock->_unconnectedConnection.push_back(
        std::make_unique<MessageConnectionTCP>(
            _eventLoopThread,
            _connFd,
            localAddr,    // local bound address
            _remoteAddr,  // remote address (peer)
            id,
            true,
            sock->_pendingReadOperations));

    sock->_unconnectedConnection.back()->onCreated();

    _connFd    = 0;
    _connected = true;

    _eventLoopThread->_eventLoop.executeLater([sock] { sock->removeConnectedTcpClient(); });
}

void TcpClient::onRead() {
    printf("TcpClient::onRead()\n");
}

void TcpClient::retry() {
    if (_retryTimes > 5) {
        printf("_retryTimes > %lu, has reached maximum, no more retry now\n", _retryTimes);
        exit(1);
        return;
    }

    close(_connFd);
    _connFd = 0;

    Timestamp now;
    auto at = now.createTimestampByOffsetDuration(std::chrono::seconds(2 << _retryTimes++));
    std::cout << "TIMESTAMP IN RETRY: " << stringifyTimestamp(at) << std::endl;
    _retryIdentifier = _eventLoopThread->_eventLoop.executeAt(at, [this] { this->onCreated(); });
}

TcpClient::~TcpClient() {
    if (_connFd) {
        _eventLoopThread->_eventLoop.removeFdFromLoop(_connFd);
        close(_connFd);
    }
    if (_retryTimes > 0)
        _eventLoopThread->_eventLoop.cancelExecution(_retryIdentifier);
    printf("%s\n", __PRETTY_FUNCTION__);
}
