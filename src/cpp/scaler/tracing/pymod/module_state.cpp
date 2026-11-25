#include "scaler/tracing/pymod/module_state.h"

#include <chrono>

namespace scaler {
namespace tracing {
namespace pymod {

using scaler::utility::pymod::AcquireGIL;
using scaler::utility::pymod::OwnedPyObject;

namespace {

// Python's numbers for the logging levels logToPython() uses
constexpr int pythonLoggingError   = 40;
constexpr int pythonLoggingWarning = 30;

}  // namespace

ModuleState& moduleState()
{
    static ModuleState state {};
    return state;
}

void logToPython(LogLevel level, std::string_view message)
{
    AcquireGIL gil {};
    if (!gil.acquired()) {
        return;
    }

    PyObject* type      = nullptr;
    PyObject* value     = nullptr;
    PyObject* traceback = nullptr;
    PyErr_Fetch(&type, &value, &traceback);  // a pending error of the calling thread survives the log call

    OwnedPyObject<> logging {PyImport_ImportModule("logging")};
    OwnedPyObject<> logger {
        logging ? PyObject_CallMethod(logging.get(), "getLogger", "s", exporterLoggerName) : nullptr};
    const int pythonLevel = level == LogLevel::error ? pythonLoggingError : pythonLoggingWarning;
    OwnedPyObject<> logged {
        logger ? PyObject_CallMethod(
                     logger.get(), "log", "is#", pythonLevel, message.data(), static_cast<Py_ssize_t>(message.size())) :
                 nullptr};
    if (!logged) {
        PyErr_Clear();
    }

    PyErr_Restore(type, value, traceback);
}

uint64_t nowUnixNano()
{
    return static_cast<uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch())
            .count());
}

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
