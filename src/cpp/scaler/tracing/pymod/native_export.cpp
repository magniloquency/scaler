#include <chrono>
#include <cstdint>
#include <string>
#include <vector>

#include "scaler/tracing/environment.h"
#include "scaler/tracing/limits.h"
#include "scaler/tracing/log_exporter.h"
#include "scaler/tracing/pymod/conversion.h"
#include "scaler/tracing/pymod/log.h"
#include "scaler/tracing/pymod/module_state.h"
#include "scaler/tracing/pymod/span_export.h"
#include "scaler/tracing/sampler.h"
#include "scaler/tracing/sdk_log_handler.h"
#include "scaler/tracing/span_exporter.h"
#include "scaler/utility/pymod/compatibility.h"

namespace scaler {
namespace tracing {
namespace pymod {

using scaler::utility::pymod::OwnedPyObject;
using scaler::utility::pymod::ReleaseGIL;

namespace {

constexpr double millisecondsPerSecond = 1000.0;

std::chrono::milliseconds toMilliseconds(double seconds)
{
    return std::chrono::milliseconds {static_cast<int64_t>(seconds * millisecondsPerSecond)};
}

// a new reference to `module`.`name`, or nullptr with the error set
PyObject* importAttribute(const char* module, const char* name)
{
    OwnedPyObject<> imported {PyImport_ImportModule(module)};
    return imported ? PyObject_GetAttrString(imported.get(), name) : nullptr;
}

bool cachePythonObjects(ModuleState& state)
{
    state._formatException = importAttribute("traceback", "format_exception");
    return state._formatException != nullptr;
}

}  // namespace

extern "C" {

static PyObject* configure(PyObject* /*self*/, PyObject* args)
{
    PyObject* resourceAttributes = nullptr;
    const char* scopeName        = nullptr;
    if (!PyArg_ParseTuple(args, "O!s", &PyDict_Type, &resourceAttributes, &scopeName)) {
        return nullptr;
    }
    ModuleState& state = moduleState();
    if (state._sampler) {
        PyErr_SetString(PyExc_RuntimeError, "native export is already configured");
        return nullptr;
    }

    std::vector<Attribute> attributes {};
    if (!addAttributes(resourceAttributes, attributes) || !cachePythonObjects(state)) {
        return nullptr;
    }

    std::vector<std::string> warnings {};
    Sampler sampler       = Sampler::fromEnvironment(processEnvironment, warnings);
    SpanLimits spanLimits = SpanLimits::fromEnvironment(processEnvironment, warnings);
    LogLimits logLimits   = LogLimits::fromEnvironment(processEnvironment, warnings);
    for (const auto& warning: warnings) {
        logToPython(LogLevel::warning, warning);
    }

    installSDKLogHandler(logToPython);
    auto spans = SpanExporter::create(attributes, scopeName, std::move(spanLimits), logToPython);
    if (!spans) {
        PyErr_Format(PyExc_RuntimeError, "cannot start the span exporter: %s", spans.error().c_str());
        return nullptr;
    }
    auto logs = LogExporter::create(attributes, std::move(logLimits));
    if (!logs) {
        PyErr_Format(PyExc_RuntimeError, "cannot start the log exporter: %s", logs.error().c_str());
        return nullptr;
    }

    state._spans   = std::move(*spans);
    state._logs    = std::move(*logs);
    state._sampler = sampler;
    Py_RETURN_NONE;
}

static PyObject* flush(PyObject* /*self*/, PyObject* args)
{
    double timeoutSeconds = 0;
    if (!PyArg_ParseTuple(args, "d", &timeoutSeconds)) {
        return nullptr;
    }
    ModuleState& state = moduleState();
    if (!state._spans) {
        Py_RETURN_TRUE;
    }

    bool flushed = false;
    {
        ReleaseGIL release {};
        const auto timeout = toMilliseconds(timeoutSeconds);
        const bool spans   = state._spans->flush(timeout);
        const bool logs    = state._logs->flush(timeout);
        flushed            = spans && logs;
    }
    return PyBool_FromLong(flushed);
}

static PyObject* shutdown(PyObject* /*self*/, PyObject* args)
{
    double timeoutSeconds = 0;
    if (!PyArg_ParseTuple(args, "d", &timeoutSeconds)) {
        return nullptr;
    }
    ModuleState& state = moduleState();
    if (!state._spans) {
        Py_RETURN_TRUE;
    }

    bool stopped = false;
    {
        ReleaseGIL release {};
        const auto timeout = toMilliseconds(timeoutSeconds);
        const bool spans   = state._spans->shutdown(timeout);
        const bool logs    = state._logs->shutdown(timeout);
        stopped            = spans && logs;
    }
    return PyBool_FromLong(stopped);
}

static PyMethodDef NativeExportMethods[] = {
    {"configure",
     (PyCFunction)configure,
     METH_VARARGS,
     "configure(resource_attributes, scope_name): start the span and log exporters, configured by the OTEL_* "
     "variables."},
    {"start_span",
     (PyCFunction)startSpan,
     METH_VARARGS,
     "start_span(parent_sampled, parent_trace_id_low) -> (trace_id_high, trace_id_low, span_id, sampled): new ids "
     "and the decision of the sampler OTEL_TRACES_SAMPLER configures; parent_sampled is -1 for a root span."},
    {"export_span",
     (PyCFunction)exportSpan,
     METH_VARARGS,
     "export_span(trace_id, span_id, parent_span_id, trace_state, name, kind, start_unix_nano, end_unix_nano, "
     "status_code, status_message, attributes, events, links): queue a finished, sampled span."},
    {"export_log",
     (PyCFunction)exportLog,
     METH_VARARGS,
     "export_log(record, body, span_context): queue a logging.LogRecord; body is the formatted message, or None."},
    {"flush",
     (PyCFunction)flush,
     METH_VARARGS,
     "flush(timeout_seconds) -> bool: wait, without the GIL, until every queued span and log record is exported."},
    {"shutdown",
     (PyCFunction)shutdown,
     METH_VARARGS,
     "shutdown(timeout_seconds) -> bool: export what is queued, then stop the exporters."},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef native_export_module = {
    .m_base     = PyModuleDef_HEAD_INIT,
    .m_name     = "native_export",
    .m_doc      = PyDoc_STR("Spans and logs exported with opentelemetry-cpp, encoded and sent without the GIL."),
    .m_size     = 0,
    .m_methods  = NativeExportMethods,
    .m_slots    = nullptr,
    .m_traverse = nullptr,
    .m_clear    = nullptr,
    .m_free     = nullptr,
};

}  // extern "C"

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler

PyMODINIT_FUNC PyInit_native_export(void)
{
    using scaler::tracing::pymod::native_export_module;
    return PyModule_Create(&native_export_module);
}
