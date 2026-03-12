# Amendment 2: Post-Review Fixes

| Field | Value |
|---|---|
| Pull Request | #583 |
| Amends | [amendment-1.md](amendment-1.md) |

**Status**: Implemented

This amendment addresses six issues identified during code review of the implementation described in amendment 1.

1. **Signal handling in `_run_fixed()`** — FIXED mode had no SIGTERM/SIGINT handlers, risking orphaned worker subprocesses on shutdown.
2. **`register_event_loop` missing from FIXED path** — The old `cluster.py` entry point called `register_event_loop` before starting workers; neither `_run_fixed()` nor the new `cluster.py` did.
3. **`configure_parser` missing type hint** — `parser` parameter was untyped, violating the project's type-annotation requirement.
4. **Startup ordering in `combo.py`** — The worker manager process was started before the scheduler, requiring workers to retry their initial connection.
5. **ECS `worker_ids` removal** — `WorkerGroupInfo.worker_ids` was removed without explanation; confirmed safe since the field was computed but never consumed.
6. **`_ident` not initialized in `__init__`** — The attribute was set only in `_setup_zmq()`, leaving it absent on the object until `run()` was called.

---

## Fix 1 & 2 — Signal handling and `register_event_loop` in `_run_fixed()`

**File:** `src/scaler/worker_manager_adapter/baremetal/native.py`

Both fixes live in `_run_fixed()`. Install SIGTERM/SIGINT handlers before the join loop; call `register_event_loop` at the top of the method.

On signal the handler terminates all living workers. Execution then resumes at the interrupted `worker.join()`, which returns promptly since the worker is now terminating. The join loop drains the remaining workers naturally — no `SystemExit` or flag needed.

```python
def _run_fixed(self) -> None:
    setup_logger(self._logging_paths, self._logging_config_file, self._logging_level)
    register_event_loop(self._event_loop)
    self._spawn_initial_workers()

    def _on_signal(sig: int, frame: object) -> None:
        logging.info("NativeWorkerManager (FIXED): received signal %d, terminating workers", sig)
        for group in self._worker_groups.values():
            for worker in group.values():
                if worker.is_alive():
                    worker.terminate()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    for group in self._worker_groups.values():
        for worker in group.values():
            worker.join()
```

---

## Fix 3 — `configure_parser` type hint

**File:** `src/scaler/config/section/native_worker_manager.py`

```python
# Before
@classmethod
def configure_parser(cls, parser) -> None:

# After
@classmethod
def configure_parser(cls, parser: argparse.ArgumentParser) -> None:
```

`argparse` is already imported.

---

## Fix 4 — Startup ordering in `combo.py`

**File:** `src/scaler/cluster/combo.py`

Start the scheduler before the worker manager so workers connect to a ready scheduler on first attempt.

```python
# Before
self._worker_manager_process.start()
self._scheduler.start()

# After
self._scheduler.start()
self._worker_manager_process.start()
```

Object storage is already up (`wait_until_ready()` was called earlier), so the scheduler can start safely.

---

## Fix 5 — ECS `WorkerGroupInfo` comment

**File:** `src/scaler/worker_manager_adapter/aws_raw/ecs.py`

`WorkerGroupInfo.worker_ids` was removed in amendment 1 because it was computed but never consumed (`shutdown_worker_group` uses only `task_arn`). Add a comment to make the narrow scope explicit and prevent future re-introduction.

```python
@dataclass
class WorkerGroupInfo:
    task_arn: str  # sufficient to identify the group for stop_task(); no worker ID tracking needed
```

---

## Fix 6 — Initialize `_ident` in `__init__`

**File:** `src/scaler/worker_manager_adapter/baremetal/native.py`

`_ident` is set in `_setup_zmq()` (DYNAMIC path only) but referenced in `__destroy()` and `start_worker_group()`. Initialize it to `None` alongside the other deferred ZMQ attributes.

```python
# ZMQ setup is deferred to _setup_zmq(), called at the start of run().
# This keeps the object picklable so callers can do Process(target=adapter.run).start().
self._context: Optional[Any] = None
self._connector_external: Optional[AsyncConnector] = None
self._ident: Optional[bytes] = None
```

---

## Files Modified

| File | Change |
|---|---|
| `src/scaler/worker_manager_adapter/baremetal/native.py` | `_run_fixed()`: signal handlers + `register_event_loop`; `__init__`: initialize `_ident` |
| `src/scaler/config/section/native_worker_manager.py` | Type hint on `configure_parser` |
| `src/scaler/cluster/combo.py` | Swap scheduler/worker-manager start order |
| `src/scaler/worker_manager_adapter/aws_raw/ecs.py` | Clarifying comment on `WorkerGroupInfo` |

---

## Verification

```bash
# Formatting
isort --check src/ tests/ examples/
black --check src/ tests/ examples/

# Linting
pflake8 src/ tests/ examples/

# Type checking
mypy src/ tests/ examples/

# Run affected tests
python -m unittest \
    tests/client/test_client.py \
    tests/scheduler/test_balance.py \
    tests/scheduler/test_capabilities.py \
    tests/cluster/test_cluster_disconnect.py \
    tests/core/test_death_timeout.py

# Smoke-test signal handling
scaler_cluster tcp://127.0.0.1:2345 --max-workers 2 &
PID=$!
sleep 2
kill -TERM $PID
wait $PID   # should return promptly with no zombie workers
```
