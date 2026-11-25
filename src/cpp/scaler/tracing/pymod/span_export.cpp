#include "scaler/tracing/pymod/span_export.h"

#include <cstdint>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "scaler/tracing/pymod/conversion.h"
#include "scaler/tracing/pymod/module_state.h"
#include "scaler/tracing/span_ids.h"
#include "scaler/tracing/span_record.h"

namespace scaler {
namespace tracing {
namespace pymod {

namespace {

// start_span()'s parent_sampled argument for a root span
constexpr int noParent = -1;

// `events` is None or a list of (name, time_unix_nano, attributes) tuples
bool toEvents(PyObject* events, std::vector<SpanEvent>& result)
{
    if (events == Py_None) {
        return true;
    }
    if (!PyList_Check(events)) {
        PyErr_SetString(PyExc_TypeError, "events must be a list or None");
        return false;
    }

    const Py_ssize_t eventCount = PyList_GET_SIZE(events);
    result.reserve(static_cast<size_t>(eventCount));
    for (Py_ssize_t event_i = 0; event_i < eventCount; ++event_i) {
        PyObject* name                  = nullptr;
        unsigned long long timeUnixNano = 0;
        PyObject* attributes            = nullptr;
        if (!PyArg_ParseTuple(PyList_GET_ITEM(events, event_i), "UKO", &name, &timeUnixNano, &attributes)) {
            return false;
        }

        SpanEvent event {._name = {}, ._timeUnixNano = timeUnixNano, ._attributes = {}};
        auto nameText = toString(name);
        if (!nameText || !addAttributes(attributes, event._attributes)) {
            return false;
        }
        event._name = std::move(*nameText);
        result.push_back(std::move(event));
    }
    return true;
}

// `links` is None or a list of (trace_id, span_id, trace_state, attributes) tuples
bool toLinks(PyObject* links, std::vector<SpanLink>& result)
{
    if (links == Py_None) {
        return true;
    }
    if (!PyList_Check(links)) {
        PyErr_SetString(PyExc_TypeError, "links must be a list or None");
        return false;
    }

    const Py_ssize_t linkCount = PyList_GET_SIZE(links);
    result.reserve(static_cast<size_t>(linkCount));
    for (Py_ssize_t link_i = 0; link_i < linkCount; ++link_i) {
        PyObject* traceID    = nullptr;
        PyObject* spanID     = nullptr;
        PyObject* traceState = nullptr;
        PyObject* attributes = nullptr;
        if (!PyArg_ParseTuple(PyList_GET_ITEM(links, link_i), "SSUO", &traceID, &spanID, &traceState, &attributes)) {
            return false;
        }

        SpanLink link {._traceID = {}, ._spanID = {}, ._traceState = {}, ._attributes = {}};
        auto traceStateText = toString(traceState);
        if (!toID(traceID, link._traceID) || !toID(spanID, link._spanID) || !traceStateText ||
            !addAttributes(attributes, link._attributes)) {
            return false;
        }
        link._traceState = std::move(*traceStateText);
        result.push_back(std::move(link));
    }
    return true;
}

}  // namespace

PyObject* startSpan(PyObject* /*self*/, PyObject* args)
{
    int parentSampled                   = noParent;
    unsigned long long parentTraceIDLow = 0;
    if (!PyArg_ParseTuple(args, "iK", &parentSampled, &parentTraceIDLow)) {
        return nullptr;
    }
    const ModuleState& state = moduleState();
    if (!state._sampler) {
        PyErr_SetString(PyExc_RuntimeError, "native export is not configured");
        return nullptr;
    }

    // a root span starts a trace; a child keeps its parent's, so its high and low halves come back as 0
    const bool isRoot          = parentSampled == noParent;
    const uint64_t traceIDHigh = isRoot ? generateID() : 0;
    const uint64_t traceIDLow  = isRoot ? generateID() : 0;
    const uint64_t spanID      = generateID();
    const bool sampled         = state._sampler->shouldSample(
        isRoot ? std::nullopt : std::optional<bool> {parentSampled != 0}, isRoot ? traceIDLow : parentTraceIDLow);

    return Py_BuildValue(
        "(KKKO)",
        static_cast<unsigned long long>(traceIDHigh),
        static_cast<unsigned long long>(traceIDLow),
        static_cast<unsigned long long>(spanID),
        sampled ? Py_True : Py_False);
}

PyObject* exportSpan(PyObject* /*self*/, PyObject* args)
{
    PyObject* traceID                = nullptr;
    PyObject* spanID                 = nullptr;
    PyObject* parentSpanID           = nullptr;
    PyObject* traceState             = nullptr;
    PyObject* name                   = nullptr;
    int kind                         = 0;
    unsigned long long startUnixNano = 0;
    unsigned long long endUnixNano   = 0;
    int statusCode                   = 0;
    PyObject* statusMessage          = nullptr;
    PyObject* attributes             = nullptr;
    PyObject* events                 = nullptr;
    PyObject* links                  = nullptr;
    if (!PyArg_ParseTuple(
            args,
            "SSOUUiKKiUOOO",
            &traceID,
            &spanID,
            &parentSpanID,
            &traceState,
            &name,
            &kind,
            &startUnixNano,
            &endUnixNano,
            &statusCode,
            &statusMessage,
            &attributes,
            &events,
            &links)) {
        return nullptr;
    }
    ModuleState& state = moduleState();
    if (!state._spans) {
        PyErr_SetString(PyExc_RuntimeError, "native export is not configured");
        return nullptr;
    }

    SpanRecord span {
        ._traceID           = {},
        ._spanID            = {},
        ._parentSpanID      = std::nullopt,
        ._traceState        = {},
        ._name              = {},
        ._kind              = kind,
        ._startTimeUnixNano = startUnixNano,
        ._endTimeUnixNano   = endUnixNano,
        ._statusCode        = statusCode,
        ._statusMessage     = {},
        ._attributes        = {},
        ._events            = {},
        ._links             = {},
    };
    if (!toID(traceID, span._traceID) || !toID(spanID, span._spanID)) {
        return nullptr;
    }
    if (parentSpanID != Py_None) {
        SpanID parent {};
        if (!toID(parentSpanID, parent)) {
            return nullptr;
        }
        span._parentSpanID = parent;
    }

    auto traceStateText = toString(traceState);
    auto nameText       = toString(name);
    auto messageText    = toString(statusMessage);
    if (!traceStateText || !nameText || !messageText || !addAttributes(attributes, span._attributes) ||
        !toEvents(events, span._events) || !toLinks(links, span._links)) {
        return nullptr;
    }
    span._traceState    = std::move(*traceStateText);
    span._name          = std::move(*nameText);
    span._statusMessage = std::move(*messageText);

    state._spans->exportSpan(std::move(span));  // queues it: the handover thread builds the SDK's span
    Py_RETURN_NONE;
}

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
