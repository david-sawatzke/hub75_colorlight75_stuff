#!/usr/bin/env python3
from liteeth.common import *
from liteeth.core.udp import LiteEthUDPDepacketizer


class SmolEthUDP(Module):
    def __init__(self, ip, udp_port, dw=8):
        ip_port = ip.crossbar.get_port(udp_protocol, dw)

        self.sink = sink = stream.Endpoint(eth_ipv4_user_description(dw))
        self.comb += [ip_port.source.connect(self.sink)]

        # Depacketizer.
        self.submodules.depacketizer = depacketizer = LiteEthUDPDepacketizer(dw)

        self.source = source = stream.Endpoint(eth_udp_user_description(dw))
        # Data-Path.
        self.comb += [
            sink.connect(depacketizer.sink),
        ]

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        fsm.act(
            "IDLE",
            If(
                depacketizer.source.valid,
                NextState("DROP"),
                If(
                    (sink.protocol == udp_protocol)
                    & (depacketizer.source.dst_port == udp_port),
                    NextState("RECEIVE"),
                ),
            ),
        )
        fsm.act(
            "RECEIVE",
            depacketizer.source.connect(
                source, keep={"data", "last_be", "last", "valid", "ready"}
            ),
            source.ip_address.eq(sink.ip_address),
            source.length.eq(depacketizer.source.length - udp_header.length),
            If(source.valid & source.ready & source.last, NextState("IDLE")),
        )

        fsm.act(
            "DROP",
            depacketizer.source.ready.eq(1),
            If(depacketizer.source.valid & depacketizer.source.last, NextState("IDLE")),
        )
