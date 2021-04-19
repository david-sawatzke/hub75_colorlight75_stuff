#!/usr/bin/env python3
# Protocol description https://fw.hardijzer.nl/?p=223
# Using binary code modulation (http://www.batsocks.co.uk/readme/art_bcm_1.htm)
from migen import *
from migen.genlib.fifo import SyncFIFO
from litedram.frontend.dma import LiteDRAMDMAWriter, LiteDRAMDMAReader
import png


sdram_offset = 0x00400000//2//4


def _get_image_array():
    r = png.Reader(file=open("demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 64
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
    assert img[1] == 64
    pixels = list(img[2])
    out_array = Array()
    # Get image data
    for arr in pixels:
        for i in range(64):
            out_array.append(arr[i])
    # Get palette data
    # rgbrgbrgb
    palette = []
    # Probably rgb?
    png_palette = img[3]["palette"]
    for a in png_palette:
        palette.append(a[0] | a[1] << 8 | a[2] << 16)
    return (out_array, palette)


# Taken from https://learn.adafruit.com/led-tricks-gamma-correction/the-longer-fix
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
        self, outputs_common, brightness_psc=1,  brightness_bits=8
    ):
        self.start_shifting = start_shifting = Signal(1)
        self.shifting_done = shifting_done = Signal(1)
        self.brightness_bits = brightness_bits
        self.clk = outputs_common.clk
        counter_max = 8

        counter = Signal(max=counter_max)
        brightness_bit = Signal(max=brightness_bits)
        self.bit = brightness_bit
        brightness_counter = Signal(
            max=(1 << brightness_bits) * brightness_psc)
        row_active = Signal(4)
        row_shifting = Signal(4)
        self.row_select = row_shifting
        output_data = Signal()
        fsm = FSM(reset_state="RST")
        self.submodules.fsm = fsm
        fsm.act(
            "RST",
            outputs_common.lat.eq(0),
            start_shifting.eq(1),
            NextState("WAIT"),
        )
        fsm.act(
            "WAIT",
            outputs_common.lat.eq(0),
            start_shifting.eq(0),
            If(
                ((brightness_counter == 0) & shifting_done),
                NextState("LATCH"),
            ),
        )
        fsm.act(
            "LATCH",
            outputs_common.lat.eq(1),
            If(
                counter == 0,
                NextValue(brightness_counter,
                          (1 << brightness_bit) * brightness_psc),
                start_shifting.eq(1),
                If(
                    brightness_bit != 0,
                    NextValue(row_active, row_shifting),
                    NextValue(brightness_bit, brightness_bit - 1),)
                .Else(
                    NextValue(row_shifting, row_shifting + 1),
                    NextValue(brightness_bit, brightness_bits - 1),
                ),
                NextState("WAIT"),)
            .Else(
                start_shifting.eq(0),
            ),
        )
        # synchronous assignments
        self.sync += [
            counter.eq(counter + 1),
            If(counter == counter_max - 1, counter.eq(0)),
            If(brightness_counter != 0, brightness_counter.eq(
                brightness_counter - 1)),
        ]

        # combinatorial assignements
        self.comb += [
            # Static outputs
            outputs_common.oe.eq(brightness_counter == 0),
            outputs_common.row.eq(row_active),
        ]


class SpecificMemoryStuff(Module):
    def __init__(self, hub75_common, outputs_specific, write_port, read_port, collumns=64,):
        img = _get_indexed_image_arrays()
        self.submodules.ram_initializer = RamInitializer(write_port, img)
        self.specials.palette_memory = palette_memory = Memory(
            width=32, depth=len(img[1]), init=img[1], name="palette"
        )
        row_buffers = Array()
        row_readers = Array()
        row_writers = Array()
        for _ in range(2):
            row_buffer = Memory(
                # width=32, depth=512,
                width=32, depth=collumns * 16,
            )
            row_writer = row_buffer.get_port(write_capable=True)
            row_reader = row_buffer.get_port()
            row_buffers.append(row_buffer)
            row_readers.append(row_reader)
            row_writers.append(row_writer)
            self.specials += [row_buffer, row_reader, row_writer]

        shifting_buffer = Signal()
        mem_start = Signal()
        self.submodules.buffer_reader = RamBufferReaderModule(
            mem_start, (hub75_common.row_select + 1) & 0xF, read_port, row_writers[~shifting_buffer], collumns)

        row_start = Signal()
        row_enable = Signal()
        self.submodules.row_module = hub75_common.row = row_module = RowModule(
            row_start, row_enable, hub75_common.clk, collumns
        )

        data = Signal(32)
        self.submodules.specific = Specific(
            hub75_common, outputs_specific, data, palette_memory)
        running = Signal()

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
                If((hub75_common.start_shifting & (hub75_common.bit == 7)) == True,
                   mem_start.eq(True),
                   row_start.eq(True),
                   row_enable.eq(True),
                   NextState("SHIFT_OUT"))
                .Elif((hub75_common.start_shifting & (hub75_common.bit != 7)) == True,
                      row_start.eq(True),
                      row_enable.eq(True),
                      NextState("SHIFT_OUT")
                      )
                )
        fsm.act("SHIFT_OUT",
                running.eq(True),
                row_enable.eq(True),
                row_readers[shifting_buffer].adr.eq(
                    self.row_module.counter),
                data.eq(row_readers[shifting_buffer].dat_r),
                If((hub75_common.bit == 0) & self.row_module.shifting_done & self.buffer_reader.done,
                   NextValue(shifting_buffer, ~shifting_buffer),
                   NextState("IDLE")),
                If((hub75_common.bit != 0) & self.row_module.shifting_done,
                   NextState("IDLE"))
                )
        self.comb += [
            # Eliminate the delay
            hub75_common.shifting_done.eq(
                ~(running | hub75_common.start_shifting)),
        ]

        self.sync += []


class RamBufferReaderModule(Module):
    def __init__(
            self,
            start: Signal(1),
            row: Signal(4),
            mem_read_port,
            buffer_write_port,
            collumns: int = 64,
    ):
        self.done = Signal()
        running = Signal()
        self.submodules.reader = LiteDRAMDMAReader(mem_read_port)
        self.submodules.ram_adr = RamAddressModule(
            start, self.reader.sink.ready, row, collumns)
        self.comb += [
            # Eliminate the delay
            self.done.eq(
                ~(start | running)),
            self.reader.sink.address.eq(self.ram_adr.adr),
            self.reader.sink.valid.eq(self.ram_adr.started),
        ]

        self.sync += [
            If(self.reader.source.valid == True,
                self.reader.source.ready.eq(True),
                buffer_write_port.dat_w.eq(self.reader.source.data),
                buffer_write_port.we.eq(True),
                buffer_write_port.adr.eq(buffer_write_port.adr + 1),)
            .Elif(
                (self.ram_adr.started == False)
                & (self.reader.rsv_level == 0),
                self.reader.source.ready.eq(False),
                buffer_write_port.we.eq(False),
                buffer_write_port.adr.eq(~0),
                running.eq(False),)
            .Else(
                self.reader.source.ready.eq(True),
                buffer_write_port.we.eq(False),
            ),
            If(start,
               running.eq(True)
               )
        ]


class RamAddressModule(Module):
    def __init__(
        self,
        start: Signal(1),
        enable: Signal(1),
        row: Signal(4),
        collumns: int = 64,
    ):
        self.counter = Signal(max=collumns * 16)
        self.counter_select = Signal(max=16)
        self.collumn = Signal(max=collumns)
        self.adr = Signal(32)
        self.started = Signal(1)
        self.start = Signal(1)
        self.comb += [
            self.counter_select.eq(self.counter & 0xF),
            self.collumn.eq(self.counter >> 4),
            self.started.eq(self.start | (self.counter != 0))
        ]

        self.sync += [
            If(start,
                self.start.eq(True),
               ),
            If((self.counter == 0) & (self.start == True) & (enable == True),
                self.counter.eq(1),
                self.start.eq(False),)
            .Elif((self.counter == (collumns * 16 - 1)) & (enable == True),
                  self.counter.eq(0))
            .Elif((self.counter > 0) & (enable == True),
                  self.counter.eq(self.counter + 1)
                  ),
            If(
                enable == False)
            .Elif(
                self.counter_select < 4,
                self.adr.eq(
                    sdram_offset + (row + self.counter_select *
                                    16) * collumns + self.collumn
                ),)
        ]


class RowModule(Module):
    def __init__(
        self,
        start: Signal(1),
        enable: Signal(1),
        clk: Signal(1),
        collumns: int = 64,
    ):
        pipeline_delay = 5
        output_delay = 16
        delay = pipeline_delay + output_delay
        counter_max = collumns * 16 + delay
        self.counter = counter = Signal(max=counter_max)
        counter_select = Signal(4)
        buffer_counter = Signal(max=counter_max)
        buffer_select = Signal(4)
        output_counter = Signal(max=collumns * 16)
        output_select = Signal(4)
        output_collumn = Signal(max=collumns)
        collumn = Signal(max=collumns)
        shifting_done = Signal(1)
        self.collumn = collumn
        self.shifting_done = shifting_done
        self.buffer_select = buffer_select
        self.counter_select = counter_select
        self.test = Signal()
        self.comb += [
            If(counter < delay, output_counter.eq(0)).Else(
                output_counter.eq(counter - delay)
            ),
            If(counter < pipeline_delay, buffer_counter.eq(0)).Else(
                buffer_counter.eq(counter - pipeline_delay)
            ),
            If(output_select < 8, clk.eq(0)).Else(clk.eq(1)),
            output_select.eq(output_counter & 0xF),
            buffer_select.eq(buffer_counter & 0xF),
            counter_select.eq(counter & 0xF),
            output_collumn.eq(output_counter >> 4),
            If(counter < counter_max - delay, collumn.eq(counter >> 4)).Else(
                collumn.eq(0),
            ),
        ]

        self.sync += [
            If((counter == 0) & (start == True) & (enable == True),
                counter.eq(1),)
            .Elif((counter == (counter_max - 1)) & enable,
                  counter.eq(0),)
            .Elif(enable & (counter > 0), counter.eq(counter + 1)
                  ),
            If(counter == (counter_max - 1),
               shifting_done.eq(1))
            .Else(
                shifting_done.eq(0)
            ),
        ]


# Should be replaced with cpu code in the future
class RamInitializer(Module):
    def __init__(self, write_port, img):
        img_data = Array(img[0])
        img_counter = Signal(max=len(img_data) + 1)
        self.submodules.writer = writer = LiteDRAMDMAWriter(write_port)
        # FIXME: Final adress might not be written properly
        self.sync += [
            If(
                img_counter != len(img_data),
                writer.sink.valid.eq(True),
                If((writer.sink.ready == True) | (img_counter == 0),
                    img_counter.eq(img_counter + 1),
                    writer.sink.address.eq(sdram_offset + img_counter),
                    writer.sink.data.eq(img_data[img_counter]),  # << 24 | 0),
                   ),)
            .Else(writer.sink.valid.eq(False)),
        ]


class Specific(Module):
    def __init__(self, hub75_common, outputs_specific, img_data, palette_memory):
        rgb_color = Signal(24)
        self.specials.palette_port = palette_port = palette_memory.get_port(
            has_re=True)
        r_pins = Array()
        g_pins = Array()
        b_pins = Array()
        for output in outputs_specific:
            r_pins.append(output.r0)
            r_pins.append(output.r1)
            g_pins.append(output.g0)
            g_pins.append(output.g1)
            b_pins.append(output.b0)
            b_pins.append(output.b1)

        self.submodules.r_color = RowColorModule(
            r_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            rgb_color,
            0,
            8,
        )
        self.submodules.g_color = RowColorModule(
            g_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            rgb_color,
            8,
            8,
        )
        self.submodules.b_color = RowColorModule(
            b_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            rgb_color,
            16,
            8,
        )

        self.comb += [
            palette_port.re.eq(True),
            rgb_color.eq(palette_port.dat_r),
        ]

        self.sync += [
            palette_port.adr.eq(img_data),
        ]


class RowColorModule(Module):
    def __init__(
        self,
        outputs: Array(Signal(1)),
        bit: Signal(3),
        buffer_select: Signal(4),
        rgb_input: Signal(24),
        color_offset: int,
        out_bits: int = 8,
    ):
        while len(outputs) < 16:
            outputs.append(Signal())

        outputs_buffer = Array((Signal()) for x in range(16))

        self.submodules.gamma = gamma = GammaCorrection(
            (rgb_input >> color_offset) & 0xFF, out_bits, bit
        )

        self.sync += [
            outputs_buffer[buffer_select].eq(gamma.out_bit),
        ]

        self.sync += [If((buffer_select == 0), outputs[i].eq(outputs_buffer[i]))
                      for i in range(16)]

#
# 1 cycle delay


class GammaCorrection(Module):
    def __init__(self, value, out_bits, bit):
        self.out_bit = Signal()
        gamma_lut = _get_gamma_corr(bits_out=out_bits)
        bit_mask = 1 << bit
        self.sync += [
            self.out_bit.eq((gamma_lut[value] & bit_mask) != 0)
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


def _test():
    for i in range(16 * 64 * 8 * 16):
        yield


class _TestModule(Module):
    def __init__(
        self, out_freq, sys_clk_freq, outputs_common, outputs_specific, collumns
    ):
        self.read_port = LiteDRAMNativeReadPort(
            address_width=32, data_width=32)
        self.write_port = LiteDRAMNativeWritePort(
            address_width=32, data_width=32)
        hub75_common = Common(outputs_common, brightness_psc=15)
        hub75_specific = SpecificMemoryStuff(hub75_common, [
            outputs_specific], self.write_port, self.read_port, collumns=collumns)
        self.submodules.common = hub75_common
        self.submodules.specific = hub75_specific


if __name__ == "__main__":
    pads = _TestPads()
    collumns = 64
    dut = _TestModule(1, 4, pads, pads, collumns)
    dut.clock_domains.cd_sys = ClockDomain("sys")
    # work around
    run_simulation(dut, _test(pads, dut, collumns), vcd_name="output_test.vcd")
