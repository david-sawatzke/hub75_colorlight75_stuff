# Smol tcp ethernet stack
# Intended for a hybrid stack, where a lot of udp traffic is received and processed by gateware, while all other ethernet tasks are handled using the softcore
# Only the softcore can send data
# Benefits:
# - Uses less resources than LiteETH (less features)
# - Can share a single IP
# Disadvantages:
# - Only supports a single IP & UDP port for hardware processing
# - Hardware receiving circuitry needs to signal packets that shouldn't be received by the
#   softcore and some leftovers may still be received by the softcore
# - Needs a functioning software ethernet stack to provide ARP at least
# - Less configurable
# - No etherbone
# License: Same one as LiteETH (two clause BSD)
# 2021-2022 <d-smoleth@sawatzke.dev>
# SPDX-License-Identifier: BSD-2-Clause
from liteeth.common import *
from liteeth.core.udp import LiteEthUDPDepacketizer
from liteeth.core.ip import LiteEthIPV4Depacketizer
from liteeth.mac.common import LiteEthMACDepacketizer
from liteeth.mac.core import LiteEthMACCore
from liteeth.mac.wishbone import LiteEthMACWishboneInterface


class SmolEthUDP(Module):
    def __init__(self, udp_port, dw=8):
        self.sink = sink = stream.Endpoint(eth_ipv4_user_description(dw))
        self.source = source = stream.Endpoint(eth_udp_user_description(dw))

        # Depacketizer.
        self.submodules.depacketizer = depacketizer = LiteEthUDPDepacketizer(dw)

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
    def __init__(self, ip_address, protocol, dw=8):
        self.sink = sink = stream.Endpoint(eth_mac_description(dw))
        self.source = source = stream.Endpoint(eth_ipv4_user_description(dw))

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


class SmolEthMACFilter(Module):
    def __init__(self, mac_address, dw=8):

        self.sink = sink = stream.Endpoint(eth_phy_description(dw))
        self.source = source = stream.Endpoint(eth_mac_description(dw))

        # # #

        # Depacketizer.
        self.submodules.depacketizer = depacketizer = LiteEthMACDepacketizer(dw)
        self.comb += sink.connect(depacketizer.sink)

        # FSM.
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act(
            "IDLE",
            If(
                depacketizer.source.valid,
                NextState("DROP"),
                If(
                    (depacketizer.source.target_mac == mac_address)
                    & (depacketizer.source.ethernet_type == ethernet_type_ip),
                    NextState("RECEIVE"),
                ),
            ),
        )
        self.comb += [
            depacketizer.source.connect(
                source, keep={"last", "data", "error", "last_be"}
            ),
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
                depacketizer.source.valid & depacketizer.source.last,
                NextState("IDLE"),
            ),
        )


class SmolEthStreamSplitter(Module):
    def __init__(self, description):
        self.sink = sink = stream.Endpoint(description)
        self.source1 = source1 = stream.Endpoint(description)
        self.source2 = source2 = stream.Endpoint(description)

        source1_already_read = Signal()
        source2_already_read = Signal()

        self.comb += [
            self.sink.connect(self.source1, omit={"ready", "valid"}),
            self.sink.connect(self.source2, omit={"ready", "valid"}),
            self.source1.valid.eq(self.sink.valid & ~source1_already_read),
            self.source2.valid.eq(self.sink.valid & ~source2_already_read),
            self.sink.ready.eq(
                (self.source1.ready | source1_already_read)
                & (self.source2.ready | source2_already_read)
            ),
        ]

        self.sync += [
            If(
                self.sink.valid & self.sink.ready,
                # Reset ready state
                source1_already_read.eq(0),
                source2_already_read.eq(0),
            ).Elif(
                self.sink.valid,
                If(
                    self.source1.ready,
                    source1_already_read.eq(1),
                ),
                If(
                    self.source2.ready,
                    source2_already_read.eq(1),
                ),
            )
        ]


class SmolEth(Module, AutoCSR):
    def __init__(self, phy, udp_port, mac_address, ip_address, dw):
        assert dw % 8 == 0
        # Add mac & ip registers
        self.ip_address = CSRStorage(32, reset=ip_address, atomic_write=True)
        self.mac_address = CSRStorage(48, reset=mac_address, atomic_write=True)

        self.submodules.core = LiteEthMACCore(
            phy=phy,
            dw=dw,
            with_sys_datapath=True,
            with_preamble_crc=True,
        )

        nrxslots = 2
        ntxslots = 2

        # Wishbone MAC
        self.rx_slots = CSRConstant(nrxslots)
        self.tx_slots = CSRConstant(ntxslots)
        self.slot_size = CSRConstant(2 ** bits_for(eth_mtu))

        wishbone_interface = LiteEthMACWishboneInterface(
            dw=dw,
            nrxslots=nrxslots,
            ntxslots=ntxslots,
            endianness="little",
        )

        self.submodules.interface = wishbone_interface
        self.ev, self.bus_rx, self.bus_tx = self.interface.sram.ev, self.interface.bus_rx, self.interface.bus_tx
        # Use this instead of AutoCSR to maintain the same names as in liteeth
        self.csrs = (
            self.interface.get_csrs()
            + self.core.get_csrs()
            + [self.ip_address, self.mac_address]
        )

        self.submodules.splitter = SmolEthStreamSplitter(eth_phy_description(dw))

        # Hardware UDP/IP "Stack"
        self.submodules.udp = SmolEthUDP(udp_port, dw)
        self.submodules.ip = SmolEthIP(self.ip_address.storage, udp_protocol, dw)
        self.submodules.mac_filter = SmolEthMACFilter(self.mac_address.storage, dw)

        self.submodules.invalidator = SmolEthInvalidator(
            # Minimum of words that are required for a packet processed by the hardware
            # Avoids dropping the next packet in the first few words if the hardware has a bit of latency
            60 // 4,
            eth_phy_description(dw),
        )
        self.comb += [
            self.core.source.connect(self.splitter.sink),
            self.interface.source.connect(self.core.sink),
            self.splitter.source1.connect(self.invalidator.sink),
            self.splitter.source2.connect(self.mac_filter.sink),
            self.mac_filter.source.connect(self.ip.sink),
            self.ip.source.connect(self.udp.sink),
            self.invalidator.source.connect(self.interface.sink),
        ]

    def get_csrs(self):
        return self.csrs


# Drops the current packet for the ram interface if it's processed by the hardware
# length is the minimum length a packet has to be to be considered valid
class SmolEthInvalidator(Module):
    def __init__(self, length, description):
        self.sink = sink = stream.Endpoint(description)
        self.source = source = stream.Endpoint(description)

        self.invalid = Signal()

        length_counter = Signal(max=1500)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act(
            "IDLE",
            NextValue(length_counter, 1),
            self.sink.connect(self.source),
            If(
                sink.valid & sink.ready,
                NextState("COPY"),
            ),
        )
        fsm.act(
            "COPY",
            self.sink.connect(self.source),
            If(
                self.invalid & (length_counter > length),
                NextState("INVALIDATE"),
            ),
            If(
                self.sink.valid & self.sink.ready,
                If(self.sink.last, NextState("IDLE")),
                NextValue(length_counter, length_counter + 1),
            ),
        )
        fsm.act(
            "INVALIDATE",
            self.source.error.eq(0xFF),
            self.source.last_be.eq(0x01),
            self.source.last.eq(1),
            self.source.valid.eq(1),
            # Discard the incoming bytes
            # With the normal interface this isn't an issue since it's always ready
            self.sink.ready.eq(~(self.sink.last & self.sink.valid)),
            If(self.source.ready, NextState("WAIT_TILL_DONE")),
        )
        fsm.act(
            "WAIT_TILL_DONE",
            self.sink.ready.eq(1),
            If(self.sink.valid & self.sink.last, NextState("IDLE")),
        )
