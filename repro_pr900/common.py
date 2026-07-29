"""Shared harness for the PR-900 "long wrapper task dies mid-flight" reproduction scripts.

Every script in this directory submits a pargraph-built graph through `scaler.Client.get()` (the same
path the reported failure took: pargraph -> dict graph -> GraphTask -> scheduler graph_controller) and
reports, with timestamps, exactly where it got to before failing.
"""

import argparse
import datetime
import logging
import os
import socket
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

MEBIBYTE = 1024 * 1024
GIBIBYTE = 1024 * 1024 * 1024

logger = logging.getLogger("repro")


def build_argument_parser(description: str) -> argparse.ArgumentParser:
    """An argument parser pre-populated with the options every repro script needs."""

    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--address",
        default=os.environ.get("SCALER_ADDRESS"),
        help="scheduler address, e.g. tcp://scheduler-host:2345 (defaults to $SCALER_ADDRESS)",
    )
    parser.add_argument(
        "--object-storage-address",
        default=os.environ.get("SCALER_OBJECT_STORAGE_ADDRESS"),
        help="override the object storage address the scheduler advertises",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=0,
        help="client heartbeat timeout, 0 keeps the scaler default (use a large value for very long tasks)",
    )
    parser.add_argument("--profiling", action="store_true", help="enable scaler task profiling on the client")
    parser.add_argument("--log-file", default=None, help="also write this script's log to the given file")
    parser.add_argument(
        "--repeat", type=int, default=1, help="run the whole graph this many times, sequentially, in one client"
    )
    parser.add_argument(
        "--local-workers",
        type=int,
        default=0,
        help="smoke-test mode: start a throwaway local scheduler+cluster with this many workers and ignore --address",
    )
    return parser


def setup_logging(log_file: Optional[str] = None) -> None:
    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def describe_environment(arguments: argparse.Namespace) -> None:
    logger.info(f"host={socket.gethostname()} pid={os.getpid()} python={sys.version.split()[0]}")

    try:
        import scaler

        logger.info(f"scaler={getattr(scaler, '__version__', 'unknown')} from {os.path.dirname(scaler.__file__)}")
    except ImportError:
        logger.warning("scaler is not importable")

    try:
        import pargraph

        logger.info(f"pargraph={pargraph.__version__} from {os.path.dirname(pargraph.__file__)}")
    except ImportError:
        logger.warning("pargraph is not importable")

    logger.info(f"arguments={vars(arguments)}")


_local_cluster = None


def start_local_cluster_if_requested(arguments: argparse.Namespace) -> None:
    """Smoke-test helper: brings up a throwaway scheduler+cluster and points `--address` at it.

    This exists so the scripts can be validated end to end before being pointed at the real cluster.
    It reproduces nothing on its own -- a single-machine cluster has none of the network topology that
    the EKS setup has.
    """

    global _local_cluster

    if not arguments.local_workers:
        return

    from scaler import SchedulerClusterCombo

    address = "tcp://127.0.0.1:23456"
    logger.warning(f"smoke-test mode: starting a local cluster with {arguments.local_workers} workers at {address}")
    _local_cluster = SchedulerClusterCombo(n_workers=arguments.local_workers, address=address)
    arguments.address = address
    arguments.object_storage_address = None


def shutdown_local_cluster() -> None:
    global _local_cluster

    if _local_cluster is None:
        return

    _local_cluster.shutdown()
    _local_cluster = None


def make_client(arguments: argparse.Namespace):
    """Builds a scaler Client, only passing the optional knobs the caller actually set."""

    from scaler import Client

    if arguments.address is None:
        raise SystemExit("no scheduler address: pass --address, set $SCALER_ADDRESS, or use --local-workers")

    client_kwargs: Dict[str, Any] = {"address": arguments.address, "profiling": arguments.profiling}
    if arguments.object_storage_address is not None:
        client_kwargs["object_storage_address"] = arguments.object_storage_address
    if arguments.timeout_seconds:
        client_kwargs["timeout_seconds"] = arguments.timeout_seconds

    logger.info(f"connecting client with {client_kwargs}")
    return Client(**client_kwargs)


def describe_graph(dict_graph: Dict[str, Any], keys: List[str]) -> None:
    """Logs the shape of the dict graph, so a failure can be tied back to the submitted structure."""

    call_nodes = {name: node for name, node in dict_graph.items() if isinstance(node, tuple)}
    data_nodes = {name: node for name, node in dict_graph.items() if not isinstance(node, tuple)}

    widest_name, widest_node = "", ()
    for name, node in call_nodes.items():
        if len(node) > len(widest_node):
            widest_name, widest_node = name, node

    logger.info(f"graph: {len(dict_graph)} nodes ({len(call_nodes)} calls, {len(data_nodes)} data), keys={keys}")
    if widest_name:
        function = widest_node[0]
        function_name = getattr(function, "__name__", repr(function))
        logger.info(f"graph: widest call node is {widest_name!r} -> {function_name} with {len(widest_node) - 1} args")


def run_graph(client, dict_graph: Dict[str, Any], keys: List[str], report: Callable[[Any], str]) -> Any:
    """Submits the graph, waits for it, and logs a precise before/after with elapsed wall clock."""

    describe_graph(dict_graph, keys)

    started_at = time.monotonic()
    started_wall = datetime.datetime.now().isoformat(timespec="seconds")
    logger.info(f"submitting graph at {started_wall} (client.get, block=True)")

    try:
        # reserialize=True matters for the sweeps: the task functions read their knobs from a module
        # level CONFIG that cloudpickle captures by value, and the client would otherwise reuse the
        # snapshot it uploaded on the first attempt, silently running every size/duration as the first.
        try:
            results = client.get(dict_graph, keys, reserialize=True)
        except TypeError:
            results = client.get(dict_graph, keys)
    except BaseException as exception:
        elapsed = time.monotonic() - started_at
        logger.error(f"FAILED after {elapsed:.1f}s ({elapsed / 60:.1f} min): {type(exception).__name__}: {exception}")
        logger.error("full traceback follows:\n" + traceback.format_exc())
        raise

    elapsed = time.monotonic() - started_at
    logger.info(f"SUCCEEDED after {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    for key in keys:
        logger.info(f"  result[{key!r}] = {report(results[key])}")
    return results


def run_attempts(
    arguments: argparse.Namespace,
    variants: List[Any],
    describe_variant: Callable[[Any], str],
    build: Callable[[Any], Tuple[Dict[str, Any], List[str]]],
    report: Callable[[Any], str] = repr,
) -> int:
    """Runs one graph per variant, each on its own client, and returns a process exit code.

    A fresh client per attempt is deliberate: `ObjectBuffer.buffer_send_function` dedups task functions
    by identity for the lifetime of a client and offers no reserialize escape hatch, so reusing one
    client would silently run every variant with the *first* variant's pickled configuration.
    """

    setup_logging(arguments.log_file)
    describe_environment(arguments)
    start_local_cluster_if_requested(arguments)

    failures: List[str] = []
    try:
        for attempt, variant in enumerate(variants, start=1):
            description = describe_variant(variant)
            logger.info(f"=== attempt {attempt}/{len(variants)}: {description} ===")

            client = make_client(arguments)
            try:
                run_graph(client, *build(variant), report=report)
            except Exception:
                failures.append(description)
                logger.error(f"variant FAILED: {description}")
            finally:
                try:
                    client.disconnect()
                except Exception as exception:
                    logger.warning(f"client disconnect failed: {exception}")
    finally:
        shutdown_local_cluster()

    if failures:
        logger.error(f"done: {len(failures)}/{len(variants)} attempt(s) failed: {failures}")
    else:
        logger.info(f"done: all {len(variants)} attempt(s) succeeded")
    return 1 if failures else 0


def current_rss_bytes() -> int:
    """Best-effort RSS of the calling process; 0 when it cannot be read."""

    try:
        import psutil

        return psutil.Process().memory_info().rss
    except Exception:
        return 0


def format_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024.0 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{count} B"
