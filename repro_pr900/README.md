# PR 900 repro suite: "long wrapper task dies mid-flight"

Standalone scripts that try to reproduce the reported failure from several independent angles. Each one
submits a pargraph-built graph through `scaler.Client.get()` — the same path the real job took
(pargraph `to_dict()` → dict graph → `GraphTask` → the scheduler's `graph_controller`) — and varies
exactly one property of the workload so a positive result is interpretable.

## What the reported symptoms narrow down

Worker side, at t+5377s:

```
Processor[..]: agent connector stop requested while task_id=.. was in flight;
no task result will be sent, shutting down
```

Scheduler side, ~4s later:

```
graph_controller:on_graph_subtask_result:152: graph b'..': aborting -- subtask b'..' returned 1
```

Reading that against the branch:

- The worker message is `Processor.__log_exit("agent connector stop requested")`, reached from
  `__run_forever`'s `except ymq.SocketStopRequestedError`. `_current_task` is only cleared at the very
  end of `__send_result`, so "in flight" means the processor was somewhere between receiving the task
  and completing the handoff.
- It printed at **WARNING**, which means `_interrupted` was **False**. `_interrupted` is set only by
  `Processor.__interrupt`, the SIGTERM handler. `ProcessorHolder.kill()` sends SIGTERM, and every
  worker-initiated teardown (`on_cancel_task`, `on_failing_processor`, `on_resume_task`,
  `__restart_current_processor`) goes through it. **So the worker agent did not kill this processor** —
  a worker-initiated kill would have logged at DEBUG. Something dropped that socket from underneath.
- An `ObjectStorageException` mid-task logs `"object storage error"` instead, so the storage write in
  `__send_result` step 1 is not where it died.
- The remaining producers of `SocketStopRequestedError` on the processor's own agent connector are in
  `message_connection.cpp`: a send canceled with `UV_ECANCELED`, or the `MessageConnection` destructor
  failing queued sends. Both mean the processor↔agent connection went away *around the handoff*.
- The scheduler's abort 4s later is the worker agent noticing the dead processor and synthesizing a
  failed `TaskResult` (`on_failing_processor` → `ProcessorDiedError`), which the graph controller then
  treats as a whole-graph abort. That is a consequence, not the cause.

The scripts below probe the plausible causes of that connection loss.

## The scripts

| Script | Isolates | Key knobs |
| --- | --- | --- |
| `repro_01_long_final_task.py` | **Wall-clock duration.** Both processor sockets are silent for the whole task; an idle-reaped connection (NLB/NAT/conntrack between the EKS pod and the scheduler host) only surfaces at handoff. Tiny payloads throughout. | `--final-seconds`, `--sweep-seconds`, `--busy` |
| `repro_02_large_result.py` | **Result size.** `__send_result` writes the whole payload as one ymq message (note `MAX_CHUNK_SIZE = 128 MiB` is defined in `YMQSyncObjectStorageConnector` but never used). Sweeps across 2^31 / 2^32. Negligible runtime. | `--sweep-gb`, `--result-gb`, `--client-upload-only` |
| `repro_03_wide_fanin.py` | **Fan-in width and input volume.** The wrapper's inputs are fetched one `get_object` at a time before its function body runs; this is also what PR 900's graph-bookkeeping changes touch. Small result. | `--sweep-fanout`, `--fanout`, `--leaf-mb` |
| `repro_04_memory_peak.py` | **Memory peak**, and whether the monitor reports it correctly. Ramps RSS to a target, holds it, and returns the peak it measured *from inside the task*. Small result. | `--peak-gb`, `--chunk-mb`, `--hold-seconds`, `--sweep-hold` |
| `repro_05_combined.py` | **All of the above at once**, defaults tuned to the reported run (5377s, 15.2 GiB peak, wide fan-in, multi-GB result). | all of the above |
| `repro_06_no_pargraph.py` | **Whether pargraph and the graph controller are involved.** `--mode graph` builds the same shape as a hand-written dict (no pargraph import); `--mode submit` uses plain `Client.submit`, which never creates a `GraphTask`. | `--mode`, plus the shape knobs |

## Running them

```bash
pip install opengris-scaler pargraph numpy psutil

# smoke test locally first (throwaway single-machine cluster, proves the scripts run)
python repro_01_long_final_task.py --local-workers 4 --fanout 4 --leaf-seconds 0.2 --sweep-seconds 3,6

# against the real cluster
export SCALER_ADDRESS=tcp://scheduler-host:2345
python repro_01_long_final_task.py --sweep-seconds 300,400,900,1800,3600,5400 --log-file angle1.log
```

Common options on every script: `--address` / `$SCALER_ADDRESS`, `--object-storage-address`,
`--timeout-seconds`, `--profiling`, `--log-file`, `--repeat`, `--local-workers`.

The scripts must run from this directory (they import `common.py` as a sibling).

## Suggested order

1. **`repro_01` with the duration sweep.** Cheapest decisive result. A clean threshold — everything
   under N minutes passes, everything over fails — points at an idle connection reaper on the pod↔host
   path, and the fix is TCP keepalives on the processor's sockets rather than anything in the graph code.
2. **`repro_02` with a size sweep.** Also cheap. A cliff at a specific size points at the transport.
3. **`repro_03` and `repro_04`.** Width and memory, still without long runtimes.
4. **`repro_05`** if the isolated angles all come back clean — the failure may need the combination.
5. **`repro_06`** once anything reproduces, to strip pargraph and/or the graph controller out of the
   minimal case before handing it to whoever fixes it.

## What to collect when one of them fails

- The script's own log (`--log-file`) — it timestamps submission and prints elapsed time on failure.
- Worker logs from the pod, at DEBUG if possible. DEBUG matters specifically because it distinguishes
  the two `__log_exit` branches: DEBUG "stopped on agent request" means the agent *did* ask (SIGTERM),
  WARNING means it did not. The real incident was WARNING; confirming that in the repro confirms the
  same code path.
- Scheduler logs around the abort, including the lines *before* it — whether a `TaskCancel`,
  balance decision, or worker disconnect preceded the failure separates "scheduler pulled the rug" from
  "connection died on its own".
- `dmesg -T | tail` on the worker node and `/sys/fs/cgroup/memory.events` (or `memory.max`) inside the
  pod, to settle the OOM question rather than assuming.
- For `repro_04`: the webui's reported peak for the `wrapper` task, next to the `observed_peak_rss`
  the task itself returned.

## Implementation notes

Two non-obvious things, in case these get edited:

- **Task functions are built per attempt inside `build_pipeline(config)`**, not at module level.
  `ObjectBuffer.buffer_send_function` dedups task functions by identity for the life of a client and
  has no reserialize escape hatch, so a module-level decorated function reused across attempts ships
  the *first* attempt's captured configuration every time. `run_attempts` also uses a fresh client per
  attempt for the same reason. Both were caught during smoke testing; a sweep silently ran every
  variant at the first variant's size before the fix.
- **`wrapper` is named `wrapper` deliberately** — that is the name the failing task showed under in the
  webui, and pargraph's node keys are derived from `function.__name__`. pargraph only accepts a
  variadic parameter when it is the sole parameter, which is why the knobs reach the task through the
  closure rather than through the signature.
