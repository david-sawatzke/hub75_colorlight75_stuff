#!/usr/bin/env python3
from migen import *


class GPIOStatic(Module):
    def __init__(self, out_freq, sys_clk_freq, outputs_specific, outputs_common):
        counter = Signal(max=int((sys_clk_freq / out_freq) / 2 - 1))
        collumn_counter = Signal(32)
        row_counter = Signal(4)
        fsm = FSM(reset_state="SHIFTING_DOWN")
        self.submodules.fsm = fsm
        fsm.act(
            "SHIFTING_UP",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            outputs_common.clk.eq(1),
            If(
                counter == 0,
                NextState("SHIFTING_DOWN"),
                # Set new data here, as it's sampled from L->H
                If(
                    collumn_counter < 32,
                    NextValue(outputs_specific.r0, ~outputs_specific.r0),
                ).Else(NextValue(outputs_specific.r0, 0)),
            ),
        )

        fsm.act(
            "SHIFTING_DOWN",
            outputs_common.oe.eq(0),
            outputs_common.lat.eq(1),
            outputs_common.clk.eq(0),
            If(
                counter == 0,
                NextValue(collumn_counter, collumn_counter + 1),
                If(
                    collumn_counter == 64,
                    NextValue(collumn_counter, 0),
                    NextState("DISABLE_OUTPUT"),
                ).Else(NextState("SHIFTING_UP")),
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
                NextState("SHIFTING_UP"),
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
