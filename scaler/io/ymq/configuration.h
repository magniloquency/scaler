#pragma once

// C++
#include <expected>
#include <functional>
#include <optional>
#include <string>

// First-party
#include "scaler/io/ymq/errors.h"

class EpollContext;
class Message;

struct Configuration {
    using PollingContext                  = EpollContext;
    using IOSocketIdentity                = std::string;
    using SendMessageCallback             = std::function<void(std::optional<Error>)>;
    using RecvMessageCallback             = std::function<void(std::expected<Message, Error>)>;
    using ConnectReturnCallback           = std::function<void(std::optional<Error>)>;
    using BindReturnCallback              = std::function<void(std::optional<Error>)>;
    using TimedQueueCallback              = std::function<void()>;
    using ExecutionCancellationIdentifier = size_t;
};
