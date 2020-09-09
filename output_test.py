#!/usr/bin/env python3
from migen import *


class GPIOStatic(Module):
    def __init__(self, out_freq, sys_clk_freq, outputs_specific, outputs_common):
        counter = Signal(32)
        collumn_counter = Signal(32)
        latching = Signal(2)
        collumn_counter = Signal(32)
        # synchronous assignments
        self.sync += [
            counter.eq(counter + 1),
            If(
                (latching == 0) & (counter == int((sys_clk_freq / out_freq) / 2 - 1)),
                counter.eq(0),
                outputs_common.clk.eq(~outputs_common.clk),
                collumn_counter.eq(collumn_counter + 1),
            ),
            If(
                collumn_counter == 128,
                counter.eq(0),
                collumn_counter.eq(0),
                outputs_common.oe.eq(1),
                latching.eq(1),
            ),
            If(
                (latching == 1) & (counter == int((sys_clk_freq / out_freq) - 1)),
                latching.eq(2),
                counter.eq(0),
                outputs_common.lat.eq(0),
            ),
            If(
                (latching == 2) & (counter == int((sys_clk_freq / out_freq) - 1)),
                latching.eq(3),
                counter.eq(0),
                outputs_common.lat.eq(1),
                outputs_common.row.eq(outputs_common.row + 1),
            ),
            If(
                (latching == 3) & (counter == int((sys_clk_freq / out_freq) - 1)),
                latching.eq(0),
                counter.eq(0),
                outputs_common.oe.eq(0),
            ),
        ]
        # combinatorial assignements
        self.comb += [
            # Static outputs
            outputs_specific.r0.eq(0),
            outputs_specific.g0.eq(0),
            outputs_specific.b0.eq(1),
            outputs_specific.r1.eq(1),
            outputs_specific.g1.eq(0),
            outputs_specific.b1.eq(0),
        ]
