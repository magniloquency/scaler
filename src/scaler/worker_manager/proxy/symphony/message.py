import array
import functools
from typing import Any, Type

from scaler.worker_manager.proxy.symphony.soam_api import load_soam_api


@functools.lru_cache(maxsize=1)
def create_soam_message_class() -> Type[Any]:
    """Build the ``soamapi.Message`` subclass that carries task payloads.

    The class is built on demand because its base class only exists once ``soamapi`` is importable.
    """
    soam_api = load_soam_api()

    # mypy cannot resolve a base class that is only available at run time
    class SoamMessage(soam_api.Message):  # type: ignore[name-defined]
        def __init__(self, payload: bytes = b""):
            self.__payload = payload

        def set_payload(self, payload: bytes):
            self.__payload = payload

        def get_payload(self) -> bytes:
            return self.__payload

        def on_serialize(self, stream):
            payload_array = array.array("b", self.get_payload())
            stream.write_byte_array(payload_array, 0, len(payload_array))

        def on_deserialize(self, stream):
            self.set_payload(stream.read_byte_array("b"))

    return SoamMessage
