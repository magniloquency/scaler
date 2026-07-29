#!/usr/bin/env python3
"""Angle 6 -- is pargraph involved at all, and is the graph controller involved at all?

The reported abort came from the scheduler's `graph_controller`, which only runs for GraphTask messages
-- i.e. for `Client.get()`. pargraph itself is only a graph *builder* here: `to_dict()` produces a plain
dict graph and `Client.get()` does the rest. So two things are worth separating from the failure:

  * `--mode graph` builds the same shape as the pargraph scripts but as a hand-written dict, with no
    pargraph import at all. If this fails identically, pargraph is not implicated and the repro can be
    handed over without it.
  * `--mode submit` runs the same work through plain `Client.submit()` calls, resolving dependencies in
    the client. That never creates a GraphTask, so the scheduler's graph controller and its whole-graph
    abort path are out of the picture. If `submit` survives what `graph` cannot, the problem is in graph
    handling rather than in the worker/transport layer.

Both modes take the same knobs, so a single pair of runs answers both questions.

Usage:
    python repro_06_no_pargraph.py --address tcp://scheduler:2345 --mode graph  --final-seconds 5400
    python repro_06_no_pargraph.py --address tcp://scheduler:2345 --mode submit --final-seconds 5400
"""

import sys
import time
from typing import Any, Callable, Dict, List, Tuple

from common import (
    build_argument_parser,
    describe_environment,
    format_bytes,
    logger,
    make_client,
    run_attempts,
    setup_logging,
    shutdown_local_cluster,
    start_local_cluster_if_requested,
)


def make_task_functions(config: Dict[str, Any]) -> Tuple[Callable, Callable]:
    """The same two tasks the pargraph scripts use, as plain closures."""

    leaf_bytes = config["leaf_bytes"]
    final_seconds = config["final_seconds"]
    result_bytes = config["result_bytes"]

    def make_part(seed: int, index: int) -> Any:
        import numpy as np

        payload = np.empty(leaf_bytes, dtype=np.uint8)
        payload[:] = (seed + index) % 251
        return payload

    def wrapper(*parts) -> Any:
        import os
        import time as task_time

        import numpy as np

        started = task_time.monotonic()
        input_bytes = sum(part.nbytes for part in parts)
        print(f"[wrapper] pid={os.getpid()} got {len(parts)} parts / {input_bytes} bytes", flush=True)

        next_report = 60.0
        while True:
            elapsed = task_time.monotonic() - started
            if elapsed >= final_seconds:
                break
            task_time.sleep(min(5.0, final_seconds - elapsed))
            if elapsed >= next_report:
                print(f"[wrapper] {elapsed:.0f}/{final_seconds:.0f}s", flush=True)
                next_report += 60.0

        result = np.empty(result_bytes, dtype=np.uint8)
        result[:] = len(parts) % 251
        print(f"[wrapper] returning {result.nbytes} bytes after {task_time.monotonic() - started:.0f}s", flush=True)
        return result

    return make_part, wrapper


def build_dict_graph(config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """The scaler dict-graph form `Client.get` expects: {name: value} and {name: (fn, *arg_names)}."""

    make_part, wrapper = make_task_functions(config)

    dict_graph: Dict[str, Any] = {"seed": 0}
    part_names = []
    for index in range(config["fanout"]):
        dict_graph[f"index_{index}"] = index
        dict_graph[f"part_{index}"] = (make_part, "seed", f"index_{index}")
        part_names.append(f"part_{index}")

    dict_graph["wrapper"] = (wrapper, *part_names)
    return dict_graph, ["wrapper"]


def report(result: Any) -> str:
    try:
        return f"{type(result).__name__} nbytes={format_bytes(result.nbytes)}"
    except AttributeError:
        return repr(result)[:200]


def run_submit_mode(arguments, config: Dict[str, Any]) -> int:
    """Same work, but as individual `Client.submit` calls -- no GraphTask, no graph controller."""

    setup_logging(arguments.log_file)
    describe_environment(arguments)
    start_local_cluster_if_requested(arguments)

    make_part, wrapper = make_task_functions(config)

    failures = 0
    try:
        for attempt in range(1, arguments.repeat + 1):
            logger.info(f"=== attempt {attempt}/{arguments.repeat}: submit mode, {config['fanout']} parts ===")
            client = make_client(arguments)
            started_at = time.monotonic()
            try:
                part_futures = [client.submit(make_part, 0, index) for index in range(config["fanout"])]
                logger.info(f"submitted {len(part_futures)} upstream tasks, waiting for them")
                parts = [future.result() for future in part_futures]

                logger.info("upstream tasks done, submitting the wrapper")
                result = client.submit(wrapper, *parts).result()
                logger.info(f"SUCCEEDED after {time.monotonic() - started_at:.1f}s: {report(result)}")
            except Exception as exception:
                failures += 1
                elapsed = time.monotonic() - started_at
                logger.exception(f"FAILED after {elapsed:.1f}s ({elapsed / 60:.1f} min): {exception}")
            finally:
                try:
                    client.disconnect()
                except Exception as exception:
                    logger.warning(f"client disconnect failed: {exception}")
    finally:
        shutdown_local_cluster()

    logger.info(f"done: {failures} failure(s) out of {arguments.repeat} attempt(s)")
    return 1 if failures else 0


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--mode", choices=["graph", "submit"], default="graph", help="submission path to exercise")
    parser.add_argument("--fanout", type=int, default=64, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--leaf-mb", type=float, default=4.0, help="size of each upstream result, in MiB")
    parser.add_argument("--final-seconds", type=float, default=5400.0, help="runtime of the final wrapper task")
    parser.add_argument("--result-gb", type=float, default=1.0, help="size of the wrapper's returned object, in GiB")
    arguments = parser.parse_args()

    config = {
        "fanout": arguments.fanout,
        "leaf_bytes": int(arguments.leaf_mb * (1 << 20)),
        "final_seconds": arguments.final_seconds,
        "result_bytes": int(arguments.result_gb * (1 << 30)),
    }

    if arguments.mode == "submit":
        # In submit mode every upstream result travels back through the client, which is a different
        # data path from the graph mode where results stay in object storage between tasks. That
        # difference is the point of the comparison, not an accident.
        return run_submit_mode(arguments, config)

    def describe(variant: int) -> str:
        return (
            f"run {variant}: hand-written dict graph, {config['fanout']} x "
            f"{format_bytes(config['leaf_bytes'])} inputs, {config['final_seconds']}s wrapper, "
            f"{format_bytes(config['result_bytes'])} result"
        )

    return run_attempts(
        arguments,
        list(range(1, arguments.repeat + 1)),
        describe_variant=describe,
        build=lambda _variant: build_dict_graph(config),
        report=report,
    )


if __name__ == "__main__":
    sys.exit(main())
