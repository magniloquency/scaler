
#include "scaler/io/ymq/message_connection_tcp.h"

#include <unistd.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>

#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"

MessageConnectionTCP::MessageConnectionTCP(
    std::shared_ptr<EventLoopThread> eventLoopThread,
    int connFd,
    sockaddr localAddr,
    sockaddr remoteAddr,
    std::string localIOSocketIdentity)
    : _eventLoopThread(eventLoopThread)
    , _eventManager(std::make_unique<EventManager>(_eventLoopThread))
    , _connFd(std::move(connFd))
    , _localAddr(localAddr)
    , _remoteAddr(remoteAddr)
    , _localIOSocketIdentity(std::move(localIOSocketIdentity))
    , _remoteIOSocketIdentity(std::nullopt)
    , _sendLocalIdentity(false) {
    _eventManager->onRead  = [this] { this->onRead(); };
    _eventManager->onWrite = [this] { this->onWrite(); };
    _eventManager->onClose = [this] { this->onClose(); };
    _eventManager->onError = [this] { this->onError(); };
}

void MessageConnectionTCP::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);
    this->_eventLoopThread->_eventLoop.addFdToLoop(_connFd, EPOLLIN | EPOLLOUT | EPOLLET, this->_eventManager.get());
}

void MessageConnectionTCP::onRead() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // TODO: do not assume the identity to be less than 128bytes
    if (!_remoteIOSocketIdentity) {
        // Other sizes are possible, but the size needs to be >= 8, in order for idBuf
        // to be aligned with 8 bytes boundary because of strict aliasing
        char idBuf[128] {};
        int n         = read(_connFd, &idBuf, 128);
        uint64_t size = *(uint64_t*)idBuf;
        char* first   = idBuf + sizeof(uint64_t);
        std::string remoteID(first, first + size);
        _remoteIOSocketIdentity.emplace(std::move(remoteID));
    }
    assert(_remoteIOSocketIdentity);
    printf("Got a remote socket, identity = %s\n", _remoteIOSocketIdentity->c_str());
}

void MessageConnectionTCP::onWrite() {
    printf("%s\n", __PRETTY_FUNCTION__);
    // TODO: do not assume the identity to be less than 128bytes
    if (!_sendLocalIdentity) {
        // Other sizes are possible, but the size needs to be >= 8, in order for idBuf
        // to be aligned with 8 bytes boundary because of strict aliasing
        char idBuf[128] {};
        *(uint64_t*)idBuf  = _localIOSocketIdentity.size();
        auto identityBegin = idBuf + sizeof(uint64_t);
        auto [_, last]     = std::ranges::copy(_localIOSocketIdentity, identityBegin);
        write(_connFd, idBuf, std::distance(idBuf, last));
        _sendLocalIdentity = true;
    }

    assert(_sendLocalIdentity);
    printf("Have sent out the local Identity\n");
}

MessageConnectionTCP::~MessageConnectionTCP() {}
