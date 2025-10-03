#include "scaler/io/ymq/pymod_ymq/python.h"

class Gil {
public:
    static Gil acquire() { return Gil(PyGILState_Ensure()); }

    ~Gil() { PyGILState_Release(_state); }

private:
    Gil(PyGILState_STATE state): _state(state) {}

    PyGILState_STATE _state;
};
