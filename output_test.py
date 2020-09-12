#!/usr/bin/env python3
from migen import *


class GPIOStatic(Module):
    def __init__(
        self, out_freq, sys_clk_freq, outputs_specific, outputs_common, collumns=64
    ):
        counter = Signal(max=int((sys_clk_freq / out_freq) / 2))
        collumn_counter = Signal(max=collumns)
        row_counter = Signal(4)
        fsm = FSM(reset_state="SHIFTING_DOWN")
        self.submodules.fsm = fsm
        fsm.act(
            "SHIFTING_UP",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            outputs_common.clk.eq(1),
            If(counter == 0, NextState("SHIFTING_SET_STATE"),),
        )
        # Set new data here, as it's sampled from L->H
        fsm.act(
            "SHIFTING_SET_STATE",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            outputs_common.clk.eq(0),
            If(
                (collumn_counter > 1),
                If(
                    (row_counter & ((1 << collumn_counter - 2))),
                    NextValue(outputs_specific.r0, 1),
                ).Else(NextValue(outputs_specific.r0, 0)),
            ).Else(NextValue(outputs_specific.r0, 0)),
            NextValue(collumn_counter, collumn_counter + 1),
            If(
                collumn_counter == collumns - 1,
                NextValue(collumn_counter, 0),
                NextState("DISABLE_OUTPUT"),
            ).Else(NextState("SHIFTING_DOWN")),
        )
        fsm.act(
            "SHIFTING_DOWN",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            outputs_common.clk.eq(0),
            If(counter == 0, NextState("SHIFTING_UP"),),
        )

        fsm.act(
            "DISABLE_OUTPUT",
            outputs_common.oe.eq(1),
            outputs_common.lat.eq(1),
            If(counter == 0, NextState("BEGIN_LATCH")),
        )

        fsm.act(
            "BEGIN_LATCH",
            outputs_common.oe.eq(1),
            outputs_common.lat.eq(0),
            If(counter == 0, NextState("END_LATCH")),
        )
        fsm.act(
            "END_LATCH",
            outputs_common.oe.eq(1),
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(row_counter, row_counter + 1),
                NextState("SHIFTING_SET_STATE"),
            ),
        )

        # synchronous assignments
        self.sync += [
            counter.eq(counter + 1),
            If(counter == int((sys_clk_freq / out_freq) / 2 - 1), counter.eq(0)),
        ]

        # combinatorial assignements
        self.comb += [
            # Static outputs
            outputs_specific.g0.eq(0),
            outputs_specific.b0.eq(0),
            outputs_specific.r1.eq(0),
            outputs_specific.g1.eq(0),
            outputs_specific.b1.eq(0),
            outputs_common.row.eq(row_counter),
        ]


class _TestPads(Module):
    def __init__(self):
        self.r0 = Signal()
        self.g0 = Signal()
        self.b0 = Signal()
        self.r1 = Signal()
        self.g1 = Signal()
        self.b1 = Signal()
        self.clk = Signal()
        self.lat = Signal()
        self.oe = Signal()
        self.row = Signal(5)


def _test_row(pads, dut, row):
    for i in range((8 * 2 + 4) * 2):
        yield


def _test(pads, dut):
    for i in range(16):
        yield from _test_row(pads, dut, i)


if __name__ == "__main__":
    pads = _TestPads()
    dut = GPIOStatic(1, 4, pads, pads, 8)
    dut.clock_domains.cd_sys = ClockDomain("sys")
    run_simulation(dut, _test(pads, dut), vcd_name="output_text.vcd")
