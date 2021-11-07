import unittest
import random
from litex.soc.interconnect import stream
from migen import *
from litex.soc.interconnect.packet import Header, HeaderField
from liteeth.packet import Depacketizer, Packetizer

sdram_offset = 0x00400000 // 2 // 4

artnet_header_length = 18
# TODO fix endian
artnet_header_fields = {
    "ident": HeaderField(0, 0, 8 * 8),
    "op": HeaderField(8, 0, 2 * 8),
    "protocol": HeaderField(10, 0, 2 * 8),
    # Ignore this
    "sequence": HeaderField(12, 0, 1 * 8),
    # Not important
    "phys": HeaderField(13, 0, 1 * 8),
    "universee": HeaderField(14, 0, 2 * 8),
    # Needs to be swapped around!!
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
        ("data", 32),
        ("address", 32),
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


# TODO make *sure* to not receive broadcasts!!!!
class ArtnetReceiver(Module):
    def __init__(self):
        # Temporary, replace with udp description
        self.sink = stream.Endpoint(artnet_stream_description())
        self.source = source = stream.Endpoint(artnet_write_description())
        self.submodule.fsm = fsm = FSM(reset_state="IDLE")
        self.submodule.data_converter = converter = RawDataStreamToColorStream()
        self.submodule.depacketizer = ArtnetDepacketizer()
        sink = stream.Endpoint(artnet_header_stream_description())
        self.comb += [
            self.sink.connect(self.depacketizer.sink),
            self.depacketizer.source.connect(sink),
        ]

        data_counter = Signal(max=170)
        ram_offset = Signal(max=(8 * 4 * 32 * 64 - 170))
        length = Signal(max=512)

        fsm.act(
            "IDLE",
            NextValue(data_counter, 0),
            converter.reset.eq(1),
        )

        fsm.act(
            "WAIT_TILL_DONE",
            sink.ready.eq(1),
            If(sink.valid & sink.last, NextState("IDLE")),
        )
        fsm.act(
            "COPY_TO_RAM",
            sink.connect(converter.sink),
            converter.source.connect(self.source, keep={"valid", "ready", "data"}),
            self.source.address.eq(sdram_offset + ram_offset + data_counter),
            If(
                converter.source.valid & converter.source.ready,
                NextValue(data_counter, data_counter + 1),
                If(converter.source.last, NextState("IDLE")),
            ),
        )


# State machine
# Three states:
# Idle
# - Reset counter to 0
# - If new packet received and metadata correct (header fields, universe), go to Copy to RAM
#   - ram_offset = universe * 170
#   - length = length
#   - data_counter = 0
# - If new packet received and metadata incorrect, go to Wait Until End
#   - ident false
#   - opcode false
#   - universe to high
#   - length > 510 (maybe also divisible by three? No, doable but a bit too complex)
# Wait Until End:
# - Read incoming data until last from packetizer, then jump to Idle
# Cppy to RAM
# - Directly connect depacketizer outupt to 32bitwordtocolor module
# - After last on input, wait until last from 32bitwordtocolor module & copy to ram is  done,
#   then go to idle
# - Count up for each color, adding it to offset in RAM and artnet universe * 170


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
            source.last_be.eq(sink.data[0:3]),
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
            source.last_be.eq(sink_d.last_be[8:]),
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

    def test_artnetreceiver():
        artnet_data = """
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
            00 00 00 00 00 00 00 00 00 00
        """
        proto_ver = 14
        sequence = 75
        universe = 12
        length = 510
        pass
