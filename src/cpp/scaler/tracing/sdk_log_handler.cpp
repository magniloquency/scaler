#include "scaler/tracing/sdk_log_handler.h"

#include <opentelemetry/nostd/shared_ptr.h>
#include <opentelemetry/sdk/common/global_log_handler.h>

#include <utility>

namespace scaler {
namespace tracing {

namespace {

class CallbackLogHandler: public opentelemetry::sdk::common::internal_log::LogHandler {
public:
    explicit CallbackLogHandler(LogCallback log): _log {std::move(log)}
    {
    }

    void Handle(
        opentelemetry::sdk::common::internal_log::LogLevel level,
        const char* /*file*/,
        int /*line*/,
        const char* message,
        const opentelemetry::sdk::common::AttributeMap& /*attributes*/) noexcept override
    {
        const bool isError = level == opentelemetry::sdk::common::internal_log::LogLevel::Error;
        _log(isError ? LogLevel::error : LogLevel::warning, message);
    }

private:
    LogCallback _log;
};

}  // namespace

void installSDKLogHandler(LogCallback log)
{
    opentelemetry::sdk::common::internal_log::GlobalLogHandler::SetLogHandler(
        opentelemetry::nostd::shared_ptr<opentelemetry::sdk::common::internal_log::LogHandler> {
            new CallbackLogHandler {std::move(log)}});
    opentelemetry::sdk::common::internal_log::GlobalLogHandler::SetLogLevel(
        opentelemetry::sdk::common::internal_log::LogLevel::Warning);
}

}  // namespace tracing
}  // namespace scaler
