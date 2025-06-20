#pragma once

// C++
#include <functional>
#include <string>
#include <optional>
#include <expected>

// First-party
#include "scaler/io/ymq/errors.h"

class EpollContext;
class Message;

struct Configuration {
    using PollingContext        = EpollContext;
    using Identity              = std::string;
    using SendMessageCallback   = std::function<void(std::optional<Error>)>;
    using RecvMessageCallback   = std::function<void(std::expected<Message, Error>)>;
    using ConnectReturnCallback = std::function<void(std::optional<Error>)>;
    using BindReturnCallback    = std::function<void(std::optional<Error>)>;
};
