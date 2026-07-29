#!/usr/bin/env python3
"""Angle 3 -- fan-in width and total input volume of the final task.

Hypothesis: what is unusual about the wrapper is not its runtime or its output but its *inputs* -- it is
the join point for a large number of upstream results. That stresses three things at once:

  * the GraphTask capnp message, which carries one Task per node with one argument entry per edge;
  * the scheduler's graph bookkeeping (`_task_id_to_graph_task_id`, per-node dependency maps), which is
    where PR 900's graph hardening lives;
  * the processor's argument fetch: before the wrapper's function even runs, the processor pulls every
    upstream object out of object storage, one `get_object` at a time, holding them all at once.

That last point also explains a memory peak that arrives well before the task's "own" work, and would
put a large amount of traffic on the processor <-> storage link right at task start and nothing at all
after -- the shape that would expose an idle-reaped connection at handoff time.

This script keeps runtime and result size negligible and varies only the width and the per-input size.

Usage:
    python repro_03_wide_fanin.py --address tcp://scheduler:2345 --sweep-fanout 100,500,1000,2000,5000
    python repro_03_wide_fanin.py --address tcp://scheduler:2345 --fanout 2000 --leaf-mb 8
"""

import sys
from typing import Any, Dict, List, Tuple

from pargraph import delayed, graph

from common import build_argument_parser, format_bytes, run_attempts


def build_pipeline(config: Dict[str, Any]):
    fanout = config["fanout"]
    leaf_bytes = config["leaf_bytes"]

    @delayed
    def make_part(seed: int, index: int) -> Any:
        """One upstream result of `leaf_bytes`; the wrapper has to fetch every one of these."""
        import numpy as np

        payload = np.empty(leaf_bytes, dtype=np.uint8)
        payload[:] = (seed + index) % 251
        return payload

    @delayed
    def wrapper(*parts) -> int:
        """Consumes every upstream result and returns something tiny.

        Reducing to a small value is deliberate: it keeps the result-handoff path (which angle 2 covers)
        out of the picture, so a failure here points at the inputs.
        """
        import os

        import numpy as np

        total_bytes = sum(part.nbytes for part in parts)
        print(f"[wrapper] pid={os.getpid()} received {len(parts)} parts, {total_bytes} bytes total", flush=True)

        checksum = 0
        for index, part in enumerate(parts):
            checksum = (checksum + int(np.sum(part, dtype=np.uint64))) % (1 << 62)
            if index % 500 == 0:
                print(f"[wrapper] reduced {index}/{len(parts)} parts", flush=True)

        print(f"[wrapper] done, checksum={checksum}", flush=True)
        return checksum

    @graph
    def pipeline(seed: int) -> int:
        parts = [make_part(seed, index) for index in range(fanout)]
        return wrapper(*parts)

    return pipeline


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--fanout", type=int, default=2000, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--leaf-mb", type=float, default=4.0, help="size of each upstream result, in MiB")
    parser.add_argument(
        "--sweep-fanout",
        default=None,
        help="comma separated fan-in widths to try in order, e.g. 100,500,1000,2000,5000,10000 "
        "(overrides --fanout and --repeat)",
    )
    arguments = parser.parse_args()

    fanouts: List[int] = (
        [int(value) for value in arguments.sweep_fanout.split(",")]
        if arguments.sweep_fanout
        else [arguments.fanout] * arguments.repeat
    )
    leaf_bytes = int(arguments.leaf_mb * (1 << 20))

    def build(fanout: int) -> Tuple[Dict[str, Any], List[str]]:
        return build_pipeline({"fanout": fanout, "leaf_bytes": leaf_bytes}).to_graph().to_dict(seed=0)

    def describe(fanout: int) -> str:
        return (
            f"{fanout} upstream tasks x {format_bytes(leaf_bytes)} each = "
            f"{format_bytes(fanout * leaf_bytes)} the wrapper must fetch"
        )

    return run_attempts(arguments, fanouts, describe_variant=describe, build=build)


if __name__ == "__main__":
    sys.exit(main())
