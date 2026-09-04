"""IBM Spectrum Symphony service that runs cloudpickle-serialized callables.

This is the service side of the Symphony worker manager. The worker manager sends
``cloudpickle.dumps((function, *arguments))`` as the task payload, so this container deserializes that
tuple, calls the function, and sends back the cloudpickled return value.
``scaler.worker_manager.proxy.symphony.execution_backend`` is the client side of the same contract.

``setup_application.py`` packages and deploys this file. Symphony runs it under the interpreter named by
the ``startCmd`` of the generated application profile, so that interpreter needs ``cloudpickle`` and a
matching ``soamapi``.
"""

import array

try:
    # Symphony ships soamapi as one bytecode directory per interpreter, below the lib64 on PYTHONPATH.
    # Importing soamapiversion appends the directory matching the running interpreter. A PYTHONPATH that
    # names that directory outright does not need it, so its absence is not an error.
    import soamapiversion  # noqa: F401
except ImportError:
    pass

import cloudpickle
import soamapi


class PickledPayloadMessage(soamapi.Message):
    """Carries an opaque cloudpickle payload in both directions."""

    def __init__(self, payload: bytes = b"") -> None:
        self._payload = payload

    def set_payload(self, payload: bytes) -> None:
        self._payload = payload

    def get_payload(self) -> bytes:
        return self._payload

    def on_serialize(self, stream) -> None:
        payload_array = array.array("b", self.get_payload())
        stream.write_byte_array(payload_array, 0, len(payload_array))

    def on_deserialize(self, stream) -> None:
        self.set_payload(stream.read_byte_array("b").tobytes())


class PickleRunnerServiceContainer(soamapi.ServiceContainer):
    """Calls the function in each task payload and returns its result."""

    def on_create_service(self, service_context) -> None:
        return

    def on_session_enter(self, session_context) -> None:
        return

    def on_invoke(self, task_context) -> None:
        input_message = PickledPayloadMessage()
        task_context.populate_task_input(input_message)

        function, *arguments = cloudpickle.loads(input_message.get_payload())

        task_context.set_task_output(PickledPayloadMessage(cloudpickle.dumps(function(*arguments))))

    def on_session_leave(self) -> None:
        return

    def on_destroy_service(self) -> None:
        return


if __name__ == "__main__":
    PickleRunnerServiceContainer().run()
