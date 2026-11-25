#pragma once

#include "scaler/utility/pymod/compatibility.h"

namespace scaler {
namespace tracing {
namespace pymod {

// start_span(parent_sampled, parent_trace_id_low) -> (trace_id_high, trace_id_low, span_id, sampled): new ids and the
// sampler's decision; parent_sampled is -1 for a root span, else the parent's sampled flag as 0 or 1
PyObject* startSpan(PyObject* self, PyObject* args);

// export_span(trace_id, span_id, parent_span_id, trace_state, name, kind, start_unix_nano, end_unix_nano,
// status_code, status_message, attributes, events, links): queues a finished, sampled span
PyObject* exportSpan(PyObject* self, PyObject* args);

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
