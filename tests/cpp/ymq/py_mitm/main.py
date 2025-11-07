print("hello from python")

import sys

print(sys.path)

# flake8: noqa: E402

"""
This script provides a framework for running MITM test cases
"""

import argparse
import os
import signal
import subprocess
from typing import List
import platform

from scapy.all import IP, TCP  # type: ignore

from tests.cpp.ymq.py_mitm import passthrough, randomly_drop_packets, send_rst_to_client
from tests.cpp.ymq.py_mitm.mitm_types import AbstractMITM, TCPConnection

def main(pid: int, mitm_ip: str, mitm_port: int, remote_ip: str, server_port: int, mitm: AbstractMITM):
    """
    This function serves as a framework for man in the middle implementations
    A client connects to the MITM, then the MITM connects to a remote server
    The MITM sits inbetween the client and the server, manipulating the packets sent depending on the test case
    This function:
        1. creates an interface and prepares it for MITM
        2. handles connecting clients and handling connection closes
        3. delegates additional logic to a pluggable callable, `mitm`
        4. returns when both connections have terminated

    Args:
        pid: this is the pid of the test process, used for signaling readiness \
        we send SIGUSR1 to this process when the mitm is ready
        mitm_ip: The desired ip address of the mitm server \
        Windows: This parameter is ignored
        mitm_port: The desired port of the mitm server. \
        Linux: This is the port used to connect to the server, but the client is free to connect on any port \
        Windows: This parameter is ignored
        remote_ip: The remote ip for the TUNTAP interface. \
        This must be the ip address that the server is bound to
        server_port: The port that the remote server is bound to
        mitm: The core logic for a MITM test case. This callable may maintain its own state and is responsible \
        for sending packets over the interface (if it doesn't, nothing will happen)
    """
    system = platform.system()
    if system == "Windows":
        from tests.cpp.ymq.py_mitm.windivert import WindivertMITMInterface
        interface = WindivertMITMInterface(mitm_ip, mitm_port, remote_ip, server_port)

        print("setting event...")

        import win32api
        import win32event
        handle = win32event.OpenEvent(
            win32event.EVENT_MODIFY_STATE,  # access rights needed to set the event
            False,                           # do not inherit handle
            "Global\\PythonSignal"
        )
        win32event.SetEvent(handle)
        win32api.CloseHandle(handle)
        print("event set!")
    elif system in ("Linux", "Darwin"):
        from tests.cpp.ymq.py_mitm.tuntap import create_tuntap_interface
        interface = create_tuntap_interface("tun0", mitm_ip, remote_ip)

        # signal the caller that the interface has been created
        if pid > 0:
            os.kill(pid, signal.SIGUSR1)

    # these track information about our connections
    # we already know what to expect for the server connection, we are the connector
    client_conn = None

    # the port that the mitm uses to connect to the server
    # we increment the port for each new connection to avoid collisions
    mitm_server_port = mitm_port
    server_conn = TCPConnection(mitm_ip, mitm_server_port, remote_ip, server_port)

    # tracks the state of each connection
    client_sent_fin_ack = False
    client_closed = False
    server_sent_fin_ack = False
    server_closed = False

    while True:
        pkt = interface.recv()
        if not pkt.haslayer(IP) or not pkt.haslayer(TCP):
            continue
        ip = pkt[IP]
        tcp = pkt[TCP]

        # for a received packet, the destination ip and port are our local ip and port
        # and the source ip and port will be the remote ip and port
        sender = TCPConnection(pkt.dst, pkt.dport, pkt.src, pkt.sport)

        pretty = f"[{tcp.flags}]{(': ' + str(bytes(tcp.payload))) if tcp.payload else ''}"

        if not mitm.proxy(interface, pkt, sender, client_conn, server_conn):
            if sender == client_conn:
                print(f"[DROPPED]: -> {pretty}")
            elif sender == server_conn:
                print(f"[DROPPED]: <- {pretty}")
            else:
                print(f"[DROPPED]: ?? {pretty}")

            continue  # the segment was not proxied, so we can't update our internal state

        if sender == client_conn:
            print(f"-> {pretty}")
        elif sender == server_conn:
            print(f"<- {pretty}")

        if tcp.flags == "S":  # SYN from client
            if sender != client_conn or client_conn is None:
                print("-> [S]")
                print(f"[*] New connection from {ip.src}:{tcp.sport} to {ip.dst}:{tcp.dport}")
                client_conn = sender

                server_conn = TCPConnection(mitm_ip, mitm_server_port, remote_ip, server_port)

                # increment the port so that the next client connection (if there is one) uses a different port
                # mitm_server_port += 1

        if tcp.flags == "SA":  # SYN-ACK from server
            if sender == server_conn:
                print(f"[*] Connection to server established: {ip.src}:{tcp.sport} to {ip.dst}:{tcp.dport}")

        if tcp.flags.F and tcp.flags.A:  # FIN-ACK
            if sender == client_conn:
                client_sent_fin_ack = True
            if sender == server_conn:
                server_sent_fin_ack = True

        if tcp.flags.A:  # ACK
            if sender == client_conn and server_sent_fin_ack:
                server_closed = True
            if sender == server_conn and client_sent_fin_ack:
                client_closed = True

        if client_closed and server_closed:
            print("[*] Both connections closed")
            return


TESTCASES = {
    "passthrough": passthrough,
    "randomly_drop_packets": randomly_drop_packets,
    "send_rst_to_client": send_rst_to_client,
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Man in the middle test framework")
    parser.add_argument("pid", type=int, help="The pid of the test process, used for signaling")
    parser.add_argument("testcase", type=str, choices=TESTCASES.keys(), help="The MITM test case module name")
    parser.add_argument("mitm_ip", type=str, help="The desired ip address of the mitm server")
    parser.add_argument("mitm_port", type=int, help="The desired port of the mitm server")
    parser.add_argument("remote_ip", type=str, help="The desired remote ip for the TUNTAP interface")
    parser.add_argument("server_port", type=int, help="The port that the remote server is bound to")

    args, unknown = parser.parse_known_args()

    module = TESTCASES[args.testcase]

    main(args.pid, args.mitm_ip, args.mitm_port, args.remote_ip, args.server_port, module.MITM(*unknown))
