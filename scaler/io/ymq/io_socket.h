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
class TcpWriteOperation;

// NOTE: Don't do this. It pollutes the env. I tried to remove it, but it reports err
// in pymod module. Consider include the corresponding file and define types there. - gxu
using Identity = Configuration::Identity;

class EventLoopThread;

class IOSocket {
public:
    std::shared_ptr<EventLoopThread> _eventLoopThread;
    Identity _identity;
    IOSocketType _socketType;

    // NOTE: Owning one TcpClient essentially means the user cannot issue another connectTo
    // when some message connection is retring to connect.
    std::optional<TcpClient> _tcpClient;
    // NOTE: Owning one TcpServer essentially means the user cannot bindTo multiple addresses.
    std::optional<TcpServer> _tcpServer;

    // NOTE: This variable needs to present in the IOSocket level because the user
    // does not care which connection a message is coming from.
    std::shared_ptr<std::queue<TcpReadOperation>> _pendingReadOperations;

public:
    using ConnectReturnCallback = Configuration::ConnectReturnCallback;
    using BindReturnCallback    = Configuration::BindReturnCallback;
    using SendMessageCallback   = Configuration::SendMessageCallback;
    using RecvMessageCallback   = Configuration::RecvMessageCallback;

    std::map<std::string, std::unique_ptr<MessageConnectionTCP>> _identityToConnection;
    std::vector<std::unique_ptr<MessageConnectionTCP>> _unconnectedConnection;

    IOSocket(std::shared_ptr<EventLoopThread> eventLoopThread, Identity identity, IOSocketType socketType);

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

    IOSocket(const IOSocket&)            = delete;
    IOSocket& operator=(const IOSocket&) = delete;
    IOSocket(IOSocket&&)                 = delete;
    IOSocket& operator=(IOSocket&&)      = delete;

    // TODO: ~IOSocket should remove all connection it is owning
    ~IOSocket();

    // void recvMessage(Message* msg);
};
