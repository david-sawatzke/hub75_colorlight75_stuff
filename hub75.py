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
            self, outputs_common, brightness_psc = 1, collumns=64, brightness_bits=8
    ):
        self.collumns = collumns
        start_shifting = Signal(1)
        row_module = RowModule(start_shifting, outputs_common.clk, collumns)
        self.submodules.row_module = row_module
        self.brightness_bits = brightness_bits
        counter_max = 8

        counter = Signal(max=counter_max)
        self.collumn = row_module.collumn
        brightness_bit = Signal(max=brightness_bits)
        self.bit = brightness_bit
        brightness_counter = Signal(max=(1 << brightness_bits) * brightness_psc)
        row_active = Signal(4)
        row_shifting = Signal(4)
        self.row = row_shifting
        output_data = Signal()
        fsm = FSM(reset_state="WAIT")
        self.submodules.fsm = fsm
        fsm.act("WAIT", outputs_common.lat.eq(0),
                start_shifting.eq(0),
                If(((brightness_counter == 0) & row_module.shifting_done), NextState("LATCH")))
        fsm.act(
            "LATCH",
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(brightness_counter, (1 << brightness_bit) * brightness_psc),
                start_shifting.eq(1),
                If(
                    brightness_bit != 0,
                    NextValue(row_active, row_shifting),
                    NextValue(brightness_bit, brightness_bit - 1),
                ).Else(
                    NextValue(row_shifting, row_shifting + 1),
                    NextValue(brightness_bit, brightness_bits - 1),
                ),
                NextState("WAIT"),
            ).Else(
                start_shifting.eq(0),
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
            ),
            outputs_common.row.eq(row_active),
        ]

class RowModule(Module):
    def __init__(
        self,
        start_shifting: Signal(1),
        clk: Signal(1),
        collumns: int = 64,
    ):
        delay = 4
        counter_max = collumns * 16
        counter = Signal(max=counter_max)
        output_counter = Signal(max=collumns * 16)
        output_select = Signal(4)
        output_collumn = Signal(max=collumns)
        collumn = Signal(max=collumns)
        shifting_done = Signal(1)
        self.collumn = collumn
        self.shifting_done = shifting_done
        self.comb += [
            If(counter < delay, output_counter.eq(0)).Else(output_counter.eq(counter - delay)),
            If(output_select < 8, clk.eq(0)).Else(clk.eq(1)),
            output_select.eq(output_counter & 0xF),
            output_collumn.eq(output_counter >> 4),
            If(counter < counter_max - delay,
                collumn.eq(counter >> 4),
            ).Else(
                collumn.eq(0),
                ),
        ]

        self.sync += [
            If(counter != (counter_max - 1), counter.eq(counter + 1)),
            If(
                (counter == (counter_max - 1)) & (start_shifting == 1),
                counter.eq(0),

            ),
            If(counter == (counter_max - 1), shifting_done.eq(1)).Else(
                shifting_done.eq(0)
            ),

        ]



class Specific(Module):
    def __init__(self, hub75_common, outputs_specific):
        img = _get_indexed_image_arrays()
        r_palette = img[1]
        g_palette = img[2]
        b_palette = img[3]
        img = img[0]
        # If it's not a seperate signal, there's breakage, somehow
        # TODO Find out why
        palette_index = Signal(8)
        r_value = Signal(8)
        g_value = Signal(8)
        b_value = Signal(8)
        self.submodules.r_gamma = r_gamma = GammaCorrection(r_value, 8, hub75_common.bit)
        self.submodules.g_gamma = g_gamma = GammaCorrection(g_value, 8, hub75_common.bit)
        self.submodules.b_gamma = b_gamma = GammaCorrection(b_value, 8, hub75_common.bit)

        self.sync += [
            palette_index.eq(img[hub75_common.row][hub75_common.collumn]),
            r_value.eq(r_palette[palette_index]),
            g_value.eq(g_palette[palette_index]),
            b_value.eq(b_palette[palette_index]),
            outputs_specific.r0.eq(r_gamma.out_bit),
            outputs_specific.g0.eq(g_gamma.out_bit),
            outputs_specific.b0.eq(b_gamma.out_bit),
        ]
#
# 1 cycle delay
class GammaCorrection(Module):
    def __init__(self, value, brightness_bits, bit):
        self.out_bit = Signal()
        gamma_lut = _get_gamma_corr(bits_out=brightness_bits)
        bit_mask = 1 << bit
        self.sync += [self.out_bit.eq((gamma_lut[value] & bit_mask) != 0)]

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
        hub75_common = Common(outputs_common, collumns)
        hub75_specific = Specific(hub75_common, outputs_specific)
        self.submodules.common = hub75_common
        self.submodules.specific = hub75_specific


if __name__ == "__main__":
    pads = _TestPads()
    collumns = 64
    dut = _TestModule(1, 4, pads, pads, collumns)
    dut.clock_domains.cd_sys = ClockDomain("sys")
    run_simulation(dut, _test(pads, dut, collumns), vcd_name="output_test.vcd")
