#include "scaler/tracing/log_exporter.h"

#include <opentelemetry/exporters/otlp/otlp_http_log_record_exporter_factory.h>
#include <opentelemetry/exporters/otlp/otlp_http_log_record_exporter_options.h>
#include <opentelemetry/logs/severity.h>
#include <opentelemetry/nostd/unique_ptr.h>
#include <opentelemetry/sdk/instrumentationscope/instrumentation_scope.h>
#include <opentelemetry/sdk/logs/batch_log_record_processor_factory.h>
#include <opentelemetry/sdk/logs/batch_log_record_processor_options.h>
#include <opentelemetry/sdk/logs/processor.h>
#include <opentelemetry/sdk/logs/recordable.h>
#include <opentelemetry/sdk/resource/resource.h>
#include <opentelemetry/trace/trace_flags.h>

#include <algorithm>
#include <exception>
#include <unordered_map>
#include <utility>

#include "scaler/tracing/handover_queue.h"
#include "scaler/tracing/sdk_conversion.h"

namespace scaler {
namespace tracing {

struct LogExporter::State {
    std::unique_ptr<opentelemetry::sdk::logs::LogRecordProcessor> _processor;
    opentelemetry::sdk::resource::Resource _resource;
    opentelemetry::sdk::logs::LogRecordLimits _limits;
    // one scope per logger name, as the Python SDK makes; only the handover thread touches it
    std::unordered_map<
        std::string,
        opentelemetry::nostd::unique_ptr<opentelemetry::sdk::instrumentationscope::InstrumentationScope>>
        _scopes;
    bool _stopped {false};
    std::unique_ptr<HandoverQueue<LogRecord>> _queue;  // last: its thread uses every field above

    const opentelemetry::sdk::instrumentationscope::InstrumentationScope& scope(const std::string& name)
    {
        auto found = _scopes.find(name);
        if (found == _scopes.end()) {
            found = _scopes.emplace(name, opentelemetry::sdk::instrumentationscope::InstrumentationScope::Create(name))
                        .first;
        }
        return *found->second;
    }

    void handOver(const LogRecord& record)
    {
        std::unique_ptr<opentelemetry::sdk::logs::Recordable> recordable = _processor->MakeRecordable();

        recordable->SetLogRecordLimits(_limits);  // before the attributes it limits
        recordable->SetResource(_resource);
        recordable->SetInstrumentationScope(scope(record._scopeName));
        recordable->SetTimestamp(toSDKTimestamp(record._timeUnixNano));
        recordable->SetObservedTimestamp(toSDKTimestamp(record._observedTimeUnixNano));
        recordable->SetSeverity(static_cast<opentelemetry::logs::Severity>(record._severityNumber));
        recordable->SetBody(toSDKValue(record._body));

        for (const auto& attribute: record._attributes) {
            recordable->SetAttribute(attribute._key, toSDKValue(attribute._value));
        }

        if (record._spanContext) {
            recordable->SetTraceId(toSDKTraceID(record._spanContext->_traceID));
            recordable->SetSpanId(toSDKSpanID(record._spanContext->_spanID));
            recordable->SetTraceFlags(
                opentelemetry::trace::TraceFlags {
                    record._spanContext->_sampled ? opentelemetry::trace::TraceFlags::kIsSampled : uint8_t {0}});
        }

        _processor->OnEmit(std::move(recordable));
    }
};

LogExporter::LogExporter(std::unique_ptr<State> state) noexcept: _state {std::move(state)}
{
}

LogExporter::~LogExporter()
{
    shutdown(std::chrono::milliseconds::zero());
}

std::expected<std::unique_ptr<LogExporter>, std::string> LogExporter::create(
    const std::vector<Attribute>& resourceAttributes, LogLimits limits) noexcept
{
    try {
        const opentelemetry::exporter::otlp::OtlpHttpLogRecordExporterOptions exporterOptions {};
        const opentelemetry::sdk::logs::BatchLogRecordProcessorOptions processorOptions {};

        auto state        = std::make_unique<State>();
        state->_processor = opentelemetry::sdk::logs::BatchLogRecordProcessorFactory::Create(
            opentelemetry::exporter::otlp::OtlpHttpLogRecordExporterFactory::Create(exporterOptions), processorOptions);
        state->_resource = toSDKResource(resourceAttributes);
        state->_limits   = toSDKLogLimits(limits);
        state->_queue    = std::make_unique<HandoverQueue<LogRecord>>(
            processorOptions.max_queue_size, [state = state.get()](LogRecord& record) { state->handOver(record); });
        return std::unique_ptr<LogExporter> {new LogExporter {std::move(state)}};
    } catch (const std::exception& error) {
        return std::unexpected {std::string {error.what()}};
    }
}

bool LogExporter::exportLog(LogRecord record) noexcept
{
    return _state->_queue->push(std::move(record));
}

bool LogExporter::flush(std::chrono::milliseconds timeout) noexcept
{
    const auto deadline = std::chrono::steady_clock::now() + timeout;
    if (!_state->_queue->waitUntilConsumed(deadline)) {
        return false;
    }

    const auto remaining =
        std::max(deadline - std::chrono::steady_clock::now(), std::chrono::steady_clock::duration::zero());
    return _state->_processor->ForceFlush(std::chrono::duration_cast<std::chrono::microseconds>(remaining));
}

bool LogExporter::shutdown(std::chrono::milliseconds timeout) noexcept
{
    if (_state->_stopped) {
        return true;
    }
    _state->_stopped = true;
    _state->_queue->stop();  // hands over every record queued before the stop
    return _state->_processor->Shutdown(std::chrono::duration_cast<std::chrono::microseconds>(timeout));
}

}  // namespace tracing
}  // namespace scaler
