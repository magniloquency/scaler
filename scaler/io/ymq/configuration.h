#pragma once

// C++
#include <functional>
#include <string>

class EpollContext;
class Message;

struct Configuration {
    using PollingContext      = EpollContext;
    using Identity            = std::string;
    using SendMessageCallback = std::function<void(int)>;
    using RecvMessageCallback = std::function<void(Message)>;
};
