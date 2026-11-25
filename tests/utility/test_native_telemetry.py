import multiprocessing
import os
import unittest
from typing import Dict

from opentelemetry.proto.logs.v1.logs_pb2 import SeverityNumber as ProtoSeverity
from opentelemetry.proto.trace.v1.trace_pb2 import Span as ProtoSpan
from opentelemetry.proto.trace.v1.trace_pb2 import Status as ProtoStatus

from scaler.utility.logging.utility import setup_logger
from tests.utility.otlp_receiver import OTLPReceiver
from tests.utility.utility import logging_test_name

PROCESS_TIMEOUT_SECONDS = 60
LONG_VALUE = "x" * 50
REMOTE_TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
REMOTE_SPAN_ID = 0x0123456789ABCDEF


def _export_two_spans(environment: Dict[str, str], flushed: "multiprocessing.Queue[bool]") -> None:
    """Starts the native provider as install_sdk does, ends a parent and a child span, and flushes."""
    os.environ.update(environment)

    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    from scaler.utility.native_telemetry import install

    provider, _ = install({"service.name": "native-test"})
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("parent", attributes={"long": LONG_VALUE, "number": 1}) as parent:
        with tracer.start_as_current_span("child", kind=SpanKind.CONSUMER) as child:
            child.add_event("child.event", {"key": "value"})
            child.add_link(parent.get_span_context(), {"linked": True})
            child.set_status(Status(StatusCode.ERROR, "boom"))

    flushed.put(provider.force_flush())


def _export_root_and_child_of_sampled_remote_parent(
    environment: Dict[str, str], flushed: "multiprocessing.Queue[bool]"
) -> None:
    """Ends one root span, and one span under a sampled parent from another process."""
    os.environ.update(environment)

    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    from scaler.utility.native_telemetry import install

    provider, _ = install({"service.name": "native-test"})
    tracer = provider.get_tracer(__name__)

    tracer.start_span("root").end()
    remote_parent = SpanContext(REMOTE_TRACE_ID, REMOTE_SPAN_ID, True, TraceFlags(TraceFlags.SAMPLED))
    tracer.start_span("child", context=trace.set_span_in_context(NonRecordingSpan(remote_parent))).end()

    flushed.put(provider.force_flush())


def _log_inside_a_span(environment: Dict[str, str], flushed: "multiprocessing.Queue[bool]") -> None:
    """Logs a warning with an extra field and an exception inside a span, and a message from the exporter's logger."""
    os.environ.update(environment)

    import logging

    from opentelemetry import trace

    from scaler.utility.native_telemetry import EXPORTER_LOGGER_NAME, install

    tracer_provider, logger_provider = install({"service.name": "native-test"})
    trace.set_tracer_provider(tracer_provider)
    logger = logging.getLogger("scaler.test")
    logger.addHandler(logger_provider.make_handler(logging.INFO))
    logging.getLogger(EXPORTER_LOGGER_NAME).addHandler(logger_provider.make_handler(logging.INFO))

    with trace.get_tracer(__name__).start_as_current_span("logging.span"):
        try:
            raise ValueError("bad value")
        except ValueError:
            logger.warning("worker %s left", "w1", exc_info=True, extra={"event.name": "scaler.worker.left"})
    logging.getLogger(EXPORTER_LOGGER_NAME).warning("an exporter message")

    flushed.put(logger_provider.force_flush() and tracer_provider.force_flush())


def _tracer_provider_type(environment: Dict[str, str], provider_type: "multiprocessing.Queue[str]") -> None:
    os.environ.update(environment)

    from opentelemetry import trace

    from scaler.utility.telemetry_sdk import install_sdk

    install_sdk("provider-test", {}, None)
    provider_type.put(type(trace.get_tracer_provider()).__name__)


def _stop(process: multiprocessing.process.BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
    process.join(PROCESS_TIMEOUT_SECONDS)


class TestNativeTracing(unittest.TestCase):
    def setUp(self) -> None:
        setup_logger()
        logging_test_name(self)

        self.receiver = OTLPReceiver()
        self.receiver.start()
        self.addCleanup(self.receiver.stop)

    def _run(self, target, environment: Dict[str, str]) -> object:
        context = multiprocessing.get_context("spawn")
        result = context.Queue()
        process = context.Process(
            target=target, args=({"OTEL_EXPORTER_OTLP_ENDPOINT": self.receiver.endpoint, **environment}, result)
        )
        process.start()
        self.addCleanup(_stop, process)

        value = result.get(timeout=PROCESS_TIMEOUT_SECONDS)
        process.join(PROCESS_TIMEOUT_SECONDS)
        self.assertEqual(process.exitcode, 0)
        return value

    def test_spans_reach_the_collector_with_their_parent_kind_status_events_and_links(self) -> None:
        """A span opentelemetry-cpp exports keeps everything the Python span recorded."""
        self.assertTrue(self._run(_export_two_spans, {}))

        parent = self.receiver.spans_named("parent")[0]
        child = self.receiver.spans_named("child")[0]
        self.assertEqual(parent.service_name, "native-test")
        self.assertEqual(parent.attributes, {"long": LONG_VALUE, "number": 1})

        self.assertEqual(child.span.trace_id, parent.span.trace_id)
        self.assertEqual(child.span.parent_span_id, parent.span.span_id)
        self.assertEqual(child.span.kind, ProtoSpan.SPAN_KIND_CONSUMER)
        self.assertEqual(child.span.status.code, ProtoStatus.STATUS_CODE_ERROR)
        self.assertEqual(child.span.status.message, "boom")
        self.assertEqual([event.name for event in child.span.events], ["child.event"])
        self.assertEqual(child.span.links[0].span_id, parent.span.span_id)
        self.assertGreater(child.span.end_time_unix_nano, child.span.start_time_unix_nano)

    def test_the_configured_sampler_drops_spans_before_they_are_exported(self) -> None:
        self.assertTrue(self._run(_export_two_spans, {"OTEL_TRACES_SAMPLER": "always_off"}))
        self.assertEqual(self.receiver.spans, [])

    def test_a_ratio_of_zero_drops_root_spans(self) -> None:
        sampler = {"OTEL_TRACES_SAMPLER": "traceidratio", "OTEL_TRACES_SAMPLER_ARG": "0"}
        self.assertTrue(self._run(_export_root_and_child_of_sampled_remote_parent, sampler))
        self.assertEqual(self.receiver.spans, [])

    def test_a_parent_based_sampler_follows_a_sampled_remote_parent(self) -> None:
        """parentbased_always_off drops the root span, and keeps the child of a sampled parent in its trace."""
        sampler = {"OTEL_TRACES_SAMPLER": "parentbased_always_off"}
        self.assertTrue(self._run(_export_root_and_child_of_sampled_remote_parent, sampler))

        self.assertEqual(self.receiver.spans_named("root"), [])
        child = self.receiver.spans_named("child")[0]
        self.assertEqual(int.from_bytes(child.span.trace_id, "big"), REMOTE_TRACE_ID)
        self.assertEqual(int.from_bytes(child.span.parent_span_id, "big"), REMOTE_SPAN_ID)

    def test_attribute_limits_cut_the_count_and_the_length(self) -> None:
        limits = {"OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT": "1", "OTEL_ATTRIBUTE_VALUE_LENGTH_LIMIT": "10"}
        self.assertTrue(self._run(_export_two_spans, limits))

        parent = self.receiver.spans_named("parent")[0]
        self.assertEqual(parent.attributes, {"long": LONG_VALUE[:10]})

    def test_a_log_record_reaches_the_collector_with_its_attributes_and_span(self) -> None:
        """A record keeps its body, severity, extra fields, code and exception attributes, and the span it was in."""
        self.assertTrue(self._run(_log_inside_a_span, {}))

        log = self.receiver.logs_with_event("scaler.worker.left")[0]
        span = self.receiver.spans_named("logging.span")[0]
        self.assertEqual(log.body, "worker w1 left")
        self.assertEqual(log.record.severity_number, ProtoSeverity.SEVERITY_NUMBER_WARN)
        self.assertEqual(log.record.severity_text, "WARN")
        self.assertEqual(log.attributes["exception.type"], "ValueError")
        self.assertEqual(log.attributes["exception.message"], "bad value")
        self.assertIn("raise ValueError", str(log.attributes["exception.stacktrace"]))
        self.assertEqual(log.attributes["code.function.name"], "_log_inside_a_span")
        self.assertEqual(log.record.trace_id, span.span.trace_id)
        self.assertEqual(log.record.span_id, span.span.span_id)

    def test_the_exporters_own_log_records_are_not_exported(self) -> None:
        self.assertTrue(self._run(_log_inside_a_span, {}))
        self.assertEqual([log for log in self.receiver.logs if log.body == "an exporter message"], [])

    def test_native_export_is_the_default_and_false_keeps_the_python_sdk(self) -> None:
        self.assertEqual(self._run(_tracer_provider_type, {}), "NativeTracerProvider")
        self.assertEqual(self._run(_tracer_provider_type, {"SCALER_NATIVE_EXPORT": "false"}), "TracerProvider")
