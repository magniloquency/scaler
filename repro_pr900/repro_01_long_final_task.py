#!/usr/bin/env python3
"""Angle 1 -- wall-clock duration of the final task.

Hypothesis: the failure is driven by *how long* the last task runs, not by what it computes. While a
processor is busy, its two sockets (processor -> worker agent, processor -> object storage) carry no
traffic at all; the worker's own heartbeat keeps only the worker <-> scheduler link warm. If anything on
the path reaps an idle connection (an NLB/NAT idle timeout between the EKS pod and the machine hosting
the scheduler/storage, a conntrack entry, a peer-side teardown), the processor only finds out when it
tries to hand the result back -- which is exactly where the reported log comes from:

    Processor[..]: agent connector stop requested while task_id=.. was in flight; no task result will
    be sent, shutting down

That message is emitted from `Processor.__run_forever`'s `ymq.SocketStopRequestedError` handler with
`_current_task` still set, and at WARNING level, which means `_interrupted` was False -- so it was *not*
a SIGTERM from the worker agent (a worker-initiated kill goes through `ProcessorHolder.kill()` ->
SIGTERM -> `__interrupt` -> `_interrupted = True` -> DEBUG). Something else dropped that connection.

This script keeps the payloads tiny and varies only the duration, so a threshold shows up cleanly.

Usage:
    # single run at the reported duration
    python repro_01_long_final_task.py --address tcp://scheduler:2345 --final-seconds 5400

    # bisect for an idle-connection threshold (each duration is a fresh graph, sequential)
    python repro_01_long_final_task.py --address tcp://scheduler:2345 \
        --sweep-seconds 120,300,400,900,1800,3600,5400

    # hold the GIL instead of sleeping, in case the failure needs a busy interpreter
    python repro_01_long_final_task.py --address tcp://scheduler:2345 --final-seconds 5400 --busy
"""

import sys
from typing import Any, Dict, List, Tuple

from pargraph import delayed, graph

from common import build_argument_parser, run_attempts


def build_pipeline(config: Dict[str, Any]):
    """Builds the graph functions fresh per attempt, closing over `config`.

    They are defined here rather than at module level so each attempt pickles its own configuration:
    the client dedups task functions by identity, so reusing one decorated function across attempts
    would ship the first attempt's settings every time.
    """

    fanout = config["fanout"]
    leaf_seconds = config["leaf_seconds"]
    final_seconds = config["final_seconds"]
    busy = config["busy"]

    @delayed
    def make_part(seed: int, index: int) -> int:
        """A cheap upstream task, one per fan-in edge."""
        import time

        time.sleep(leaf_seconds)
        return seed + index

    @delayed
    def wrapper(*parts) -> int:
        """The long-running combining task.

        Named `wrapper` on purpose: that is the name the failing task showed under in the webui.
        pargraph only accepts a variadic parameter when it is the sole parameter, so the knobs arrive
        through the closure instead of through the signature.
        """
        import os
        import time

        started = time.monotonic()
        print(f"[wrapper] pid={os.getpid()} start, running {final_seconds}s over {len(parts)} parts", flush=True)

        next_report = 60.0
        accumulator = 0
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= final_seconds:
                break

            if busy:
                # Spin in Python so the interpreter is never idle: a busy main thread changes when
                # signals and pending calls actually get handled, and keeps the process off any
                # sleeping fast path.
                for step in range(200_000):
                    accumulator = (accumulator + step) % 1_000_003
            else:
                time.sleep(min(5.0, final_seconds - elapsed))

            if elapsed >= next_report:
                mode = "busy" if busy else "idle"
                print(f"[wrapper] {mode} {elapsed:.0f}/{final_seconds:.0f}s", flush=True)
                next_report += 60.0

        total = sum(parts)
        print(f"[wrapper] finished after {time.monotonic() - started:.0f}s, returning {total}", flush=True)
        return total

    @graph
    def pipeline(seed: int) -> int:
        parts = [make_part(seed, index) for index in range(fanout)]
        return wrapper(*parts)

    return pipeline


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--fanout", type=int, default=8, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--leaf-seconds", type=float, default=1.0, help="runtime of each upstream task")
    parser.add_argument("--final-seconds", type=float, default=5400.0, help="runtime of the final wrapper task")
    parser.add_argument("--busy", action="store_true", help="spin on the CPU instead of sleeping in the wrapper")
    parser.add_argument(
        "--sweep-seconds",
        default=None,
        help="comma separated wrapper durations to try in order, e.g. 300,900,1800,3600,5400 "
        "(overrides --final-seconds and --repeat)",
    )
    arguments = parser.parse_args()

    durations: List[float] = (
        [float(value) for value in arguments.sweep_seconds.split(",")]
        if arguments.sweep_seconds
        else [arguments.final_seconds] * arguments.repeat
    )

    def build(duration: float) -> Tuple[Dict[str, Any], List[str]]:
        config = {
            "fanout": arguments.fanout,
            "leaf_seconds": arguments.leaf_seconds,
            "final_seconds": duration,
            "busy": arguments.busy,
        }
        return build_pipeline(config).to_graph().to_dict(seed=0)

    return run_attempts(
        arguments,
        durations,
        describe_variant=lambda duration: f"wrapper runs for {duration}s ({duration / 60:.1f} min)",
        build=build,
    )


if __name__ == "__main__":
    sys.exit(main())
