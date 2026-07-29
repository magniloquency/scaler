#!/usr/bin/env python3
"""Angle 4 -- memory: the real peak, and whether the monitor sees it.

Two things at once, because they share a workload:

  1. Reproduction: drive the processor's RSS to a chosen peak inside the wrapper and hold it there.
     If the failure is memory-driven (a cgroup limit nobody knew about, the kernel OOM killer, an
     allocation failure inside the ymq/storage transfer), it should reproduce here without needing 90
     minutes of runtime. The wrapper returns a *small* value, so a failure cannot be blamed on the
     result handoff.

  2. Instrumentation for the "15.2 GB peak looks wrong" complaint. The wrapper samples its own RSS from
     inside the task and returns the peak it actually observed, so the number the webui reports can be
     compared against a ground truth taken in the same process. `--ramp-seconds` controls how long the
     peak is held, which is the thing a sampling monitor can miss: a peak held for 2 seconds and a peak
     held for 300 seconds should read identically if the monitor is tracking a true high-water mark, and
     will not if it is sampling.

Usage:
    python repro_04_memory_peak.py --address tcp://scheduler:2345 --peak-gb 16 --hold-seconds 120
    # does the reported peak depend on how long the peak is held? (monitor sampling check)
    python repro_04_memory_peak.py --address tcp://scheduler:2345 --peak-gb 8 --sweep-hold 2,30,300
"""

import sys
from typing import Any, Dict, List, Tuple

from pargraph import delayed, graph

from common import build_argument_parser, format_bytes, run_attempts


def build_pipeline(config: Dict[str, Any]):
    fanout = config["fanout"]
    peak_bytes = config["peak_bytes"]
    chunk_bytes = config["chunk_bytes"]
    hold_seconds = config["hold_seconds"]

    @delayed
    def make_part(seed: int, index: int) -> int:
        return seed + index

    @delayed
    def wrapper(*parts) -> Any:
        """Ramps RSS up to `peak_bytes`, holds it, frees it, and reports what it measured."""
        import gc
        import os
        import time

        import numpy as np

        def read_rss() -> int:
            try:
                import psutil

                return psutil.Process().memory_info().rss
            except Exception:
                # /proc fallback: field 2 of statm is resident pages.
                try:
                    with open("/proc/self/statm") as statm:
                        return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                except Exception:
                    return 0

        observed_peak = read_rss()
        print(f"[wrapper] pid={os.getpid()} baseline rss={observed_peak}", flush=True)

        chunks = []
        allocated = 0
        while allocated < peak_bytes:
            size = min(chunk_bytes, peak_bytes - allocated)
            chunk = np.empty(size, dtype=np.uint8)
            chunk[:] = 1  # touch every page, otherwise the pages are never really resident
            chunks.append(chunk)
            allocated += size

            rss = read_rss()
            observed_peak = max(observed_peak, rss)
            print(f"[wrapper] allocated={allocated} rss={rss} peak={observed_peak}", flush=True)

        deadline = time.monotonic() + hold_seconds
        while time.monotonic() < deadline:
            time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
            rss = read_rss()
            observed_peak = max(observed_peak, rss)
            print(f"[wrapper] holding, rss={rss} peak={observed_peak}", flush=True)

        del chunks
        gc.collect()
        after_free = read_rss()
        print(f"[wrapper] freed, rss={after_free}, observed peak={observed_peak}", flush=True)

        # Small result on purpose: this angle must not be confounded by the result handoff.
        return {
            "pid": os.getpid(),
            "requested_peak_bytes": peak_bytes,
            "observed_peak_rss_bytes": observed_peak,
            "rss_after_free_bytes": after_free,
            "hold_seconds": hold_seconds,
            "parts": len(parts),
        }

    @graph
    def pipeline(seed: int) -> Any:
        parts = [make_part(seed, index) for index in range(fanout)]
        return wrapper(*parts)

    return pipeline


def report(result: Any) -> str:
    if not isinstance(result, dict):
        return repr(result)[:200]
    return (
        f"pid={result['pid']} requested={format_bytes(result['requested_peak_bytes'])} "
        f"observed_peak_rss={format_bytes(result['observed_peak_rss_bytes'])} "
        f"after_free={format_bytes(result['rss_after_free_bytes'])} "
        f"held_for={result['hold_seconds']}s "
        f"<-- compare observed_peak_rss against the webui's peak for this task"
    )


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--fanout", type=int, default=8, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--peak-gb", type=float, default=16.0, help="RSS peak the wrapper ramps up to, in GiB")
    parser.add_argument("--chunk-mb", type=float, default=512.0, help="allocation granularity of the ramp, in MiB")
    parser.add_argument("--hold-seconds", type=float, default=120.0, help="how long to hold the peak")
    parser.add_argument(
        "--sweep-hold",
        default=None,
        help="comma separated hold durations to try in order, e.g. 2,30,300 (overrides --hold-seconds "
        "and --repeat); use this to tell a sampled peak from a true high-water mark",
    )
    arguments = parser.parse_args()

    holds: List[float] = (
        [float(value) for value in arguments.sweep_hold.split(",")]
        if arguments.sweep_hold
        else [arguments.hold_seconds] * arguments.repeat
    )
    peak_bytes = int(arguments.peak_gb * (1 << 30))
    chunk_bytes = int(arguments.chunk_mb * (1 << 20))

    def build(hold_seconds: float) -> Tuple[Dict[str, Any], List[str]]:
        config = {
            "fanout": arguments.fanout,
            "peak_bytes": peak_bytes,
            "chunk_bytes": chunk_bytes,
            "hold_seconds": hold_seconds,
        }
        return build_pipeline(config).to_graph().to_dict(seed=0)

    def describe(hold_seconds: float) -> str:
        return f"ramp to {format_bytes(peak_bytes)} in {format_bytes(chunk_bytes)} chunks, hold {hold_seconds}s"

    return run_attempts(arguments, holds, describe_variant=describe, build=build, report=report)


if __name__ == "__main__":
    sys.exit(main())
