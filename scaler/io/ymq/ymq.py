# This file wraps the interface exported by the C implementation of the module
# and provides a more ergonomic interface supporting both asynchronous and synchronous execution

__all__ = ["IOSocket", "IOContext", "Message", "IOSocketType", "YMQException", "Bytes", "ErrorCode"]

import asyncio
import concurrent.futures
from typing import Optional

from scaler.io.ymq._ymq import BaseIOSocket, Message, IOSocketType, BaseIOContext, YMQException, Bytes, ErrorCode

async def call_async(func, *args, **kwargs):
    future = asyncio.get_event_loop().create_future()
    def callback(result):
        if future.done():
            return

        if isinstance(result, Exception):
            method = future.set_exception
        else:
            method = future.set_result

        loop = future.get_loop()
        loop.call_soon_threadsafe(method, result)

    func(*args, **kwargs, callback=callback)
    return await future

def call_sync(func, *args, timeout: Optional[float] = None, **kwargs):
    future = concurrent.futures.Future()
    def callback(result):
        if future.done():
            return

        if isinstance(result, Exception):
            future.set_exception(result)
        else:
            future.set_result(result)

    func(*args, **kwargs, callback=callback)
    return future.result(timeout)

class IOSocket:
    _base: BaseIOSocket

    def __init__(self, base: BaseIOSocket) -> None:
        self._base = base

    @property
    def socket_type(self) -> IOSocketType:
        return self._base.socket_type

    @property
    def identity(self) -> str:
        return self._base.identity

    async def bind(self, address: str) -> None:
        """Bind the socket to an address and listen for incoming connections"""
        await call_async(self._base.bind, address)

    def bind_sync(self, address: str, /, timeout: Optional[float] = None) -> None:
        """Bind the socket to an address and listen for incoming connections"""
        call_sync(self._base.bind, address, timeout=timeout)

    async def connect(self, address: str) -> None:
        """Connect to a remote socket"""
        return await call_async(self._base.connect, address)

    def connect_sync(self, address: str, /, timeout: Optional[float] = None) -> None:
        """Connect to a remote socket"""
        return call_sync(self._base.connect, address, timeout=timeout)
    
    async def send(self, message: Message) -> None:
        """Send a message to one of the socket's peers"""
        await call_async(self._base.send, message)

    def send_sync(self, message: Message, /, timeout: Optional[float] = None) -> None:
        """Send a message to one of the socket's peers"""
        call_sync(self._base.send, message, timeout=timeout)

    async def recv(self) -> Message:
        """Receive a message from one of the socket's peers"""
        return await call_async(self._base.recv)

    def recv_sync(self, /, timeout: Optional[float] = None) -> Message:
        """Receive a message from one of the socket's peers"""
        return call_sync(self._base.recv, timeout=timeout)

class IOContext:
    _base: BaseIOContext

    def __init__(self, num_threads: int = 1) -> None:
        self._base = BaseIOContext(num_threads)

    async def createIOSocket(self, identity: str, socket_type: IOSocketType) -> IOSocket:
        """Create an io socket with an identity and socket type"""
        return IOSocket(await call_async(self._base.createIOSocket, identity, socket_type))

    def createIOSocket_sync(self, identity: str, socket_type: IOSocketType) -> IOSocket:
        """Create an io socket with an identity and socket type"""
        return IOSocket(call_sync(self._base.createIOSocket, identity, socket_type))
