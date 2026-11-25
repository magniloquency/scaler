#pragma once

#include <functional>
#include <string_view>

namespace scaler {
namespace tracing {

enum class LogLevel { error, warning };

// Receives a message about exporting telemetry; it may run on any of the exporters' threads.
using LogCallback = std::function<void(LogLevel level, std::string_view message)>;

// Routes opentelemetry-cpp's own errors and warnings, such as a failed export, to `log`; process-wide, like the
// SDK's log handler it replaces.
void installSDKLogHandler(LogCallback log);

}  // namespace tracing
}  // namespace scaler
