#include "scaler/tracing/sdk_conversion.h"

#include <opentelemetry/nostd/span.h>
#include <opentelemetry/trace/trace_flags.h>
#include <opentelemetry/trace/trace_state.h>

#include <chrono>
#include <limits>
#include <optional>
#include <type_traits>
#include <variant>

namespace scaler {
namespace tracing {

opentelemetry::common::AttributeValue toSDKValue(const AttributeValue& value)
{
    return std::visit(
        [](const auto& alternative) -> opentelemetry::common::AttributeValue {
            if constexpr (std::is_same_v<std::decay_t<decltype(alternative)>, std::string>) {
                return opentelemetry::nostd::string_view {alternative};
            } else {
                return alternative;
            }
        },
        value);
}

SDKAttributes toSDKAttributes(const std::vector<Attribute>& attributes)
{
    SDKAttributes result {};
    result.reserve(attributes.size());
    for (const auto& attribute: attributes) {
        result.emplace_back(attribute._key, toSDKValue(attribute._value));
    }
    return result;
}

opentelemetry::sdk::resource::Resource toSDKResource(const std::vector<Attribute>& attributes)
{
    opentelemetry::sdk::resource::ResourceAttributes resourceAttributes {};
    for (const auto& attribute: attributes) {
        resourceAttributes.SetAttribute(attribute._key, toSDKValue(attribute._value));
    }
    return opentelemetry::sdk::resource::Resource::Create(resourceAttributes);
}

opentelemetry::trace::TraceId toSDKTraceID(const TraceID& traceID)
{
    return opentelemetry::trace::TraceId {
        opentelemetry::nostd::span<const uint8_t, 16> {traceID.data(), traceID.size()}};
}

opentelemetry::trace::SpanId toSDKSpanID(const SpanID& spanID)
{
    return opentelemetry::trace::SpanId {opentelemetry::nostd::span<const uint8_t, 8> {spanID.data(), spanID.size()}};
}

opentelemetry::common::SystemTimestamp toSDKTimestamp(uint64_t unixNano)
{
    return opentelemetry::common::SystemTimestamp {std::chrono::nanoseconds {unixNano}};
}

namespace {

template <typename Count>
Count orNoLimit(const std::optional<size_t>& limit)
{
    return limit ? static_cast<Count>(*limit) : (std::numeric_limits<Count>::max)();
}

}  // namespace

opentelemetry::sdk::trace::SpanLimits toSDKSpanLimits(const SpanLimits& limits)
{
    opentelemetry::sdk::trace::SpanLimits sdkLimits {};
    sdkLimits.attribute_count_limit        = orNoLimit<std::uint32_t>(limits._maxAttributes);
    sdkLimits.attribute_value_length_limit = orNoLimit<std::size_t>(limits._maxAttributeLength);
    sdkLimits.event_count_limit            = orNoLimit<std::uint32_t>(limits._maxEvents);
    sdkLimits.link_count_limit             = orNoLimit<std::uint32_t>(limits._maxLinks);
    sdkLimits.event_attribute_count_limit  = orNoLimit<std::uint32_t>(limits._maxEventAttributes);
    sdkLimits.link_attribute_count_limit   = orNoLimit<std::uint32_t>(limits._maxLinkAttributes);
    return sdkLimits;
}

opentelemetry::sdk::logs::LogRecordLimits toSDKLogLimits(const LogLimits& limits)
{
    opentelemetry::sdk::logs::LogRecordLimits sdkLimits {};
    sdkLimits.attribute_count_limit        = orNoLimit<std::size_t>(limits._maxAttributes);
    sdkLimits.attribute_value_length_limit = orNoLimit<std::size_t>(limits._maxAttributeLength);
    return sdkLimits;
}

opentelemetry::trace::SpanContext toSDKSpanContext(
    const TraceID& traceID, const SpanID& spanID, const std::string& traceState)
{
    return opentelemetry::trace::SpanContext {
        toSDKTraceID(traceID),
        toSDKSpanID(spanID),
        opentelemetry::trace::TraceFlags {opentelemetry::trace::TraceFlags::kIsSampled},
        false,
        traceState.empty() ? opentelemetry::trace::TraceState::GetDefault() :
                             opentelemetry::trace::TraceState::FromHeader(traceState),
    };
}

}  // namespace tracing
}  // namespace scaler
