#pragma once

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <atomic>
#include <chrono>
#include <thread>

namespace scaler {
namespace utility {
namespace pymod {

// Longest interpreter exit is held up waiting for threads that already passed the shutdown check.
// They only have a short callback and a PyGILState_Release() left to run, so this is generous;
// anything slower is a bug elsewhere and must not be allowed to wedge the exit.
constexpr std::chrono::milliseconds GIL_DRAIN_TIMEOUT {1000};

// How often awaitGILAcquirersDrained() re-reads the counter. Short enough that the common case (an
// empty counter, or one callback already on its way out) adds nothing measurable to exit.
constexpr std::chrono::microseconds GIL_DRAIN_POLL_INTERVAL {200};

// Set to true once the interpreter has begun shutting down.
//
// From that point on, CPython (up to and including 3.13) kills any non-Python thread that calls
// PyGILState_Ensure(), by way of pthread_exit(). A forced unwind through our noexcept event loop frames aborts
// the process; even where it does not, the thread disappears without completing whatever the Python side is
// blocked on. The flag is set from an atexit callback, which runs before CPython arms that behaviour.
//
// Reading the flag is not on its own enough to be safe: a thread can read `false` and then be descheduled
// before it reaches PyGILState_Ensure(), by which point the kill may be armed. See gilAcquirersInFlight().
inline std::atomic<bool>& interpreterIsShuttingDown() noexcept
{
    static std::atomic<bool> shuttingDown {false};
    return shuttingDown;
}

// Number of threads currently between the shutdown check in AcquireGIL and the matching
// PyGILState_Release(), i.e. inside the window where being killed would be fatal.
//
// CPython arms the kill in _PyRuntimeState_SetFinalizing(), which runs just after _PyAtExit_Call() returns.
// The shutdown hook therefore sets the flag and then waits here until the window is empty, so it never
// returns while a thread is inside it, and the kill is armed only once nobody can be hit by it.
//
// Correctness rests on one property: a thread that read the flag as `false` is always counted. The increment
// happens before the flag is read, and the sequentially consistent ordering on both sides puts all four
// operations in a single total order, so if this thread's read misses the hook's store then the hook's read
// cannot miss this thread's increment.
inline std::atomic<int>& gilAcquirersInFlight() noexcept
{
    static std::atomic<int> inFlight {0};
    return inFlight;
}

// Waits for every thread already past the shutdown check to finish with the GIL. The caller must not hold
// the GIL: the threads being waited on need it to make progress.
//
// Returns false if `timeout` elapsed first, which leaves whoever is still in flight exposed to the race this
// is meant to close. That is the deliberate trade against an unbounded wait, which would turn a rare crash
// into a guaranteed hang whenever a callback (a __del__ reached through Py_CLEAR, say) fails to return.
inline bool awaitGILAcquirersDrained(std::chrono::milliseconds timeout) noexcept
{
    const auto deadline = std::chrono::steady_clock::now() + timeout;

    while (gilAcquirersInFlight().load(std::memory_order_seq_cst) != 0) {
        if (std::chrono::steady_clock::now() >= deadline)
            return false;

        std::this_thread::sleep_for(GIL_DRAIN_POLL_INTERVAL);
    }

    return true;
}

// Acquires the GIL, unless the interpreter is shutting down, in which case acquiring it would kill the calling
// thread. Callers must check `acquired()` before touching any Python state.
class AcquireGIL {
public:
    AcquireGIL()
    {
        // Must precede the flag read, and must be sequentially consistent on both sides: this is what lets
        // the shutdown hook know that this thread is about to ask for the GIL. See gilAcquirersInFlight().
        gilAcquirersInFlight().fetch_add(1, std::memory_order_seq_cst);

        if (interpreterIsShuttingDown().load(std::memory_order_seq_cst)) {
            gilAcquirersInFlight().fetch_sub(1, std::memory_order_seq_cst);
            return;
        }

        _state    = PyGILState_Ensure();
        _acquired = true;
    }

    ~AcquireGIL()
    {
        if (!_acquired)
            return;

        // The decrement belongs strictly after the release, not before it. PyGILState_Release() re-enters
        // Python -- PyThreadState_Clear() can run destructors, and _PyThreadState_DeleteCurrent() unbinds the
        // thread state -- so leaving the window early would let finalization start underneath it.
        PyGILState_Release(_state);
        gilAcquirersInFlight().fetch_sub(1, std::memory_order_seq_cst);
    }

    AcquireGIL(const AcquireGIL&)            = delete;
    AcquireGIL& operator=(const AcquireGIL&) = delete;
    AcquireGIL(AcquireGIL&&)                 = delete;
    AcquireGIL& operator=(AcquireGIL&&)      = delete;

    bool acquired() const noexcept
    {
        return _acquired;
    }

private:
    bool _acquired {false};
    PyGILState_STATE _state {};
};

}  // namespace pymod
}  // namespace utility
}  // namespace scaler
