"""Span and log providers that export through opentelemetry-cpp, so encoding and export never hold the GIL.

native_export makes each span's ids and sampling decision, as OTEL_TRACES_SAMPLER configures, in one call; end() hands
the finished span over, and a log record is translated as the Python SDK's LoggingHandler translates it. Both are
queued, and opentelemetry-cpp's threads apply the OTEL_*_LIMIT limits, encode, and send them.
"""

import atexit
import logging
import time
import traceback
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from opentelemetry import baggage, trace
from opentelemetry.context import Context
from opentelemetry.trace import Link, NonRecordingSpan, SpanContext, SpanKind, Status, StatusCode, TraceFlags
from opentelemetry.util._decorator import _agnosticcontextmanager
from opentelemetry.util.types import AnyValue, Attributes

from scaler.utility import native_export

SCOPE_NAME = "scaler"
FLUSH_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 30.0

# the logger native_export reports export problems to; exporting its records could loop
EXPORTER_LOGGER_NAME = __name__

TRACE_ID_BYTES = 16
SPAN_ID_BYTES = 8
HALF_TRACE_ID_BITS = 64
LOW_TRACE_ID_MASK = (1 << HALF_TRACE_ID_BITS) - 1

# native_export.start_span()'s parent_sampled argument
NO_PARENT = -1

SAMPLED = TraceFlags(TraceFlags.SAMPLED)
NOT_SAMPLED = TraceFlags(TraceFlags.DEFAULT)

Event = Tuple[str, int, Optional[Dict[str, AnyValue]]]
ExportedLink = Tuple[bytes, bytes, str, Optional[Dict[str, AnyValue]]]


def _to_bytes(trace_id: int, span_id: int) -> Tuple[bytes, bytes]:
    return trace_id.to_bytes(TRACE_ID_BYTES, "big"), span_id.to_bytes(SPAN_ID_BYTES, "big")


class NativeSpan(trace.Span):
    __slots__ = (
        "_context",
        "_parent_span_id",
        "_name",
        "_kind",
        "_start",
        "_attributes",
        "_events",
        "_links",
        "_status",
        "_ended",
    )

    def __init__(
        self,
        context: SpanContext,
        parent_span_id: Optional[int],
        name: str,
        kind: SpanKind,
        start: int,
        attributes: Dict[str, AnyValue],
        links: Optional[Sequence[Link]],
    ) -> None:
        self._context = context
        self._parent_span_id = parent_span_id
        self._name = name
        self._kind = kind
        self._start = start
        self._attributes = attributes
        self._events: Optional[List[Event]] = None
        self._links = links
        self._status = Status(StatusCode.UNSET)
        self._ended = False

    def get_span_context(self) -> SpanContext:
        return self._context

    def is_recording(self) -> bool:
        return not self._ended

    def set_attribute(self, key: str, value: AnyValue) -> None:
        self._attributes[key] = value

    def set_attributes(self, attributes: Mapping[str, AnyValue]) -> None:
        self._attributes.update(attributes)

    def add_event(self, name: str, attributes: Attributes = None, timestamp: Optional[int] = None) -> None:
        if self._events is None:
            self._events = []
        self._events.append((name, timestamp or time.time_ns(), dict(attributes) if attributes else None))

    def add_link(self, context: SpanContext, attributes: Attributes = None) -> None:
        self._links = [*(self._links or ()), Link(context, attributes)]

    def update_name(self, name: str) -> None:
        self._name = name

    def set_status(self, status: Any, description: Optional[str] = None) -> None:
        self._status = status if isinstance(status, Status) else Status(status, description)

    def record_exception(
        self,
        exception: BaseException,
        attributes: Attributes = None,
        timestamp: Optional[int] = None,
        escaped: bool = False,
    ) -> None:
        event_attributes: Dict[str, AnyValue] = {
            "exception.type": type(exception).__name__,
            "exception.message": str(exception),
            "exception.stacktrace": "".join(
                traceback.format_exception(type(exception), exception, exception.__traceback__)
            ),
            "exception.escaped": str(escaped),
        }
        if attributes:
            event_attributes.update(attributes)
        self.add_event("exception", event_attributes, timestamp)

    def end(self, end_time: Optional[int] = None) -> None:
        if self._ended:
            return
        self._ended = True

        trace_id, span_id = _to_bytes(self._context.trace_id, self._context.span_id)
        parent_span_id = None if self._parent_span_id is None else self._parent_span_id.to_bytes(SPAN_ID_BYTES, "big")
        trace_state = self._context.trace_state.to_header() if self._context.trace_state else ""

        links: Optional[List[ExportedLink]] = None
        if self._links:
            links = []
            for link in self._links:
                link_trace_id, link_span_id = _to_bytes(link.context.trace_id, link.context.span_id)
                link_trace_state = link.context.trace_state.to_header() if link.context.trace_state else ""
                link_attributes = dict(link.attributes) if link.attributes else None
                links.append((link_trace_id, link_span_id, link_trace_state, link_attributes))

        native_export.export_span(
            trace_id,
            span_id,
            parent_span_id,
            trace_state,
            self._name,
            self._kind.value,
            self._start,
            end_time or time.time_ns(),
            self._status.status_code.value,
            self._status.description or "",
            self._attributes or None,
            self._events,
            links,
        )


class NativeTracer(trace.Tracer):
    def start_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Attributes = None,
        links: Optional[Sequence[Link]] = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> trace.Span:
        parent = trace.get_current_span(context).get_span_context()
        if parent.is_valid:
            parent_sampled = 1 if parent.trace_flags.sampled else 0
            _, _, span_id, sampled = native_export.start_span(parent_sampled, parent.trace_id & LOW_TRACE_ID_MASK)
            trace_id, parent_span_id, trace_state = parent.trace_id, parent.span_id, parent.trace_state
        else:
            trace_id_high, trace_id_low, span_id, sampled = native_export.start_span(NO_PARENT, 0)
            trace_id, parent_span_id, trace_state = (trace_id_high << HALF_TRACE_ID_BITS) | trace_id_low, None, None

        if not sampled:
            return NonRecordingSpan(SpanContext(trace_id, span_id, False, NOT_SAMPLED, trace_state))

        span_attributes: Dict[str, AnyValue] = dict(attributes) if attributes else {}
        # as the Scaler SDK setup's BaggageSpanProcessor does: a user tag reaches every span
        for key, value in baggage.get_all(context).items():
            span_attributes[key] = str(value)

        span_context = SpanContext(trace_id, span_id, False, SAMPLED, trace_state)
        return NativeSpan(
            span_context, parent_span_id, name, kind, start_time or time.time_ns(), span_attributes, links
        )

    @_agnosticcontextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Optional[Context] = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Attributes = None,
        links: Optional[Sequence[Link]] = None,
        start_time: Optional[int] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[trace.Span]:
        span = self.start_span(name, context, kind, attributes, links, start_time)
        with trace.use_span(
            span,
            end_on_exit=end_on_exit,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        ) as current:
            yield current


class NativeTracerProvider(trace.TracerProvider):
    """Exports to the endpoint the OTEL_EXPORTER_OTLP_* variables set, as the Python SDK's OTLP exporter does."""

    def __init__(self) -> None:
        self._tracer = NativeTracer()

    def get_tracer(self, instrumenting_module_name: str, *args: Any, **kwargs: Any) -> trace.Tracer:
        return self._tracer

    def force_flush(self, timeout_millis: int = int(FLUSH_TIMEOUT_SECONDS * 1000)) -> bool:
        return native_export.flush(timeout_millis / 1000)


class NativeLogHandler(logging.Handler):
    """Exports each record of the logger it is attached to, without the records native_export logs itself."""

    def __init__(self, level: int) -> None:
        super().__init__(level=level)
        self.addFilter(lambda record: record.name != EXPORTER_LOGGER_NAME)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            body = self.format(record) if self.formatter else None
            native_export.export_log(record, body, trace.get_current_span().get_span_context())
        except Exception:
            self.handleError(record)


class NativeLoggerProvider:
    """The log side of native export, which InstalledSDK flushes and attach_log_handler attaches."""

    def force_flush(self, timeout_millis: int = int(FLUSH_TIMEOUT_SECONDS * 1000)) -> bool:
        return native_export.flush(timeout_millis / 1000)

    def make_handler(self, level: int) -> NativeLogHandler:
        return NativeLogHandler(level)


def install(resource_attributes: Dict[str, AnyValue]) -> Tuple[NativeTracerProvider, NativeLoggerProvider]:
    """Start the native span and log exporters, once per process."""
    native_export.configure(resource_attributes, SCOPE_NAME)
    atexit.register(native_export.shutdown, SHUTDOWN_TIMEOUT_SECONDS)
    return NativeTracerProvider(), NativeLoggerProvider()
