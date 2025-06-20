#pragma once

// C++
#include <map>
#include <memory>
#include <optional>

// First-party
#include "scaler/io/ymq/configuration.h"
#include "scaler/io/ymq/message.h"
#include "scaler/io/ymq/message_connection_tcp.h"
#include "scaler/io/ymq/tcp_client.h"
#include "scaler/io/ymq/tcp_server.h"
#include "scaler/io/ymq/typedefs.h"

class TcpReadOperation;

// NOTE: Don't do this. It pollutes the env. I tried to remove it, but it reports err
// in pymod module. Consider include the corresponding file and define types there. - gxu
using Identity = Configuration::Identity;

class EventLoopThread;

class IOSocket {
public:
    std::shared_ptr<EventLoopThread> _eventLoopThread;
    Identity _identity;
    IOSocketType _socketType;

    std::optional<TcpClient> _tcpClient;
    std::optional<TcpServer> _tcpServer;

public:
    using ConnectReturnCallback = Configuration::ConnectReturnCallback;
    using BindReturnCallback    = Configuration::BindReturnCallback;
    using SendMessageCallback   = Configuration::SendMessageCallback;
    using RecvMessageCallback   = Configuration::RecvMessageCallback;

    std::shared_ptr<std::queue<TcpReadOperation>> _pendingReadOperations;
    // FIXME: Maybe we don't provide this map at all. _identity and connection is not injective.
    // Or maybe we enforce user to provide unique name.
    // We can provide canonical name etc.
    std::map<std::string, MessageConnectionTCP*> _identityToConnection;
    std::map<int /* class FileDescriptor */, std::unique_ptr<MessageConnectionTCP>> _fdToConnection;

    std::vector<std::unique_ptr<MessageConnectionTCP>> _deadConnection;

    IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType);

    // IOSocket();
    IOSocket(const IOSocket&)            = delete;
    IOSocket& operator=(const IOSocket&) = delete;
    IOSocket(IOSocket&&)                 = delete;
    IOSocket& operator=(IOSocket&&)      = delete;

    Identity identity() const { return _identity; }
    IOSocketType socketType() const { return _socketType; }

    void removeConnectedTcpClient();

    void sendMessage(Message message, SendMessageCallback callback);
    void recvMessage(RecvMessageCallback callback);

    void connectTo(sockaddr addr, ConnectReturnCallback callback);
    void connectTo(std::string networkAddress, ConnectReturnCallback callback);

    void bindTo(std::string networkAddress, BindReturnCallback callback);

    // From Connection Class only
    void onConnectionDisconnected(MessageConnectionTCP* conn);

    // From Connection Class only
    void onConnectionIdentityReceived(MessageConnectionTCP* conn);

    void onCreated();
    // TODO: ~IOSocket should remove all connection it is owning
    ~IOSocket() {}

    // void recvMessage(Message* msg);
};
