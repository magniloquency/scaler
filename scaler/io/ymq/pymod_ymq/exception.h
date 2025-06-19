#pragma once

#include <Python.h>
#include <structmember.h>

#include "scaler/io/ymq/pymod_ymq/ymq.h"

typedef struct {
    PyObject_HEAD;
    PyObject* error;
} YmqException;

extern "C" {

static int YmqException_init(YmqException* self, PyObject* args, PyObject* kwds) {
    PyObject* error             = nullptr;
    static const char* kwlist[] = {"error", nullptr};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O", (char**)kwlist, &error))
        return -1;

    // replace with PyType_GetModuleByDef(Py_TYPE(self), &ymq_module) in a newer Python version
    // https://docs.python.org/3/c-api/type.html#c.PyType_GetModuleByDef
    PyObject* module = PyType_GetModule(Py_TYPE(self));
    if (!module) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get module for Message type");
        return -1;
    }

    auto state = (YmqState*)PyModule_GetState(module);
    if (!state) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get module state");
        return -1;
    }

    if (!PyObject_IsInstance(error, state->errorEnum)) {
        PyErr_SetString(PyExc_TypeError, "expected a value of type Error");
        return -1;
    }

    Py_XINCREF(error);
    Py_XDECREF(self->error);
    self->error = error;
    return 0;
}
static PyObject* YmqException_new(PyTypeObject* type, PyObject* args, PyObject* kwds) {
    YmqException* self = (YmqException*)type->tp_alloc(type, 0);

    if (self) {
        self->error = nullptr;
    }

    return (PyObject*)self;
}
static void YmqException_dealloc(YmqException* self) {
    Py_XDECREF(self->error);
    Py_TYPE(self)->tp_free((PyObject*)self);
}
}

static PyMemberDef YmqException_members[] = {
    {"error", T_OBJECT_EX, offsetof(YmqException, error), 0, "error code"}, {nullptr}};

static PyType_Slot YmqException_slots[] = {
    {Py_tp_base, (void*)PyExc_Exception},  // Will be set at runtime
    {Py_tp_init, (void*)YmqException_init},
    {Py_tp_new, (void*)YmqException_new},
    {Py_tp_dealloc, (void*)YmqException_dealloc},
    {Py_tp_members, (void*)YmqException_members},
    {0, 0}};

static PyType_Spec YmqException_spec = {
    "ymq.Exception", sizeof(YmqException), 0, Py_TPFLAGS_DEFAULT, YmqException_slots};
