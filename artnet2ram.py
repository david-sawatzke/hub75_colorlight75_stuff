import unittest
import random
from litex.soc.interconnect import stream
from migen import *

# PHY
def artnet_stream_description():
    payload_layout = [
        ("data", 32),
        ("last_be", 4),
    ]
    return stream.EndpointDescription(payload_layout)


# class ArtnetDepacketizer(Module):
#     foo

# class ArtnetReceiver(Module):
# State machine
# Three states:
# Idle
# - Reset counter to 0
# - If new packet received and metadata correct (header fields, universe), go to Copy to RAM
# - If new packet received and metadata incorrect, go to Wait Until End
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
    def pipe_test(self, dut):
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

    def test_pipe_valid(self):
        dut = RawDataStreamToColorStream()
        self.pipe_test(dut)
