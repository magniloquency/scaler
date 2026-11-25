#pragma once

#include "scaler/utility/pymod/compatibility.h"

namespace scaler {
namespace tracing {
namespace pymod {

// export_log(record, body, span_context): queues a logging.LogRecord, translated as the Python SDK's LoggingHandler
// translates it; `body` is the formatted message when the handler has a formatter, else None
PyObject* exportLog(PyObject* self, PyObject* args);

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
