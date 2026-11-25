#pragma once

#include <chrono>
#include <expected>
#include <memory>
#include <string>
#include <vector>

#include "scaler/tracing/limits.h"
#include "scaler/tracing/log_record.h"
#include "scaler/tracing/sdk_log_handler.h"

namespace scaler {
namespace tracing {

// Exports log records with opentelemetry-cpp's batch processor and OTLP/HTTP log exporter, as SpanExporter does
// spans: exportLog() only queues, and the encoding and sending happen on the exporter's threads.
//
// The exporter reads the OTEL_EXPORTER_OTLP_* (and _LOGS_*) variables, and the batch processor OTEL_BLRP_*.
class LogExporter {
public:
    ~LogExporter();

    LogExporter(const LogExporter&)            = delete;
    LogExporter& operator=(const LogExporter&) = delete;
    LogExporter(LogExporter&&)                 = delete;
    LogExporter& operator=(LogExporter&&)      = delete;

    static std::expected<std::unique_ptr<LogExporter>, std::string> create(
        const std::vector<Attribute>& resourceAttributes, LogLimits limits) noexcept;

    // Thread-safe; drops the record when OTEL_BLRP_MAX_QUEUE_SIZE records already wait, and returns false.
    bool exportLog(LogRecord record) noexcept;

    // Blocks until every record queued so far is exported, or `timeout` passes.
    bool flush(std::chrono::milliseconds timeout) noexcept;

    // Exports what is queued, then stops both threads; every later record is dropped.
    bool shutdown(std::chrono::milliseconds timeout) noexcept;

private:
    struct State;

    std::unique_ptr<State> _state;

    explicit LogExporter(std::unique_ptr<State> state) noexcept;
};

}  // namespace tracing
}  // namespace scaler
