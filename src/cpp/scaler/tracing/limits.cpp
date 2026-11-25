#include "scaler/tracing/limits.h"

#include <algorithm>
#include <cctype>
#include <charconv>
#include <system_error>

namespace scaler {
namespace tracing {

namespace {

// the Python SDK's defaults: 128 of each, and no length limit
constexpr size_t defaultCountLimit = 128;

constexpr const char* unsetValue = "unset";

// `fallback` when the variable is not set or holds no usable count, nullopt when it says "unset"
std::optional<size_t> readLimit(
    const EnvironmentLookup& lookup,
    const char* variable,
    std::optional<size_t> fallback,
    std::vector<std::string>& warnings)
{
    std::optional<std::string> value = lookup(variable);
    if (!value) {
        return fallback;
    }

    std::string text = *value;
    text.erase(0, text.find_first_not_of(" \t"));
    text.erase(text.find_last_not_of(" \t") + 1);
    std::transform(text.begin(), text.end(), text.begin(), [](unsigned char letter) { return std::tolower(letter); });
    if (text == unsetValue) {
        return std::nullopt;
    }

    size_t limit            = 0;
    const char* end         = text.data() + text.size();
    const auto [ptr, error] = std::from_chars(text.data(), end, limit);
    if (text.empty() || error != std::errc {} || ptr != end) {
        warnings.push_back(std::string {variable} + " must be a non-negative integer, got \"" + *value + "\"");
        return fallback;
    }
    return limit;
}

}  // namespace

SpanLimits SpanLimits::fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings)
{
    // OTEL_ATTRIBUTE_COUNT_LIMIT is the default of the three attribute counts, and the general length limit the
    // default of the span attribute length, as in the Python SDK; opentelemetry-cpp has one length for spans
    const std::optional<size_t> attributeCount =
        readLimit(lookup, "OTEL_ATTRIBUTE_COUNT_LIMIT", defaultCountLimit, warnings);
    const std::optional<size_t> attributeLength =
        readLimit(lookup, "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT", std::nullopt, warnings);

    return SpanLimits {
        ._maxAttributes      = readLimit(lookup, "OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT", attributeCount, warnings),
        ._maxEventAttributes = readLimit(lookup, "OTEL_EVENT_ATTRIBUTE_COUNT_LIMIT", attributeCount, warnings),
        ._maxLinkAttributes  = readLimit(lookup, "OTEL_LINK_ATTRIBUTE_COUNT_LIMIT", attributeCount, warnings),
        ._maxEvents          = readLimit(lookup, "OTEL_SPAN_EVENT_COUNT_LIMIT", defaultCountLimit, warnings),
        ._maxLinks           = readLimit(lookup, "OTEL_SPAN_LINK_COUNT_LIMIT", defaultCountLimit, warnings),
        ._maxAttributeLength = readLimit(lookup, "OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT", attributeLength, warnings),
    };
}

LogLimits LogLimits::fromEnvironment(const EnvironmentLookup& lookup, std::vector<std::string>& warnings)
{
    const std::optional<size_t> attributeCount =
        readLimit(lookup, "OTEL_ATTRIBUTE_COUNT_LIMIT", defaultCountLimit, warnings);
    const std::optional<size_t> attributeLength =
        readLimit(lookup, "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT", std::nullopt, warnings);

    return LogLimits {
        ._maxAttributes = readLimit(lookup, "OTEL_LOGRECORD_ATTRIBUTE_COUNT_LIMIT", attributeCount, warnings),
        ._maxAttributeLength =
            readLimit(lookup, "OTEL_LOGRECORD_ATTRIBUTE_VALUE_LENGTH_LIMIT", attributeLength, warnings),
    };
}

}  // namespace tracing
}  // namespace scaler
