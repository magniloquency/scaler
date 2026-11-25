#include "scaler/tracing/span_exporter.h"

#include <opentelemetry/common/key_value_iterable_view.h>
#include <opentelemetry/exporters/otlp/otlp_http_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_http_exporter_options.h>
#include <opentelemetry/nostd/unique_ptr.h>
#include <opentelemetry/sdk/instrumentationscope/instrumentation_scope.h>
#include <opentelemetry/sdk/resource/resource.h>
#include <opentelemetry/sdk/trace/batch_span_processor_factory.h>
#include <opentelemetry/sdk/trace/batch_span_processor_options.h>
#include <opentelemetry/sdk/trace/processor.h>
#include <opentelemetry/sdk/trace/recordable.h>
#include <opentelemetry/trace/span_metadata.h>
#include <opentelemetry/trace/trace_flags.h>

#include <algorithm>
#include <atomic>
#include <exception>
#include <utility>

#include "scaler/tracing/handover_queue.h"
#include "scaler/tracing/sdk_conversion.h"

namespace scaler {
namespace tracing {

namespace {

// the first dropped span is logged, then every this many
constexpr uint64_t droppedSpanLogInterval = 1000;

}  // namespace

struct SpanExporter::State {
    std::unique_ptr<opentelemetry::sdk::trace::SpanProcessor> _processor;
    opentelemetry::sdk::resource::Resource _resource;
    opentelemetry::nostd::unique_ptr<opentelemetry::sdk::instrumentationscope::InstrumentationScope> _scope;
    opentelemetry::sdk::trace::SpanLimits _limits;
    LogCallback _log;
    std::atomic<uint64_t> _droppedCount {0};
    bool _stopped {false};
    std::unique_ptr<HandoverQueue<SpanRecord>> _queue;  // last: its thread uses every field above

    void handOver(const SpanRecord& span)
    {
        std::unique_ptr<opentelemetry::sdk::trace::Recordable> recordable = _processor->MakeRecordable();

        recordable->SetSpanLimits(_limits);  // before the attributes, events, and links it limits
        recordable->SetResource(_resource);
        recordable->SetInstrumentationScope(*_scope);
        recordable->SetIdentity(
            toSDKSpanContext(span._traceID, span._spanID, span._traceState),
            span._parentSpanID ? toSDKSpanID(*span._parentSpanID) : opentelemetry::trace::SpanId {});
        recordable->SetTraceFlags(opentelemetry::trace::TraceFlags {opentelemetry::trace::TraceFlags::kIsSampled});
        recordable->SetName(span._name);
        recordable->SetSpanKind(static_cast<opentelemetry::trace::SpanKind>(span._kind));
        recordable->SetStartTime(toSDKTimestamp(span._startTimeUnixNano));
        recordable->SetDuration(std::chrono::nanoseconds {span._endTimeUnixNano - span._startTimeUnixNano});
        recordable->SetStatus(static_cast<opentelemetry::trace::StatusCode>(span._statusCode), span._statusMessage);

        for (const auto& attribute: span._attributes) {
            recordable->SetAttribute(attribute._key, toSDKValue(attribute._value));
        }

        for (const auto& event: span._events) {
            const SDKAttributes attributes = toSDKAttributes(event._attributes);
            recordable->AddEvent(
                event._name,
                toSDKTimestamp(event._timeUnixNano),
                opentelemetry::common::KeyValueIterableView<SDKAttributes> {attributes});
        }

        for (const auto& link: span._links) {
            const SDKAttributes attributes = toSDKAttributes(link._attributes);
            recordable->AddLink(
                toSDKSpanContext(link._traceID, link._spanID, link._traceState),
                opentelemetry::common::KeyValueIterableView<SDKAttributes> {attributes});
        }

        _processor->OnEnd(std::move(recordable));
    }
};

SpanExporter::SpanExporter(std::unique_ptr<State> state) noexcept: _state {std::move(state)}
{
}

SpanExporter::~SpanExporter()
{
    shutdown(std::chrono::milliseconds::zero());
}

std::expected<std::unique_ptr<SpanExporter>, std::string> SpanExporter::create(
    const std::vector<Attribute>& resourceAttributes,
    const std::string& scopeName,
    SpanLimits limits,
    LogCallback log) noexcept
{
    try {
        const opentelemetry::exporter::otlp::OtlpHttpExporterOptions exporterOptions {};
        const opentelemetry::sdk::trace::BatchSpanProcessorOptions processorOptions {};

        auto state        = std::make_unique<State>();
        state->_processor = opentelemetry::sdk::trace::BatchSpanProcessorFactory::Create(
            opentelemetry::exporter::otlp::OtlpHttpExporterFactory::Create(exporterOptions), processorOptions);
        state->_resource = toSDKResource(resourceAttributes);
        state->_scope    = opentelemetry::sdk::instrumentationscope::InstrumentationScope::Create(scopeName);
        state->_limits   = toSDKSpanLimits(limits);
        state->_log      = std::move(log);
        state->_queue    = std::make_unique<HandoverQueue<SpanRecord>>(
            processorOptions.max_queue_size, [state = state.get()](SpanRecord& span) { state->handOver(span); });
        return std::unique_ptr<SpanExporter> {new SpanExporter {std::move(state)}};
    } catch (const std::exception& error) {
        return std::unexpected {std::string {error.what()}};
    }
}

void SpanExporter::exportSpan(SpanRecord span) noexcept
{
    if (_state->_queue->push(std::move(span))) {
        return;
    }

    const uint64_t droppedCount = ++_state->_droppedCount;
    if (droppedCount == 1 || droppedCount % droppedSpanLogInterval == 0) {
        _state->_log(
            LogLevel::warning,
            "dropped " + std::to_string(droppedCount) + " span(s): the export queue is full or shut down");
    }
}

bool SpanExporter::flush(std::chrono::milliseconds timeout) noexcept
{
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    if (!_state->_queue->waitUntilConsumed(deadline)) {
        return false;
    }

    const auto remaining =
        std::max(deadline - std::chrono::steady_clock::now(), std::chrono::steady_clock::duration::zero());
    return _state->_processor->ForceFlush(std::chrono::duration_cast<std::chrono::microseconds>(remaining));
}

bool SpanExporter::shutdown(std::chrono::milliseconds timeout) noexcept
{
    if (_state->_stopped) {
        return true;
    }
    _state->_stopped = true;
    _state->_queue->stop();  // hands over every span queued before the stop
    return _state->_processor->Shutdown(std::chrono::duration_cast<std::chrono::microseconds>(timeout));
}

}  // namespace tracing
}  // namespace scaler
