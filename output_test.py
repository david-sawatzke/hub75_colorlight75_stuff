#!/usr/bin/env python3
from migen import *


class GPIOStatic(Module):
    def __init__(self, out_freq, sys_clk_freq, outputs_specific, outputs_common):
        counter = Signal(max=int((sys_clk_freq / out_freq) / 2 - 1))
        collumn_counter = Signal(32)
        row_counter = Signal(4)
        fsm = FSM(reset_state="SHIFTING")
        self.submodules.fsm = fsm
        fsm.act(
            "SHIFTING",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(outputs_common.clk, ~outputs_common.clk),
                NextValue(collumn_counter, collumn_counter + 1),
                If(
                    collumn_counter == 128,
                    NextValue(collumn_counter, 0),
                    NextState("DISABLE_OUTPUT"),
                ),
            ),
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
                NextValue(outputs_common.row, outputs_common.row + 1),
                NextValue(outputs_specific.r0, ~outputs_specific.r0),
                NextState("SHIFTING"),
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
            outputs_specific.b0.eq(1),
            outputs_specific.r1.eq(1),
            outputs_specific.g1.eq(0),
            outputs_specific.b1.eq(0),
        ]
