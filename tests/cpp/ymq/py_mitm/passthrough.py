"""
This MITM acts as a transparent passthrough, it simply forwards packets as they are,
minus necessary header changes to retransmit
This MITM should have no effect on the client and server,
and they should behave as if the MITM is not present
"""

from typing import Optional

from tests.cpp.ymq.py_mitm.mitm_types import IP, TCP, AbstractMITM, TCPConnection, AbstractMITMInterface


class MITM(AbstractMITM):
    def proxy(
        self,
        tuntap: AbstractMITMInterface,
        pkt: IP,
        sender: TCPConnection,
        client_conn: Optional[TCPConnection],
        server_conn: TCPConnection,
    ) -> bool:
        print(f"pkt: from ({pkt[IP].src}:{pkt[TCP].sport}) to ({pkt[IP].dst}:{pkt[TCP].dport})")
        #tuntap.send(pkt)
        if sender == client_conn or client_conn is None:
            pass
            tuntap.send(server_conn.rewrite(pkt))
        elif sender == server_conn:
            pass
            tuntap.send(client_conn.rewrite(pkt))
        return True
