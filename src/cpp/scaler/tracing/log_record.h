#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "scaler/tracing/span_record.h"

namespace scaler {
namespace tracing {

// The span a log record was emitted inside, which the record carries so a backend can join the two.
struct LogSpanContext {
    TraceID _traceID;
    SpanID _spanID;
    bool _sampled;
};

// A `logging` record, copied out of Python so it can be exported without the GIL.
struct LogRecord {
    uint64_t _timeUnixNano;
    uint64_t _observedTimeUnixNano;
    int _severityNumber;     // OTLP SeverityNumber, which opentelemetry::logs::Severity numbers alike
    std::string _scopeName;  // the logger's name, as the Python SDK's instrumentation scope
    AttributeValue _body;
    std::vector<Attribute> _attributes;
    std::optional<LogSpanContext> _spanContext;
};

}  // namespace tracing
}  // namespace scaler
