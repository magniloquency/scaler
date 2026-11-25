#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace scaler {
namespace tracing {

using TraceID = std::array<uint8_t, 16>;
using SpanID  = std::array<uint8_t, 8>;

using AttributeValue = std::variant<std::string, bool, int64_t, double>;

struct Attribute {
    std::string _key;
    AttributeValue _value;
};

struct SpanEvent {
    std::string _name;
    uint64_t _timeUnixNano;
    std::vector<Attribute> _attributes;
};

struct SpanLink {
    TraceID _traceID;
    SpanID _spanID;
    std::string _traceState;  // W3C tracestate header, empty when none
    std::vector<Attribute> _attributes;
};

// A finished, sampled span, copied out of Python so it can be exported without the GIL.
struct SpanRecord {
    TraceID _traceID;
    SpanID _spanID;
    std::optional<SpanID> _parentSpanID;
    std::string _traceState;  // W3C tracestate header, empty when none
    std::string _name;
    int _kind;  // opentelemetry::trace::SpanKind, which numbers kinds as the Python API does
    uint64_t _startTimeUnixNano;
    uint64_t _endTimeUnixNano;
    int _statusCode;  // opentelemetry::trace::StatusCode, numbered as the Python API does
    std::string _statusMessage;
    std::vector<Attribute> _attributes;
    std::vector<SpanEvent> _events;
    std::vector<SpanLink> _links;
};

}  // namespace tracing
}  // namespace scaler
