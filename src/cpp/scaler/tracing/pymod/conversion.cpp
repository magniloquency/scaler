#include "scaler/tracing/pymod/conversion.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace scaler {
namespace tracing {
namespace pymod {

using scaler::utility::pymod::OwnedPyObject;

namespace {

constexpr int bitsPerByte  = 8;
constexpr int bitsPerHalf  = 64;
constexpr size_t halfBytes = sizeof(uint64_t);

void writeBigEndian(uint64_t value, uint8_t* destination)
{
    for (size_t byte_i = halfBytes; byte_i > 0; --byte_i) {
        destination[byte_i - 1] = static_cast<uint8_t>(value);
        value >>= bitsPerByte;
    }
}

}  // namespace

std::optional<std::string> toString(PyObject* object)
{
    Py_ssize_t size  = 0;
    const char* utf8 = PyUnicode_AsUTF8AndSize(object, &size);
    if (utf8 == nullptr) {
        return std::nullopt;
    }
    return std::string {utf8, static_cast<size_t>(size)};
}

std::optional<AttributeValue> toAttributeValue(PyObject* value)
{
    if (PyUnicode_Check(value)) {
        auto text = toString(value);
        if (!text) {
            return std::nullopt;
        }
        return AttributeValue {std::move(*text)};
    }
    if (PyBool_Check(value)) {  // before int: a Python bool is an int
        return AttributeValue {value == Py_True};
    }
    if (PyLong_Check(value)) {
        const long long integer = PyLong_AsLongLong(value);
        if (PyErr_Occurred()) {
            return std::nullopt;
        }
        return AttributeValue {static_cast<int64_t>(integer)};
    }
    if (PyFloat_Check(value)) {
        return AttributeValue {PyFloat_AsDouble(value)};
    }

    OwnedPyObject<> text {PyObject_Str(value)};
    if (!text) {
        return std::nullopt;
    }
    auto converted = toString(text.get());
    if (!converted) {
        return std::nullopt;
    }
    return AttributeValue {std::move(*converted)};
}

bool setAttribute(PyObject* key, PyObject* value, std::vector<Attribute>& attributes)
{
    auto keyText        = toString(key);
    auto attributeValue = toAttributeValue(value);
    if (!keyText || !attributeValue) {
        return false;
    }

    auto existing = std::find_if(attributes.begin(), attributes.end(), [&keyText](const Attribute& attribute) {
        return attribute._key == *keyText;
    });
    if (existing != attributes.end()) {
        existing->_value = std::move(*attributeValue);
        return true;
    }
    attributes.push_back({._key = std::move(*keyText), ._value = std::move(*attributeValue)});
    return true;
}

bool addAttributes(PyObject* mapping, std::vector<Attribute>& attributes)
{
    if (mapping == Py_None) {
        return true;
    }

    if (PyDict_Check(mapping)) {
        PyObject* key      = nullptr;
        PyObject* value    = nullptr;
        Py_ssize_t entry_i = 0;
        while (PyDict_Next(mapping, &entry_i, &key, &value)) {
            if (!setAttribute(key, value, attributes)) {
                return false;
            }
        }
        return true;
    }

    OwnedPyObject<> items {PyMapping_Items(mapping)};
    if (!items) {
        return false;
    }
    const Py_ssize_t itemCount = PyList_GET_SIZE(items.get());
    for (Py_ssize_t item_i = 0; item_i < itemCount; ++item_i) {
        PyObject* item = PyList_GET_ITEM(items.get(), item_i);
        if (!setAttribute(PyTuple_GET_ITEM(item, 0), PyTuple_GET_ITEM(item, 1), attributes)) {
            return false;
        }
    }
    return true;
}

bool toTraceID(PyObject* integer, TraceID& traceID)
{
    if (!PyLong_Check(integer)) {
        PyErr_SetString(PyExc_TypeError, "a trace id must be an int");
        return false;
    }
    OwnedPyObject<> shift {PyLong_FromLong(bitsPerHalf)};
    OwnedPyObject<> high {shift ? PyNumber_Rshift(integer, shift.get()) : nullptr};
    if (!high) {
        return false;
    }
    const uint64_t highHalf = PyLong_AsUnsignedLongLongMask(high.get());
    const uint64_t lowHalf  = PyLong_AsUnsignedLongLongMask(integer);
    if (PyErr_Occurred()) {
        return false;
    }
    writeBigEndian(highHalf, traceID.data());
    writeBigEndian(lowHalf, traceID.data() + halfBytes);
    return true;
}

bool toSpanID(PyObject* integer, SpanID& spanID)
{
    if (!PyLong_Check(integer)) {
        PyErr_SetString(PyExc_TypeError, "a span id must be an int");
        return false;
    }
    const uint64_t value = PyLong_AsUnsignedLongLongMask(integer);
    if (PyErr_Occurred()) {
        return false;
    }
    writeBigEndian(value, spanID.data());
    return true;
}

}  // namespace pymod
}  // namespace tracing
}  // namespace scaler
