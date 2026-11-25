#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

#include "scaler/tracing/environment.h"

namespace scaler {
namespace tracing {

// The span limits the OTEL_*_LIMIT variables set, read as the Python SDK's SpanLimits are; nullopt is no limit.
// opentelemetry-cpp's recordables apply them, cutting strings at the last whole UTF-8 character within the length.
struct SpanLimits {
    std::optional<size_t> _maxAttributes;
    std::optional<size_t> _maxEventAttributes;
    std::optional<size_t> _maxLinkAttributes;
    std::optional<size_t> _maxEvents;
    std::optional<size_t> _maxLinks;
    std::optional<size_t> _maxAttributeLength;  // in bytes, for span, event, and link attributes alike

    // A value it cannot use adds a warning, and that limit keeps its default.
    static SpanLimits fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings);
};

// The log record limits the OTEL_LOGRECORD_*_LIMIT variables set, read as the Python SDK's LogLimits are.
struct LogLimits {
    std::optional<size_t> _maxAttributes;
    std::optional<size_t> _maxAttributeLength;  // in bytes

    static LogLimits fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings);
};

}  // namespace tracing
}  // namespace scaler
