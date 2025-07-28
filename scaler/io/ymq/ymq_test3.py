import ymq
from multiprocessing import Process
import itertools as itools
import time

def peerA():
    ctx = ymq.IOContext()
    sock = ctx.createIOSocket_sync("A", ymq.IOSocketType.Connector)
    sock.connect_sync("tcp://127.0.0.1:8181")

    for i in itools.count():
        sock.send_sync(ymq.Message(None, f"A: {i}".encode()))
        msg = sock.recv_sync()
        print(f"{msg.address.data.decode()}; {msg.payload.data.decode()}")
        time.sleep(3)

def peerB():
    ctx = ymq.IOContext()
    sock = ctx.createIOSocket_sync("B", ymq.IOSocketType.Binder)
    sock.bind_sync("tcp://127.0.0.1:8181")

    for i in itools.count():
        msg = sock.recv_sync()
        print(f"{msg.address.data.decode()}; {msg.payload.data.decode()}")
        time.sleep(3)
        sock.send_sync(ymq.Message(b"A", f"B: {i}".encode()))
        

s = Process(name="A", target=peerA)
r = Process(name="B", target=peerB)

s.start()
r.start()

input()

s.kill()
r.kill()
