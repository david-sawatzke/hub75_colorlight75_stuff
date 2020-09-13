#!/usr/bin/env python3
from migen import *

import png


def _get_image_array():
    r = png.Reader(file=open("demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 16
    threshhold = (1 << img[3]["bitdepth"]) // 2
    pixels = list(img[2])
    out_array = Array()
    for arr in pixels:
        # Assue rgba
        row_arr = Array()
        for i in range(64):
            red = bool(arr[i * 4 + 0] // threshhold)
            green = bool(arr[i * 4 + 1] // threshhold)
            blue = bool(arr[i * 4 + 2] // threshhold)
            row_arr.append((red, green, blue))
        out_array.append(row_arr)
    return out_array


class Common(Module):
    def __init__(self, out_freq, sys_clk_freq, outputs_common, collumns=64):
        counter = Signal(max=int((sys_clk_freq / out_freq) / 2))
        collumn_counter = Signal(max=collumns)
        self.collumn = collumn_counter
        row_active = Signal(4)
        row_shifting = Signal(4)
        self.row = row_shifting
        output_data = Signal()
        fsm = FSM(reset_state="SHIFTING_SET_STATE")
        self.submodules.fsm = fsm
        fsm.act(
            "SHIFTING_UP",
            outputs_common.lat.eq(0),
            outputs_common.clk.eq(1),
            If(
                counter == 0,
                If(
                    collumn_counter == collumns - 1,
                    NextValue(collumn_counter, 0),
                    NextState("LATCH"),
                ).Else(
                    NextValue(collumn_counter, collumn_counter + 1),
                    NextState("SHIFTING_SET_STATE"),
                ),
            ),
        )
        # Set new data here, as it's sampled from L->H
        fsm.act(
            "SHIFTING_SET_STATE",
            outputs_common.lat.eq(0),
            outputs_common.clk.eq(0),
            output_data.eq(1),
            NextState("SHIFTING_DOWN"),
        )
        fsm.act(
            "SHIFTING_DOWN",
            outputs_common.lat.eq(0),
            outputs_common.clk.eq(0),
            If(counter == 0, NextState("SHIFTING_UP"),),
        )
        fsm.act(
            "LATCH",
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(row_active, row_active + 1),
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
            outputs_common.oe.eq(
                (collumn_counter < 8) | (collumn_counter > (collumns - 8))
            ),
            outputs_common.row.eq(row_active),
            row_shifting.eq(row_active + 1),
        ]


class Specific(Module):
    def __init__(self, hub75_common, outputs_specific, collumns=64):
        img = _get_image_array()
        self.sync += [
            outputs_specific.r0.eq(img[hub75_common.row][hub75_common.collumn][0]),
            outputs_specific.g0.eq(img[hub75_common.row][hub75_common.collumn][1]),
            outputs_specific.b0.eq(img[hub75_common.row][hub75_common.collumn][2]),
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


def _test_row(pads, dut, row, cols):
    for i in range((cols * 2 + 4) * 2):
        yield


def _test(pads, dut, cols):
    for i in range(16):
        yield from _test_row(pads, dut, i, cols)


class _TestModule(Module):
    def __init__(
        self, out_freq, sys_clk_freq, outputs_common, outputs_specific, collumns
    ):
        hub75_common = Common(out_freq, sys_clk_freq, outputs_common, collumns)
        hub75_specific = Specific(hub75_common, outputs_specific, collumns)
        self.submodules.common = hub75_common
        self.submodules.specific = hub75_specific


if __name__ == "__main__":
    pads = _TestPads()
    collumns = 64
    dut = _TestModule(1, 4, pads, pads, collumns)
    dut.clock_domains.cd_sys = ClockDomain("sys")
    run_simulation(dut, _test(pads, dut, collumns), vcd_name="output_test.vcd")
