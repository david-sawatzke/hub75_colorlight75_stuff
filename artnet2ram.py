import unittest
import random
from litex.soc.interconnect import stream
from migen import *
from litex.soc.interconnect.packet import Header, HeaderField
from litex.soc.interconnect.stream import SyncFIFO
from litex.gen.common import reverse_bytes
from liteeth.packet import Depacketizer, Packetizer
from litedram.frontend.dma import LiteDRAMDMAWriter
from liteeth.common import eth_udp_user_description

max_universe = (8 * 4 * 32 * 64) // 170 + 1
sdram_offset = 0x00400000 // 2 // 4

artnet_header_length = 18

artnet_header_fields = {
    "ident": HeaderField(0, 0, 8 * 8),
    "op": HeaderField(8, 0, 2 * 8),
    "protocol": HeaderField(10, 0, 2 * 8),
    # Ignore this
    "sequence": HeaderField(12, 0, 1 * 8),
    # Not important
    "phys": HeaderField(13, 0, 1 * 8),
    # Needs to be swapped around when reading the field
    "universe": HeaderField(14, 0, 2 * 8),
    "length": HeaderField(16, 0, 2 * 8),
}
artnet_header = Header(
    artnet_header_fields, artnet_header_length, swap_field_bytes=True
)


def artnet_stream_description():
    payload_layout = [
        ("data", 32),
        ("last_be", 4),
    ]
    return stream.EndpointDescription(payload_layout)


def artnet_header_stream_description():
    param_layout = artnet_header.get_layout()
    payload_layout = [
        ("data", 32),
        ("last_be", 4),
    ]
    return stream.EndpointDescription(payload_layout, param_layout)


def artnet_write_description():
    payload_layout = [
        ("address", 32),
        ("data", 32),
    ]
    return stream.EndpointDescription(payload_layout)


class ArtnetDepacketizer(Depacketizer):
    def __init__(self):
        Depacketizer.__init__(
            self,
            artnet_stream_description(),
            artnet_header_stream_description(),
            artnet_header,
        )


class ArtnetReceiver(Module):
    def __init__(self):
        self.sink = stream.Endpoint(artnet_stream_description())
        self.source = source = stream.Endpoint(artnet_write_description())
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        self.submodules.data_converter = converter = RawDataStreamToColorStream()
        self.submodules.depacketizer = ArtnetDepacketizer()
        sink = stream.Endpoint(artnet_header_stream_description())
        self.comb += [
            self.sink.connect(self.depacketizer.sink),
            self.depacketizer.source.connect(sink),
        ]

        self.valid_packet = Signal()
        data_counter = Signal(max=170)
        ram_offset = Signal(max=(8 * 4 * 32 * 64 - 170))
        # Currently unused
        # length = Signal(max=512)

        fsm.act(
            "IDLE",
            NextValue(data_counter, 0),
            converter.reset.eq(1),
            If(
                sink.valid,
                If(
                    (sink.ident == int.from_bytes(b"Art-Net\0", byteorder="big"))
                    & (sink.op == 0x0050)  # Wrong endian
                    & (sink.length <= 510)
                    & (reverse_bytes(sink.universe) < max_universe),
                    self.valid_packet.eq(1),
                    NextValue(ram_offset, reverse_bytes(sink.universe) * 170),
                    # NextValue(length, sink.length * 170),
                    NextState("COPY_TO_RAM"),
                ).Else(
                    NextState("WAIT_TILL_DONE"),
                ),
            ),
        )

        fsm.act(
            "WAIT_TILL_DONE",
            sink.ready.eq(1),
            If(sink.valid & sink.last, NextState("IDLE")),
        )
        fsm.act(
            "COPY_TO_RAM",
            sink.connect(
                converter.sink, keep={"valid", "ready", "data", "last", "last_be"}
            ),
            converter.source.connect(self.source, keep={"valid", "ready", "data"}),
            self.source.address.eq(sdram_offset + ram_offset + data_counter),
            If(
                converter.source.valid & converter.source.ready,
                NextValue(data_counter, data_counter + 1),
                If(converter.source.last, NextState("IDLE")),
            ),
        )


class Artnet2RAM(Module):
    def __init__(self, sdram):
        # Interface
        self.sink = stream.Endpoint(eth_udp_user_description(32))
        # If the fifo is (semi-)full, signal other parts to reduce memory bandwidth needs
        self.fifo_backlog = Signal()
        # The packet received via the sink is valid (can be used to drop processing of the packet in other parts
        self.valid_packet = Signal()

        write_port = sdram.crossbar.get_port(mode="write", data_width=32)
        self.submodules.writer = LiteDRAMDMAWriter(write_port)
        self.submodules.artnet_receiver = ArtnetReceiver()
        self.submodules.fifo = SyncFIFO(artnet_write_description(), 512)

        self.comb += [
            self.sink.connect(
                self.artnet_receiver.sink,
                keep=["data", "last_be", "valid", "ready", "last"],
            ),
            self.artnet_receiver.source.connect(self.fifo.sink, omit=["ready"]),
            self.fifo.source.connect(
                self.writer.sink,
            ),
            # TODO indicate if this happens somehow Just drop data if the fifo is full
            self.artnet_receiver.source.ready.eq(1),
            self.valid_packet.eq(self.artnet_receiver.valid_packet),
            self.fifo_backlog.eq(self.fifo.level > 256),
        ]


@ResetInserter()
class RawDataStreamToColorStream(Module):
    def __init__(self):
        self.sink = sink = stream.Endpoint(artnet_stream_description())
        self.source = source = stream.Endpoint(artnet_stream_description())

        sink_d = stream.Endpoint(artnet_stream_description())
        # Four states for each possible input alignment
        # Match last_be to last!! output?

        self.submodules.fsm = fsm = FSM(reset_state="0")

        fsm.act(
            "0",
            source.data.eq(sink.data[0:24]),
            source.last_be.eq(sink.last_be[0:3]),
            source.valid.eq(sink.valid),
            sink.ready.eq(source.ready),
            If(
                source.ready & source.valid,
                NextState("1"),
            ),
        )
        fsm.act(
            "1",
            source.data.eq(Cat(sink_d.data[24:], sink.data[0:16])),
            source.last_be.eq(Cat(sink_d.last_be[3:], sink.last_be[0:2])),
            source.valid.eq(sink.valid),
            sink.ready.eq(source.ready),
            If(
                source.ready & source.valid,
                NextState("2"),
            ),
        )
        fsm.act(
            "2",
            source.data.eq(Cat(sink_d.data[16:], sink.data[0:8])),
            source.last_be.eq(Cat(sink_d.last_be[2:], sink.last_be[0:1])),
            source.valid.eq(sink.valid),
            sink.ready.eq(source.ready),
            If(
                source.ready & source.valid,
                NextState("3"),
            ),
        )
        fsm.act(
            "3",
            source.data.eq(sink_d.data[8:]),
            source.last_be.eq(sink_d.last_be[1:]),
            source.valid.eq(1),
            sink.ready.eq(0),
            If(
                source.ready & source.valid,
                NextState("0"),
            ),
        )

        self.comb += [
            If(source.last_be != 0, source.last.eq(1)),
        ]

        self.sync += [
            If(sink.ready & sink.valid, sink_d.eq(sink)),
        ]


## Tests


class TestStream(unittest.TestCase):
    def fourtothree_test(self, dut):
        prng = random.Random(42)

        def generator(dut, valid_rand=90):
            for data in range(0, 48, 4):
                yield dut.sink.valid.eq(1)
                yield dut.sink.data.eq(
                    data | ((data + 1) << 8) | ((data + 2) << 16) | ((data + 3) << 24)
                )
                yield
                while (yield dut.sink.ready) == 0:
                    yield
                yield dut.sink.valid.eq(0)
                while prng.randrange(100) < valid_rand:
                    yield

        def checker(dut, ready_rand=90):
            dut.errors = 0
            for data in range(0, 48, 3):
                yield dut.source.ready.eq(0)
                yield
                while (yield dut.source.valid) == 0:
                    yield
                while prng.randrange(100) < ready_rand:
                    yield
                yield dut.source.ready.eq(1)
                yield
                if (yield dut.source.data) != (
                    data | ((data + 1) << 8) | ((data + 2) << 16)
                ):
                    dut.errors += 1
            yield

        run_simulation(dut, [generator(dut), checker(dut)])
        self.assertEqual(dut.errors, 0)

    def test_fourtothree_valid(self):
        dut = RawDataStreamToColorStream()
        self.fourtothree_test(dut)

    def footest_artnetreceiver(self):
        artnet_hex_data = """
            41 72 74 2d 4e 65
            74 00 00 50 00 0e 4b 00 0c 00 01 fe 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
            00 00 00 00 00 00 00 DE EE ED
        """
        proto_ver = 14
        sequence = 75
        universe = 12
        length = 510
        artnet_data = bytearray.fromhex(artnet_hex_data)
        artnet_data_length = length + 18

        prng = random.Random(42)
        # Hacky!!
        def generator(dut, data, length, valid_rand=90):
            for idx in range(0, length, 4):
                yield dut.sink.valid.eq(1)
                yield dut.sink.data.eq(
                    data[idx]
                    | (data[idx + 1] << 8)
                    | (data[idx + 2] << 16)
                    | (data[idx + 3] << 24)
                )
                yield
                while (yield dut.sink.ready) == 0:
                    yield
                yield dut.sink.valid.eq(0)
                while prng.randrange(100) < valid_rand:
                    yield
            print("Generator done")

        def checker(dut, length, ready_rand=90):
            for idx in range(0, length):
                print(idx)
                yield dut.source.ready.eq(0)
                yield
                while (yield dut.source.valid) == 0:
                    yield
                while prng.randrange(100) < ready_rand:
                    yield
                yield dut.source.ready.eq(1)
                yield
                # if (yield dut.source.data) != (
                #     data | ((data + 1) << 8) | ((data + 2) << 16)
                # ):
                #     dut.errors += 1
            yield
            print("Receiver done")

        dut = ArtnetReceiver()
        run_simulation(
            dut,
            [generator(dut, artnet_data, artnet_data_length), checker(dut, 170)],
            vcd_name="depacktest.vcd",
        )
        self.assertEqual(dut.errors, 0)
