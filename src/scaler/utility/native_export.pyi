import logging
from typing import Any, Dict, List, Mapping, Optional, Tuple

from opentelemetry.trace import SpanContext

# values other than str, bool, int, and float are exported as their str()
Attributes = Optional[Mapping[str, Any]]
RecordAttributes = Optional[Dict[str, Any]]  # inside a list, whose element type mypy holds to exactly

def configure(resource_attributes: Mapping[str, Any], scope_name: str) -> None: ...
def start_span(parent_sampled: int, parent_trace_id_low: int) -> Tuple[int, int, int, bool]: ...
def export_span(
    trace_id: bytes,
    span_id: bytes,
    parent_span_id: Optional[bytes],
    trace_state: str,
    name: str,
    kind: int,
    start_unix_nano: int,
    end_unix_nano: int,
    status_code: int,
    status_message: str,
    attributes: Attributes,
    events: Optional[List[Tuple[str, int, RecordAttributes]]],
    links: Optional[List[Tuple[bytes, bytes, str, RecordAttributes]]],
) -> None: ...
def export_log(record: logging.LogRecord, body: Optional[str], span_context: SpanContext) -> None: ...
def flush(timeout_seconds: float) -> bool: ...
def shutdown(timeout_seconds: float) -> bool: ...
