#!/usr/bin/env python3
from migen import *

import png


def _get_image_array():
    r = png.Reader(file=open("demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 16
    pixels = list(img[2])
    out_array = Array()
    for arr in pixels:
        # Assue rgba
        row_arr = Array()
        for i in range(64):
            red = arr[i * 4 + 0]
            green = arr[i * 4 + 1]
            blue = arr[i * 4 + 2]
            row_arr.append((red, green, blue))
        out_array.append(row_arr)
    return out_array


def _get_indexed_image_arrays():
    r = png.Reader(file=open("demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 16
    pixels = list(img[2])
    out_array = Array()
    # Get image data
    for arr in pixels:
        row_arr = Array()
        for i in range(64):
            row_arr.append(arr[i])
        out_array.append(row_arr)
    # Get palette data
    # rgbrgbrgb
    r_palette = Array()
    g_palette = Array()
    b_palette = Array()
    # Probably rgb?
    png_palette = img[3]["palette"]
    for a in png_palette:
        r_palette.append(a[0])
        g_palette.append(a[1])
        b_palette.append(a[2])
    return (out_array, r_palette, g_palette, b_palette)


def _get_gamma_corr(bits_in=8, bits_out=8):
    gamma = 2.8
    max_in = (1 << bits_in) - 1
    max_out = (1 << bits_out) - 1
    gamma_lut = Array()
    for i in range(max_in + 1):
        gamma_lut.append(int(pow(i / max_in, gamma) * max_out + 0.5))
    return gamma_lut


class Common(Module):
    def __init__(
        self, outputs_common, collumns=64, brightness_bits=8
    ):
        self.collumns = collumns
        self.brightness_bits = brightness_bits
        counter_max = 8

        counter = Signal(max=counter_max)
        collumn_counter = Signal(max=collumns)
        self.collumn = collumn_counter
        brightness_bit = Signal(max=brightness_bits)
        self.bit = brightness_bit
        brightness_counter = Signal(max=(1 << brightness_bits))
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
                    NextState("WAIT"),
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
        fsm.act("WAIT", If(brightness_counter == 0, NextState("LATCH")))
        fsm.act(
            "LATCH",
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(brightness_counter, 1 << brightness_bit),
                If(
                    brightness_bit != 0,
                    NextValue(row_active, row_shifting),
                    NextValue(brightness_bit, brightness_bit - 1),
                ).Else(
                    NextValue(row_shifting, row_shifting + 1),
                    NextValue(brightness_bit, brightness_bits - 1),
                ),
                NextState("SHIFTING_SET_STATE"),
            ),
        )
        # synchronous assignments
        self.sync += [
            counter.eq(counter + 1),
            If(counter == counter_max - 1, counter.eq(0)),
            If(brightness_counter != 0, brightness_counter.eq(brightness_counter - 1)),
        ]

        # combinatorial assignements
        self.comb += [
            # Static outputs
            outputs_common.oe.eq(
                brightness_counter
                == 0
                # (collumn_counter < 8) | (collumn_counter > (collumns - 8))
            ),
            outputs_common.row.eq(row_active),
        ]


class Specific(Module):
    def __init__(self, hub75_common, outputs_specific):
        img = _get_indexed_image_arrays()
        r_palette = img[1]
        g_palette = img[2]
        b_palette = img[3]
        img = img[0]
        gamma_lut = _get_gamma_corr()
        # If it's not a seperate signal, there's breakage, somehow
        # TODO Find out why
        palette_index = Signal(8)
        bit = 1 << hub75_common.bit
        self.sync += [
            palette_index.eq(img[hub75_common.row][hub75_common.collumn]),
            outputs_specific.r0.eq((gamma_lut[r_palette[palette_index]] & bit) != 0),
            outputs_specific.g0.eq((gamma_lut[g_palette[palette_index]] & bit) != 0),
            outputs_specific.b0.eq((gamma_lut[b_palette[palette_index]] & bit) != 0),
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
    for i in range(((cols * 2 + 4) * 2) * 8):
        yield


def _test(pads, dut, cols):
    for i in range(16):
        yield from _test_row(pads, dut, i, cols)


class _TestModule(Module):
    def __init__(
        self, out_freq, sys_clk_freq, outputs_common, outputs_specific, collumns
    ):
        hub75_common = Common(out_freq, sys_clk_freq, outputs_common, collumns)
        hub75_specific = Specific(hub75_common, outputs_specific)
        self.submodules.common = hub75_common
        self.submodules.specific = hub75_specific


if __name__ == "__main__":
    pads = _TestPads()
    collumns = 64
    dut = _TestModule(1, 4, pads, pads, collumns)
    dut.clock_domains.cd_sys = ClockDomain("sys")
    run_simulation(dut, _test(pads, dut, collumns), vcd_name="output_test.vcd")
