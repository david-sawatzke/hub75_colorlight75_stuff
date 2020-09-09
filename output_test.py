#!/usr/bin/env python3
from migen import *
from litex.soc.cores.uart import *

import math


class GPIOStatic(Module):
    def __init__(self, blink_freq, sys_clk_freq, led):
        counter = Signal(32)
        # synchronous assignments
        self.sync += [
            counter.eq(counter + 1),
            If(
                counter == int((sys_clk_freq / blink_freq) / 2 - 1),
                counter.eq(0),
                led.eq(~led),
            ),
        ]
        # combinatorial assignements
        self.comb += []
