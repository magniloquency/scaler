#pragma once

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "scaler/tracing/span_record.h"
#include "scaler/utility/pymod/compatibility.h"

namespace scaler {
namespace tracing {
namespace pymod {

// Each returns false, or nullopt, with a Python error set, when `object` cannot be converted.
std::optional<std::string> toString(PyObject* object);

// str, bool, int, and float keep their type; any other value becomes its str(), as the Python SDK exports it
std::optional<AttributeValue> toAttributeValue(PyObject* value);

// Adds the entries of a mapping, or nothing for None, replacing an attribute of the same key as a dict would.
bool addAttributes(PyObject* mapping, std::vector<Attribute>& attributes);
bool setAttribute(PyObject* key, PyObject* value, std::vector<Attribute>& attributes);

// a 128-bit trace id or 64-bit span id held in a Python int, as opentelemetry.trace.SpanContext holds them
bool toTraceID(PyObject* integer, TraceID& traceID);
bool toSpanID(PyObject* integer, SpanID& spanID);

// an id passed as big-endian bytes, as the Python provider passes them
template <size_t Size>
bool toID(PyObject* bytes, std::array<uint8_t, Size>& id)
{
    if (!PyBytes_Check(bytes) || PyBytes_GET_SIZE(bytes) != static_cast<Py_ssize_t>(Size)) {
        PyErr_Format(PyExc_ValueError, "an id must be %zu bytes", Size);
        return false;
    }
    std::copy_n(reinterpret_cast<const uint8_t*>(PyBytes_AS_STRING(bytes)), Size, id.begin());
    return true;
}

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
