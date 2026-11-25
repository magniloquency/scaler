#include "scaler/tracing/pymod/log.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

#include "scaler/tracing/log_record.h"
#include "scaler/tracing/pymod/conversion.h"
#include "scaler/tracing/pymod/module_state.h"

namespace scaler {
namespace tracing {
namespace pymod {

using scaler::utility::pymod::OwnedPyObject;

namespace {

constexpr double nanosecondsPerSecond = 1e9;

// opentelemetry.trace.TraceFlags.SAMPLED
constexpr long sampledFlag = 0x01;

// the first dropped record is logged, then every this many
constexpr uint64_t droppedLogInterval = 1000;

// std_to_otel in the Python SDK: levels 10 to 53 map to DEBUG to FATAL4, each level of ten to four severities
constexpr long lowestMappedLevel  = 10;
constexpr long highestMappedLevel = 53;
constexpr long levelsPerSeverity  = 10;
constexpr int severitiesPerLevel  = 4;
constexpr int lastSeverityOffset  = 3;
constexpr int unspecifiedSeverity = 0;
constexpr int debugSeverity       = 5;
constexpr int highestSeverity     = 24;

// the LogRecord fields the Python SDK leaves out of the attributes
constexpr std::array<std::string_view, 24> reservedAttributes {
    "args",      "asctime", "created",     "exc_info",        "exc_text",   "filename", "funcName", "getMessage",
    "levelname", "levelno", "lineno",      "message",         "module",     "msecs",    "msg",      "name",
    "pathname",  "process", "processName", "relativeCreated", "stack_info", "taskName", "thread",   "threadName",
};

std::atomic<uint64_t> droppedCount {0};

int severityNumber(long levelno)
{
    if (levelno < lowestMappedLevel) {
        return unspecifiedSeverity;
    }
    if (levelno > highestMappedLevel) {
        return highestSeverity;
    }
    const long offset     = levelno - lowestMappedLevel;
    const int withinLevel = static_cast<int>(std::min<long>(offset % levelsPerSeverity, lastSeverityOffset));
    return debugSeverity + severitiesPerLevel * static_cast<int>(offset / levelsPerSeverity) + withinLevel;
}

bool isReserved(std::string_view name)
{
    for (std::string_view reserved: reservedAttributes) {
        if (reserved == name) {
            return true;
        }
    }
    return false;
}

bool setStringAttribute(const char* key, PyObject* value, std::vector<Attribute>& attributes)
{
    OwnedPyObject<> keyObject {PyUnicode_FromString(key)};
    return keyObject && setAttribute(keyObject.get(), value, attributes);
}

// the SDK's rule: an object logged with no arguments is the body itself, else the formatted message
std::optional<AttributeValue> recordBody(PyObject* record)
{
    OwnedPyObject<> message {PyObject_GetAttrString(record, "msg")};
    OwnedPyObject<> arguments {PyObject_GetAttrString(record, "args")};
    if (!message || !arguments) {
        return std::nullopt;
    }
    if (!PyObject_IsTrue(arguments.get()) && !PyUnicode_Check(message.get())) {
        return toAttributeValue(message.get());
    }
    OwnedPyObject<> formatted {PyObject_CallMethod(record, "getMessage", nullptr)};
    if (!formatted) {
        return std::nullopt;
    }
    return toAttributeValue(formatted.get());
}

bool addRecordAttributes(PyObject* record, std::vector<Attribute>& attributes)
{
    OwnedPyObject<> fields {PyObject_GetAttrString(record, "__dict__")};
    if (!fields) {
        return false;
    }
    PyObject* key      = nullptr;
    PyObject* value    = nullptr;
    Py_ssize_t entry_i = 0;
    while (PyDict_Next(fields.get(), &entry_i, &key, &value)) {
        auto name = toString(key);
        if (!name) {
            return false;
        }
        if (!isReserved(*name) && !setAttribute(key, value, attributes)) {
            return false;
        }
    }

    OwnedPyObject<> pathname {PyObject_GetAttrString(record, "pathname")};
    OwnedPyObject<> function {PyObject_GetAttrString(record, "funcName")};
    OwnedPyObject<> line {PyObject_GetAttrString(record, "lineno")};
    if (!pathname || !function || !line || !setStringAttribute("code.file.path", pathname.get(), attributes) ||
        !setStringAttribute("code.function.name", function.get(), attributes) ||
        !setStringAttribute("code.line.number", line.get(), attributes)) {
        return false;
    }

    OwnedPyObject<> exceptionInfo {PyObject_GetAttrString(record, "exc_info")};
    if (!exceptionInfo) {
        return false;
    }
    if (!PyTuple_Check(exceptionInfo.get()) || PyTuple_GET_SIZE(exceptionInfo.get()) != 3) {
        return true;
    }

    PyObject* exceptionType = PyTuple_GET_ITEM(exceptionInfo.get(), 0);
    PyObject* exception     = PyTuple_GET_ITEM(exceptionInfo.get(), 1);
    PyObject* traceback     = PyTuple_GET_ITEM(exceptionInfo.get(), 2);
    if (exceptionType != Py_None) {
        OwnedPyObject<> typeName {PyObject_GetAttrString(exceptionType, "__name__")};
        if (!typeName || !setStringAttribute("exception.type", typeName.get(), attributes)) {
            return false;
        }
    }
    if (exception != Py_None) {
        OwnedPyObject<> exceptionArguments {PyObject_GetAttrString(exception, "args")};
        if (!exceptionArguments) {
            return false;
        }
        if (PyTuple_Check(exceptionArguments.get()) && PyTuple_GET_SIZE(exceptionArguments.get()) > 0) {
            OwnedPyObject<> message {PyObject_Str(PyTuple_GET_ITEM(exceptionArguments.get(), 0))};
            if (!message || !setStringAttribute("exception.message", message.get(), attributes)) {
                return false;
            }
        }
    }
    if (traceback != Py_None) {
        OwnedPyObject<> lines {
            PyObject_CallFunctionObjArgs(moduleState()._formatException, exceptionType, exception, traceback, nullptr)};
        OwnedPyObject<> separator {PyUnicode_FromString("")};
        OwnedPyObject<> stacktrace {lines && separator ? PyUnicode_Join(separator.get(), lines.get()) : nullptr};
        if (!stacktrace || !setStringAttribute("exception.stacktrace", stacktrace.get(), attributes)) {
            return false;
        }
    }
    return true;
}

bool readSpanContext(PyObject* spanContext, std::optional<LogSpanContext>& result)
{
    OwnedPyObject<> valid {PyObject_GetAttrString(spanContext, "is_valid")};
    if (!valid) {
        return false;
    }
    if (!PyObject_IsTrue(valid.get())) {
        return true;
    }

    OwnedPyObject<> traceIDInt {PyObject_GetAttrString(spanContext, "trace_id")};
    OwnedPyObject<> spanIDInt {PyObject_GetAttrString(spanContext, "span_id")};
    OwnedPyObject<> flags {PyObject_GetAttrString(spanContext, "trace_flags")};
    LogSpanContext context {};
    if (!traceIDInt || !spanIDInt || !flags || !toTraceID(traceIDInt.get(), context._traceID) ||
        !toSpanID(spanIDInt.get(), context._spanID)) {
        return false;
    }
    context._sampled = (PyLong_AsLong(flags.get()) & sampledFlag) != 0;
    result           = context;
    return true;
}

}  // namespace

PyObject* exportLog(PyObject* /*self*/, PyObject* args)
{
    PyObject* record      = nullptr;
    PyObject* body        = nullptr;
    PyObject* spanContext = nullptr;
    if (!PyArg_ParseTuple(args, "OOO", &record, &body, &spanContext)) {
        return nullptr;
    }
    ModuleState& module = moduleState();
    if (!module._logs) {
        PyErr_SetString(PyExc_RuntimeError, "native export is not configured");
        return nullptr;
    }

    OwnedPyObject<> created {PyObject_GetAttrString(record, "created")};
    OwnedPyObject<> levelno {PyObject_GetAttrString(record, "levelno")};
    OwnedPyObject<> name {PyObject_GetAttrString(record, "name")};
    if (!created || !levelno || !name) {
        return nullptr;
    }

    LogRecord logRecord {};
    logRecord._timeUnixNano         = static_cast<uint64_t>(PyFloat_AsDouble(created.get()) * nanosecondsPerSecond);
    logRecord._observedTimeUnixNano = nowUnixNano();
    logRecord._severityNumber       = severityNumber(PyLong_AsLong(levelno.get()));
    if (PyErr_Occurred()) {
        return nullptr;
    }

    auto scopeName = toString(name.get());
    auto bodyValue = body == Py_None ? recordBody(record) : toAttributeValue(body);
    if (!scopeName || !bodyValue || !addRecordAttributes(record, logRecord._attributes) ||
        !readSpanContext(spanContext, logRecord._spanContext)) {
        return nullptr;
    }
    logRecord._scopeName = std::move(*scopeName);
    logRecord._body      = std::move(*bodyValue);

    if (!module._logs->exportLog(std::move(logRecord))) {
        const uint64_t dropped = ++droppedCount;
        if (dropped == 1 || dropped % droppedLogInterval == 0) {
            logToPython(
                LogLevel::warning,
                "dropped " + std::to_string(dropped) + " log record(s): the export queue is full or shut down");
        }
    }
    Py_RETURN_NONE;
}

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
