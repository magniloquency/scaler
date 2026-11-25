#pragma once

#include <cstdint>
#include <memory>
#include <optional>
#include <string_view>

#include "scaler/tracing/log_exporter.h"
#include "scaler/tracing/sampler.h"
#include "scaler/tracing/sdk_log_handler.h"
#include "scaler/tracing/span_exporter.h"
#include "scaler/utility/pymod/compatibility.h"

namespace scaler {
namespace tracing {
namespace pymod {

// One per process, like the Python SDK's global providers; configure() fills it.
struct ModuleState {
    std::optional<Sampler> _sampler;
    std::unique_ptr<SpanExporter> _spans;
    std::unique_ptr<LogExporter> _logs;

    // traceback.format_exception, for a log record's stack trace; kept for the life of the process, since releasing
    // it after the interpreter finalized would crash it
    PyObject* _formatException {nullptr};
};

ModuleState& moduleState();

// to the logger the exporters' own messages go to; it takes the GIL, and drops the message while Python shuts down
void logToPython(LogLevel level, std::string_view message);

uint64_t nowUnixNano();

// the name of the logger logToPython() writes to, which the native log handler must not export
constexpr const char* exporterLoggerName = "scaler.utility.native_telemetry";

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
