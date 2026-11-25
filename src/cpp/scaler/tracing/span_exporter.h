#pragma once

#include <chrono>
#include <expected>
#include <memory>
#include <string>
#include <vector>

#include "scaler/tracing/limits.h"
#include "scaler/tracing/sdk_log_handler.h"
#include "scaler/tracing/span_record.h"

namespace scaler {
namespace tracing {

// Exports finished spans with opentelemetry-cpp's batch processor and OTLP/HTTP exporter.
//
// exportSpan() only queues the span: a handover thread builds the SDK's span, which applies the limits, and passes it
// to the batch processor, whose own thread encodes and sends batches. The calling thread does no encoding.
//
// The exporter reads its endpoint, headers, timeout, compression, and TLS settings from the standard
// OTEL_EXPORTER_OTLP_* variables, and the batch processor its queue and delay settings from OTEL_BSP_*.
class SpanExporter {
public:
    ~SpanExporter();

    SpanExporter(const SpanExporter&)            = delete;
    SpanExporter& operator=(const SpanExporter&) = delete;
    SpanExporter(SpanExporter&&)                 = delete;
    SpanExporter& operator=(SpanExporter&&)      = delete;

    static std::expected<std::unique_ptr<SpanExporter>, std::string> create(
        const std::vector<Attribute>& resourceAttributes,
        const std::string& scopeName,
        SpanLimits limits,
        LogCallback log) noexcept;

    // Thread-safe; drops the span, and logs it, when OTEL_BSP_MAX_QUEUE_SIZE spans already wait.
    void exportSpan(SpanRecord span) noexcept;

    // Blocks until every span queued so far is exported, or `timeout` passes.
    bool flush(std::chrono::milliseconds timeout) noexcept;

    // Exports what is queued, then stops both threads; every later span is dropped.
    bool shutdown(std::chrono::milliseconds timeout) noexcept;

private:
    struct State;

    std::unique_ptr<State> _state;

    explicit SpanExporter(std::unique_ptr<State> state) noexcept;
};

}  // namespace tracing
}  // namespace scaler
