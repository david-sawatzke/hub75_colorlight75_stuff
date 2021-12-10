#!/usr/bin/env python3
from liteeth.common import *
from liteeth.core.udp import LiteEthUDPDepacketizer
from liteeth.core.ip import LiteEthIPV4Depacketizer


class SmolEthUDP(Module):
    def __init__(self, ip, udp_port, dw=8):

        self.sink = sink = stream.Endpoint(eth_ipv4_user_description(dw))
        self.comb += [ip.source.connect(self.sink)]

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


class SmolEthIP(Module):
    def __init__(self, mac, ip_address, protocol, dw=8):
        mac_port = mac.crossbar.get_port(ethernet_type_ip, dw)

        self.sink = sink = stream.Endpoint(eth_mac_description(dw))
        self.source = source = stream.Endpoint(eth_ipv4_user_description(dw))

        self.comb += [mac_port.source.connect(sink)]
        # # #

        # Depacketizer.
        self.submodules.depacketizer = depacketizer = LiteEthIPV4Depacketizer(dw)
        self.comb += sink.connect(depacketizer.sink)

        # FSM.
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act(
            "IDLE",
            If(
                depacketizer.source.valid,
                NextState("DROP"),
                If(
                    (depacketizer.source.target_ip == ip_address)
                    & (depacketizer.source.version == 0x4)
                    & (depacketizer.source.ihl == 0x5)
                    & (depacketizer.source.protocol == protocol),
                    NextState("RECEIVE"),
                ),
            ),
        )
        self.comb += [
            depacketizer.source.connect(
                source, keep={"last", "protocol", "data", "error", "last_be"}
            ),
            source.length.eq(depacketizer.source.total_length - (0x5 * 4)),
            source.ip_address.eq(depacketizer.source.sender_ip),
        ]
        fsm.act(
            "RECEIVE",
            depacketizer.source.connect(source, keep={"valid", "ready"}),
            If(source.valid & source.ready & source.last, NextState("IDLE")),
        )
        fsm.act(
            "DROP",
            depacketizer.source.ready.eq(1),
            If(
                depacketizer.source.valid
                & depacketizer.source.last
                & depacketizer.source.ready,
                NextState("IDLE"),
            ),
        )
