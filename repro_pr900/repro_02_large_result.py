#!/usr/bin/env python3
"""Angle 2 -- size of the value the final task returns.

Hypothesis: the wrapper's *result* is what breaks, not its runtime. `Processor.__send_result` does three
things in order, and `_current_task` is only cleared after all three:

    1. `self._connector_storage.set_object(result_object_id, result_bytes)`   # whole payload, one message
    2. `self._connector_agent.send(ObjectInstruction(...))`
    3. `self._connector_agent.send(TaskResult(...))`

Step 1 failing raises ObjectStorageException and logs "object storage error", which is *not* what was
seen. Steps 2 and 3 failing with SocketStopRequestedError produce exactly the reported message. A send
gets SocketStopRequestedError when its MessageConnection is torn down under it (UV_ECANCELED, or the
connection being destroyed with sends still queued) -- i.e. the processor <-> agent link went away
between the storage write and the handoff. A multi-GB step 1 is a long window for that to happen, and
it is also where a size cliff would live: `YMQSyncObjectStorageConnector` defines MAX_CHUNK_SIZE =
128 MiB with a comment about oversized send buffers but never actually chunks -- the payload goes out
as a single ymq message behind a uint64 length header.

This script sweeps result sizes across the interesting boundaries (2^31, 2^32) with negligible runtime,
so a size cliff separates cleanly from a time effect.

Usage:
    python repro_02_large_result.py --address tcp://scheduler:2345 --sweep-gb 1,1.9,2.1,3.9,4.1,8,16
    python repro_02_large_result.py --address tcp://scheduler:2345 --result-gb 15.2
    python repro_02_large_result.py --address tcp://scheduler:2345 --sweep-gb 4,8,16 --client-upload-only
"""

import sys
from typing import Any, Dict, List, Tuple

from pargraph import delayed, graph

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


def build_pipeline(config: Dict[str, Any]):
    fanout = config["fanout"]
    result_bytes = config["result_bytes"]

    @delayed
    def make_part(seed: int, index: int) -> int:
        """A cheap upstream task; the interesting payload is built in the wrapper."""
        return seed + index

    @delayed
    def wrapper(*parts) -> Any:
        """Builds and returns one large object, mimicking a combining task with a big output."""
        import os

        import numpy as np

        print(f"[wrapper] pid={os.getpid()} allocating {result_bytes} bytes", flush=True)

        # np.zeros hands back untouched pages on Linux, so the process would never really own the
        # memory. Fill it, so the size is real in RSS as well as on the wire.
        payload = np.empty(result_bytes, dtype=np.uint8)
        payload[:] = len(parts) % 251

        print(f"[wrapper] built {payload.nbytes} bytes, returning it as the task result", flush=True)
        return payload

    @graph
    def pipeline(seed: int) -> Any:
        parts = [make_part(seed, index) for index in range(fanout)]
        return wrapper(*parts)

    return pipeline


def report(result: Any) -> str:
    try:
        return f"{type(result).__name__} nbytes={format_bytes(result.nbytes)} first={result[0]} last={result[-1]}"
    except AttributeError:
        return repr(result)[:200]


def run_client_upload_only(arguments, sizes_bytes: List[int]) -> int:
    """Isolates the *client's* upload of a same-sized object, which uses the same connector code path.

    If this fails at the same size a worker does, the cliff is in the object storage transport rather
    than in anything specific to a worker processor.
    """

    import numpy as np

    setup_logging(arguments.log_file)
    describe_environment(arguments)
    start_local_cluster_if_requested(arguments)

    failures = 0
    try:
        for size_bytes in sizes_bytes:
            logger.info(f"=== client-upload-only: {format_bytes(size_bytes)} ===")
            client = make_client(arguments)
            try:
                payload = np.empty(size_bytes, dtype=np.uint8)
                payload[:] = 7
                reference = client.send_object(payload, name="repro_large")
                logger.info(f"uploaded, reference={reference}")
                logger.info(f"round trip len() returned {client.submit(len, reference).result()}")
            except Exception as exception:
                failures += 1
                logger.exception(f"client upload of {format_bytes(size_bytes)} FAILED: {exception}")
            finally:
                try:
                    client.disconnect()
                except Exception as exception:
                    logger.warning(f"client disconnect failed: {exception}")
    finally:
        shutdown_local_cluster()

    logger.info(f"done: {failures} failure(s) out of {len(sizes_bytes)} attempt(s)")
    return 1 if failures else 0


def main() -> int:
    parser = build_argument_parser(__doc__ or "")
    parser.add_argument("--fanout", type=int, default=8, help="number of upstream tasks feeding the wrapper")
    parser.add_argument("--result-gb", type=float, default=15.2, help="size of the wrapper's returned object, in GiB")
    parser.add_argument(
        "--sweep-gb",
        default=None,
        help="comma separated result sizes in GiB to try in order, e.g. 1,1.9,2.1,3.9,4.1,8,16 "
        "(overrides --result-gb and --repeat)",
    )
    parser.add_argument(
        "--client-upload-only",
        action="store_true",
        help="skip the graph; just have the client upload an object of the same size and read it back",
    )
    arguments = parser.parse_args()

    sizes_bytes = [
        int(size_gb * (1 << 30))
        for size_gb in (
            [float(value) for value in arguments.sweep_gb.split(",")]
            if arguments.sweep_gb
            else [arguments.result_gb] * arguments.repeat
        )
    ]

    if arguments.client_upload_only:
        return run_client_upload_only(arguments, sizes_bytes)

    def build(size_bytes: int) -> Tuple[Dict[str, Any], List[str]]:
        config = {"fanout": arguments.fanout, "result_bytes": size_bytes}
        return build_pipeline(config).to_graph().to_dict(seed=0)

    def describe(size_bytes: int) -> str:
        return (
            f"wrapper returns {format_bytes(size_bytes)} ({size_bytes} bytes; "
            f"2^31={2**31}, 2^32={2**32}, delta_to_2^32={size_bytes - 2**32})"
        )

    return run_attempts(arguments, sizes_bytes, describe_variant=describe, build=build, report=report)


if __name__ == "__main__":
    sys.exit(main())
