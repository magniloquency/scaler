import asyncio
import hashlib
import ymq


async def main():
    ctx = ymq.IOContext()
    print("created ioctx")
    s1 = await ctx.createIOSocket("s1", ymq.IOSocketType.Binder)
    print("created binder")
    s2 = await ctx.createIOSocket("s2", ymq.IOSocketType.Connector)
    print("created connector")

    await s1.bind("tcp://127.0.0.1:8080")
    print("bound")
    await s2.connect("tcp://127.0.0.1:8080")
    print("connected")

    data = b"hello from s1"
    print(f"sending: {hashlib.sha1(data).hexdigest()[:8]}")

    x = s1.send(ymq.Message(b"s2", data))
    y = s2.recv()

    await x
    message = await y
    print(f"Received message: {message.payload.data.decode()} {hashlib.sha1(message.payload.data).hexdigest()[:8]} from {message.address.data}")



asyncio.run(main())
