#pragma once

#include <opentelemetry/common/attribute_value.h>
#include <opentelemetry/common/timestamp.h>
#include <opentelemetry/nostd/string_view.h>
#include <opentelemetry/sdk/logs/log_record_limits.h>
#include <opentelemetry/sdk/resource/resource.h>
#include <opentelemetry/sdk/trace/span_limits.h>
#include <opentelemetry/trace/span_context.h>
#include <opentelemetry/trace/span_id.h>
#include <opentelemetry/trace/trace_id.h>

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

#include "scaler/tracing/limits.h"
#include "scaler/tracing/span_record.h"

namespace scaler {
namespace tracing {

// a view of Scaler attributes as the SDK takes them; the strings stay owned by the record they came from
using SDKAttributes = std::vector<std::pair<opentelemetry::nostd::string_view, opentelemetry::common::AttributeValue>>;

opentelemetry::common::AttributeValue toSDKValue(const AttributeValue& value);
SDKAttributes toSDKAttributes(const std::vector<Attribute>& attributes);
opentelemetry::sdk::resource::Resource toSDKResource(const std::vector<Attribute>& attributes);
opentelemetry::trace::TraceId toSDKTraceID(const TraceID& traceID);
opentelemetry::trace::SpanId toSDKSpanID(const SpanID& spanID);
opentelemetry::common::SystemTimestamp toSDKTimestamp(uint64_t unixNano);

// a missing limit becomes the largest value, which is no limit to the SDK
opentelemetry::sdk::trace::SpanLimits toSDKSpanLimits(const SpanLimits& limits);
opentelemetry::sdk::logs::LogRecordLimits toSDKLogLimits(const LogLimits& limits);

// a sampled span context: every span and parent the Python provider hands over was sampled
opentelemetry::trace::SpanContext toSDKSpanContext(
    const TraceID& traceID, const SpanID& spanID, const std::string& traceState);

}  // namespace tracing
}  // namespace scaler
