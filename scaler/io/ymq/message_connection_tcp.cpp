

#include "scaler/io/ymq/message_connection_tcp.h"

#include <unistd.h>

#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>

#include "scaler/io/ymq/bytes.h"
#include "scaler/io/ymq/common.h"
#include "scaler/io/ymq/event_loop_thread.h"
#include "scaler/io/ymq/event_manager.h"
#include "scaler/io/ymq/file_descriptor.h"
#include "scaler/io/ymq/io_socket.h"
#include "scaler/io/ymq/typedefs.h"

MessageConnectionTCP::MessageConnectionTCP(
    std::shared_ptr<IOSocket> ioSocket, FileDescriptor fd, sockaddr_storage remoteAddress)
    : _socket(ioSocket), _remoteAddress(remoteAddress) {
    _readOp = {};

    _eventManager = std::make_unique<EventManager>(
        _socket->eventLoopThread(), fd, [this](FileDescriptor& fd, Events events) { this->onEvent(fd, events); });
}

void MessageConnectionTCP::onEvent(FileDescriptor& fd, Events events) {
    if (events.readable) {
        this->onRead(fd);
    }
    if (events.writable) {
        this->onWrite(fd);
    }
}

void MessageConnectionTCP::onCreated() {
    printf("%s\n", __PRETTY_FUNCTION__);

    // todo: pass EPOLLIN, EPOLLOUT, etc.
    _socket->eventLoopThread()->registerEventManager(*this->_eventManager.get());
    // this->_eventLoopThread->_eventLoop.addFdToLoop(_connFd, EPOLLIN | EPOLLOUT | EPOLLET, this->_eventManager.get());
}

void MessageConnectionTCP::onRead(FileDescriptor& fd) {
    if (_readOp.progress == IOProgress::Header) {
        auto result = fd.read(_readOp.header, 4 - _readOp.cursor);
        if (!result) {
            if (result.error() == EAGAIN)
                return;

            // todo: error handling
            panic("read failed");
        }

        _readOp.cursor += *result;

        if (!_readOp.is_stage_complete())
            return;

        _readOp.payload  = new uint8_t[_readOp.len()];
        _readOp.progress = IOProgress::Payload;
        _readOp.cursor   = 0;
    }

    if (_readOp.progress == IOProgress::Payload) {
        auto result = fd.read(_readOp.payload, 4 - _readOp.cursor);
        if (!result) {
            if (result.error() == EAGAIN)
                return;

            // todo: error handling
            panic("read failed");
        }

        _readOp.cursor += *result;

        if (_readOp.is_stage_complete())
            this->onReadMessage();
    }
}

void MessageConnectionTCP::onReadMessage() {
    auto bytes = Bytes(_readOp.payload, _readOp.len(), Ownership::Owned);

    switch (_stage) {
        case ConnectionStage::IdentityExchange:
            this->_remoteIdentity = std::move(bytes);
            this->_stage          = ConnectionStage::Stable;
            break;
        case ConnectionStage::Stable:
            if (_readQueue.empty()) {
                _receivedMessages.push(std::move(bytes));
            } else {
                auto callback = _readQueue.front();
                callback(std::move(bytes));
                _readQueue.pop();
            }
    }

    _readOp.reset();
}

void MessageConnectionTCP::onWrite(FileDescriptor& fd) {
    if (_writeOp.is_empty()) {
        if (_writeQueue.empty())
            return;

        auto request = &_writeQueue.front();
        serialize_u32(request->payload.len, _writeOp.header);
        _writeOp.payload = request->payload.data;
    }

    if (_writeOp.progress == IOProgress::Header) {
        auto result = fd.write(_writeOp.header, 4 - _writeOp.cursor);

        if (!result) {
            if (result.error() == EAGAIN)
                return;

            // todo: error handling
            panic("write failed");
        }

        _writeOp.cursor += *result;

        if (!_writeOp.is_stage_complete())
            return;

        _writeOp.progress = IOProgress::Payload;
    }

    if (_writeOp.progress == IOProgress::Payload) {
        auto result = fd.write(_writeOp.header, 4 - _writeOp.cursor);

        if (!result) {
            if (result.error() == EAGAIN)
                return;

            // todo: error handling
            panic("write failed");
        }

        _writeOp.cursor += *result;

        if (!_writeOp.is_stage_complete())
            return;

        this->onWroteMessage();
    }
}

void MessageConnectionTCP::onWroteMessage() {
    this->_writeQueue.pop();
    _writeOp.reset();
}

// TODO: Maybe change this to message_t
void MessageConnectionTCP::send(Bytes msg, std::function<void()> callback) {
    _writeQueue.push({.payload = std::move(msg), .callback = callback});

    this->_eventManager->onEvent({.writable = true});
}

void MessageConnectionTCP::recv(std::function<void(Bytes)> callback) {
    _readQueue.push(callback);

    this->_eventManager->onEvent({.readable = true});
}

MessageConnectionTCP::~MessageConnectionTCP() {}
