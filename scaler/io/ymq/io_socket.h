#pragma once

// C++
#include <map>
#include <memory>
#include <optional>

// First-party
#include "scaler/io/ymq/bytes.h"
#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"
#include "scaler/io/ymq/typedefs.h"

// NOTE: Don't do this. It pollutes the env. I tried to remove it, but it reports err
// in pymod module. Consider include the corresponding file and define types there. - gxu
using Identity = Configuration::Identity;

class EventLoopThread;
class MessageConnectionTCP;

class TcpClient;
class TcpServer;

class IOSocket: public std::enable_shared_from_this<IOSocket> {
    std::shared_ptr<EventLoopThread> _eventLoopThread;
    Identity _identity;
    IOSocketType _socketType;

    std::unique_ptr<TcpClient> _tcpClient;
    std::unique_ptr<TcpServer> _tcpServer;

public:
    std::map<std::string, std::shared_ptr<MessageConnectionTCP>> _identityToConnection;

    IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType);

    IOSocket();
    IOSocket(const IOSocket&)            = delete;
    IOSocket& operator=(const IOSocket&) = delete;
    IOSocket(IOSocket&&)                 = delete;
    IOSocket& operator=(IOSocket&&)      = delete;

    Identity identity() const { return _identity; }
    IOSocketType socketType() const { return _socketType; }

    // TODO: In the future, this will be Message
    void recvMessage(std::vector<char>& buf);

    void removeConnectedTcpClient();

    void sendMessage(Bytes address, Bytes payload, std::function<void()> callback);
    void sendMessage(Bytes buf, std::function<void()> callback, std::string remoteIdentity);

    void addConnection(std::unique_ptr<MessageConnectionTCP> connection) { todo(); }

    std::shared_ptr<EventLoopThread> eventLoopThread() const { return this->_eventLoopThread; }

    // string -> connection mapping
    // and connection->string mapping

    // put it into the concurrent q, which is execute_now
    // void sendMessage(Message* msg, Continuation cont) {
    // EXAMPLE
    // execute_now(
    // switch (socketTypes) {
    //     case Pub:
    //         for (auto [fd, conn] &: fd_to_conn) {
    //             conn.send(msg.len, msg.size);
    //             conn.setWriteCompleteCallback(cont);
    //             eventLoopThread.getEventLoop().update_events(turn write on for this fd);
    //         }
    //         break;
    // }
    // )
    // }

    void connectTo(sockaddr addr);

    void onCreated();
    // TODO: ~IOSocket should remove all connection it is owning
    ~IOSocket() {}

    // void recvMessage(Message* msg);
};
