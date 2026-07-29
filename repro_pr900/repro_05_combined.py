#!/usr/bin/env python3
"""Angle 5 -- the composite, tuned to the reported run.

Angles 1-4 each isolate one variable so a positive result is interpretable. This one puts them back
together, because the failure may need the combination: a wide fan-in whose inputs are fetched at task
start, a long compute during which both processor sockets go completely silent, a large memory peak, and
a large result that has to be written to object storage and handed off at the very end.

Defaults approximate the reported job: ~90 minutes in the final `wrapper`, a 15.2 GB peak, and a
non-trivial result. Run this one when the isolated angles all come back clean.

Usage:
    python repro_05_combined.py --address tcp://scheduler:2345
    python repro_05_combined.py --address tcp://scheduler:2345 --final-seconds 5377 --peak-gb 15.2 \
        --fanout 256 --leaf-mb 8 --result-gb 2 --repeat 3
"""

import sys
from typing import Any, Dict, List, Tuple

from pargraph import delayed, graph

from common import build_argument_parser, format_bytes, run_attempts


def build_pipeline(config: Dict[str, Any]):
    fanout = config["fanout"]
    leaf_bytes = config["leaf_bytes"]
    leaf_seconds = config["leaf_seconds"]
    final_seconds = config["final_seconds"]
    peak_bytes = config["peak_bytes"]
    chunk_bytes = config["chunk_bytes"]
    result_bytes = config["result_bytes"]

    @delayed
    def make_part(seed: int, index: int) -> Any:
        import time

        import numpy as np

        time.sleep(leaf_seconds)
        payload = np.empty(leaf_bytes, dtype=np.uint8)
        payload[:] = (seed + index) % 251
        return payload

    @delayed
    def wrapper(*parts) -> Any:
        """Fetch-heavy, long-running, memory-heavy, and large-result all in one task."""
        import gc
        import os
        import time

        import numpy as np

        def read_rss() -> int:
            try:
                import psutil

                return psutil.Process().memory_info().rss
            except Exception:
                try:
                    with open("/proc/self/statm") as statm:
                        return int(statm.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                except Exception:
                    return 0

        started = time.monotonic()
        observed_peak = read_rss()
        input_bytes = sum(part.nbytes for part in parts)
        print(
            f"[wrapper] pid={os.getpid()} got {len(parts)} parts / {input_bytes} bytes, rss={observed_peak}", flush=True
        )

        # Ramp to the target peak on top of whatever the inputs already cost.
        chunks: List[Any] = []
        allocated = 0
        while allocated < peak_bytes:
            size = min(chunk_bytes, peak_bytes - allocated)
            chunk = np.empty(size, dtype=np.uint8)
            chunk[:] = 1
            chunks.append(chunk)
            allocated += size
            observed_peak = max(observed_peak, read_rss())
        print(f"[wrapper] ramped to {allocated} bytes, rss peak={observed_peak}", flush=True)

        # Burn the rest of the wall clock with both sockets idle, exactly like the real task.
        next_report = 60.0
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= final_seconds:
                break
            time.sleep(min(5.0, final_seconds - elapsed))
            observed_peak = max(observed_peak, read_rss())
            if elapsed >= next_report:
                print(f"[wrapper] {elapsed:.0f}/{final_seconds:.0f}s rss peak={observed_peak}", flush=True)
                next_report += 60.0

        del chunks
        gc.collect()

        print(f"[wrapper] building a {result_bytes} byte result after {time.monotonic() - started:.0f}s", flush=True)
        result = np.empty(result_bytes, dtype=np.uint8)
        result[:] = len(parts) % 251
        observed_peak = max(observed_peak, read_rss())
        print(f"[wrapper] handing back {result.nbytes} bytes, observed peak rss={observed_peak}", flush=True)
        return result

    @graph
    def pipeline(seed: int) -> Any:
        parts = [make_part(seed, index) for index in range(fanout)]
        return wrapper(*parts)

    return pipeline


def report(result: Any) -> str:
    try:
        return f"{type(result).__name__} nbytes={format_bytes(result.nbytes)}"
    except AttributeError:
        return repr(result)[:200]


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--fanout", type=int, default=256, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--leaf-mb", type=float, default=8.0, help="size of each upstream result, in MiB")
    parser.add_argument("--leaf-seconds", type=float, default=2.0, help="runtime of each upstream task")
    parser.add_argument("--final-seconds", type=float, default=5377.0, help="total runtime of the wrapper task")
    parser.add_argument("--peak-gb", type=float, default=15.2, help="RSS peak the wrapper ramps to, in GiB")
    parser.add_argument("--chunk-mb", type=float, default=512.0, help="allocation granularity of the ramp, in MiB")
    parser.add_argument("--result-gb", type=float, default=2.0, help="size of the wrapper's returned object, in GiB")
    arguments = parser.parse_args()

    config = {
        "fanout": arguments.fanout,
        "leaf_bytes": int(arguments.leaf_mb * (1 << 20)),
        "leaf_seconds": arguments.leaf_seconds,
        "final_seconds": arguments.final_seconds,
        "peak_bytes": int(arguments.peak_gb * (1 << 30)),
        "chunk_bytes": int(arguments.chunk_mb * (1 << 20)),
        "result_bytes": int(arguments.result_gb * (1 << 30)),
    }

    def build(_variant: int) -> Tuple[Dict[str, Any], List[str]]:
        return build_pipeline(config).to_graph().to_dict(seed=0)

    def describe(variant: int) -> str:
        return (
            f"run {variant}: {config['fanout']} x {format_bytes(config['leaf_bytes'])} inputs, "
            f"{config['final_seconds']}s wrapper, {format_bytes(config['peak_bytes'])} peak, "
            f"{format_bytes(config['result_bytes'])} result"
        )

    return run_attempts(
        arguments, list(range(1, arguments.repeat + 1)), describe_variant=describe, build=build, report=report
    )


if __name__ == "__main__":
    sys.exit(main())
