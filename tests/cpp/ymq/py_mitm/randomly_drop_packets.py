"""
This MITM drops a % of packets
"""

import random
from typing import Optional

from tests.cpp.ymq.py_mitm.types import IP, AbstractMITM, TCPConnection, TunTapInterface


class MITM(AbstractMITM):
    def __init__(self, drop_pcent: str):
        self.drop_pcent = float(drop_pcent)
        self.consecutive_drop_limit = 3
        self.client_consecutive_drops = 0
        self.server_consecutive_drops = 0

    @property
    def can_drop_client(self) -> bool:
        return self.client_consecutive_drops < self.consecutive_drop_limit

    @property
    def can_drop_server(self) -> bool:
        return self.server_consecutive_drops < self.consecutive_drop_limit

    def proxy(
        self,
        tuntap: TunTapInterface,
        pkt: IP,
        sender: TCPConnection,
        client_conn: Optional[TCPConnection],
        server_conn: TCPConnection,
    ) -> bool:
        drop = random.random() < self.drop_pcent

        if sender == client_conn or client_conn is None:
            if self.can_drop_client and drop:
                self.client_consecutive_drops += 1
                return False

            self.client_consecutive_drops = 0
            tuntap.send(server_conn.rewrite(pkt))
        elif sender == server_conn:
            if self.can_drop_server and drop:
                self.server_consecutive_drops += 1
                return False

            self.server_consecutive_drops == 0
            tuntap.send(client_conn.rewrite(pkt))
        return True
