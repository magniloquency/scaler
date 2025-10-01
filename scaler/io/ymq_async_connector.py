import logging
import os
import uuid
from typing import Awaitable, Callable, Literal, Optional

from scaler.io.ymq import ymq

from scaler.io.mixins import AsyncConnector
from scaler.io.utility import deserialize, serialize
from scaler.protocol.python.mixins import Message
from scaler.utility.zmq_config import ZMQConfig, ZMQType


class YMQAsyncConnector(AsyncConnector):
    def __init__(
        self,
        context: ymq.IOContext,
        name: str,
        socket_type: int,
        address: ZMQConfig,
        bind_or_connect: Literal["bind", "connect"],
        callback: Optional[Callable[[Message], Awaitable[None]]],
        identity: Optional[bytes],
    ):
        self._address = address
        self._context = context

        if identity is None:
            identity = f"{os.getpid()}|{name}|{uuid.uuid4().bytes.hex()}".encode()
        self._identity = identity

        self._socket = self._context.createIOSocket_sync(self.identity.decode(), socket_type)

        if self._address.type != ZMQType.tcp:
            raise ValueError(f"YMQ only supports tcp transport, got {self._address.type}")

        if bind_or_connect == "bind":
            self._socket.bind_sync(self.address)
        elif bind_or_connect == "connect":
            self._socket.connect_sync(self.address)
        else:
            raise TypeError("bind_or_connect has to be 'bind' or 'connect'")

        self._callback: Optional[Callable[[Message], Awaitable[None]]] = callback

    def __del__(self):
        self.destroy()

    def destroy(self):
        self._context = None
        self._socket = None

    @property
    def identity(self) -> bytes:
        return self._identity

    @property
    def socket(self) -> ymq.IOSocket:
        return self._socket

    @property
    def address(self) -> str:
        return self._address.to_address()

    async def routine(self):
        if self._callback is None:
            return

        message: Optional[Message] = await self.receive()
        if message is None:
            return

        await self._callback(message)

    async def receive(self) -> Optional[Message]:
        if self._socket is None:
            return None

        msg = await self._socket.recv()

        # TODO: zero-copy
        result: Optional[Message] = deserialize(msg.payload.data)
        if result is None:
            logging.error(f"received unknown message: {msg.payload!r}")
            return None

        return result

    async def send(self, message: Message):
        await self._socket.send(ymq.Message(None, serialize(message)))
