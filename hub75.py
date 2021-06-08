#!/usr/bin/env python3
# Protocol description https://fw.hardijzer.nl/?p=223
# Using binary code modulation (http://www.batsocks.co.uk/readme/art_bcm_1.htm)
from migen import If, Signal, Array, Memory, Module, FSM, NextValue, NextState, Mux
from migen.genlib.fifo import SyncFIFO
from litex.soc.interconnect.csr import AutoCSR, CSRStorage, CSRField
from litedram.frontend.dma import LiteDRAMDMAReader
import png


sdram_offset = 0x00400000//2//4
#              0x00200000


class Hub75(Module, AutoCSR):
    def __init__(self, pins_common, pins, sdram):
        # Registers
        self.ctrl = CSRStorage(1, fields=[CSRField("indexed", description="Display an indexed image")])

        read_port = sdram.crossbar.get_port(mode="read", data_width=32)

        self.submodules.common = FrameController(
            pins_common,
            # TODO Adjust later on
            brightness_psc=8,
        )
        self.submodules.specific = RowController(
            self.common, pins, read_port
        )
        self.palette_memory = self.specific.palette_memory


def _get_image_arrays():
    r = png.Reader(file=open("demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 64
    pixels = list(img[2])
    out_array = Array()
    for arr in pixels:
        # Assue rgb
        for i in range(64):
            red = arr[i * 3 + 0]
            green = arr[i * 3 + 1]
            blue = arr[i * 3 + 2]
            out_array.append(red | green << 8 | blue << 16)
    palette = [0]
    return (out_array, palette)


def _get_indexed_image_arrays():
    r = png.Reader(file=open("demo_img_indexed.png", "rb"))
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


class FrameController(Module):
    def __init__(
        self, outputs_common, brightness_psc=1,  brightness_bits=8
    ):
        self.start_shifting = start_shifting = Signal(1)
        self.shifting_done = shifting_done = Signal(1)
        self.brightness_bits = brightness_bits
        self.clk = outputs_common.clk
        counter_max = 8

        counter = Signal(max=counter_max)
        self.bit = brightness_bit = Signal(max=brightness_bits)
        brightness_counter = Signal(
            max=(1 << brightness_bits) * brightness_psc)
        row_active = Signal(4)
        self.row_select = row_shifting = Signal(4)
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
                # TODO Does this do anything useful?
                # Seems pretty free-running
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
        self.sync += [
            counter.eq(counter + 1),
            If(counter == counter_max - 1, counter.eq(0)),
            If(brightness_counter != 0, brightness_counter.eq(
                brightness_counter - 1)),
        ]

        self.comb += [
            outputs_common.oe.eq(brightness_counter == 0),
            outputs_common.row.eq(row_active),
        ]


class RowController(Module):
    def __init__(self, hub75_common, outputs_specific, read_port, collumns=64,):
        self.specials.palette_memory = palette_memory = Memory(
            width=32, depth=256, name="palette"
        )

        use_palette = Signal()
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
        self.submodules.buffer_reader = RamToBufferReader(
            mem_start, (hub75_common.row_select + 1) & 0xF, use_palette, read_port,
            row_writers[~shifting_buffer], palette_memory, collumns)

        row_start = Signal()
        self.submodules.row_module = hub75_common.row = RowModule(
            row_start, hub75_common.clk, collumns
        )

        data = Signal(32)
        self.submodules.specific = Output(
            hub75_common, outputs_specific, data)
        running = Signal()

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
                If((hub75_common.start_shifting & (hub75_common.bit == 7)),
                   mem_start.eq(True),
                   row_start.eq(True),
                   NextState("SHIFT_OUT"))
                .Elif((hub75_common.start_shifting & (hub75_common.bit != 7)),
                      row_start.eq(True),
                      NextState("SHIFT_OUT")
                      )
                )
        fsm.act("SHIFT_OUT",
                running.eq(True),
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

        self.sync += [
            use_palette.eq(True),
            ]


class RamToBufferReader(Module):
    def __init__(
            self,
            start: Signal(1),
            row: Signal(4),
            use_palette: Signal(1),
            mem_read_port,
            buffer_write_port,
            palette_memory,
            collumns: int = 64,
    ):
        self.done = Signal()
        running = Signal()
        self.comb += [
            # Eliminate the delay
            self.done.eq(~(start | running)),
        ]
        self.sync += [If(start, running.eq(True))]

        # RAM Reader
        self.submodules.reader = LiteDRAMDMAReader(mem_read_port)
        self.submodules.ram_adr = RamAddressGenerator(
            start, self.reader.sink.ready, row, collumns)

        ram_valid = self.reader.source.valid
        ram_data = self.reader.source.data
        ram_done = Signal()
        self.comb += [
            self.reader.sink.address.eq(self.ram_adr.adr),
            self.reader.sink.valid.eq(self.ram_adr.started),
            ram_done.eq((self.ram_adr.started == False)
                        & (self.reader.rsv_level == 0)
                        & (self.reader.source.valid == False))
        ]
        self.sync += [
            If(self.reader.source.valid,
                self.reader.source.ready.eq(True),
               )
            .Elif(
                (self.ram_adr.started == False)
                & (self.reader.rsv_level == 0),
                self.reader.source.ready.eq(False),
            )
            .Else(
                self.reader.source.ready.eq(True),
                buffer_write_port.we.eq(False),
            ),
        ]

        # Palette Lookup
        self.specials.palette_port = palette_port = palette_memory.get_port()

        palette_data_done = Signal()
        palette_data_valid = Signal()
        palette_data = Signal(24)
        palette_data_buffer = Signal(24)
        self.comb += [palette_data.eq(Mux(use_palette,
                                          palette_port.dat_r, palette_data_buffer)),
                      palette_port.adr.eq(ram_data & 0x000FF)
                      ]
        self.sync += [
            palette_data_buffer.eq(ram_data & 0x0FFFFFF),
            palette_data_valid.eq(ram_valid),
            If(ram_done & (~palette_data_done),
               palette_data_done.eq(True),
               ).Else(
                palette_data_done.eq(ram_done),
            )
        ]

        # Gamma Correction
        gamma_lut_r = _get_gamma_corr()
        gamma_lut_g = _get_gamma_corr()
        gamma_lut_b = _get_gamma_corr()
        gamma_data_done = Signal()
        gamma_data_valid = Signal()
        gamma_data = Signal(24)
        self.sync += [
            If(palette_data_valid,
               gamma_data.eq(
                   gamma_lut_r[palette_data & 0xFF]
                   | (gamma_lut_g[(palette_data >> 8) & 0xFF] << 8)
                   | (gamma_lut_b[(palette_data >> 16) & 0xFF] << 16)
               )
               ),
            gamma_data_valid.eq(palette_data_valid),
            If(palette_data_done & (~gamma_data_done),
               gamma_data_done.eq(True),
               ).Else(
                gamma_data_done.eq(palette_data_done),
            )
        ]

        # Buffer Writer
        buffer_done = Signal()
        self.sync += [
            If(gamma_data_valid,
               buffer_write_port.we.eq(True),
               buffer_write_port.dat_w.eq(gamma_data),
               buffer_write_port.adr.eq(buffer_write_port.adr + 1),
               )
            .Elif(gamma_data_done & (~buffer_done),
                  buffer_done.eq(True),
                  buffer_write_port.we.eq(False),
                  buffer_write_port.adr.eq(~0),
                  running.eq(False),)
            .Else(
                buffer_done.eq(gamma_data_done)
            )
        ]


class RamAddressGenerator(Module):
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
            If((self.counter == 0) & self.start & enable,
                self.counter.eq(1),
                self.start.eq(False))
            .Elif((self.counter == (collumns * 16 - 1)) & enable,
                  self.counter.eq(0))
            .Elif((self.counter > 0) & enable,
                  self.counter.eq(self.counter + 1)
                  ),
            If(
                enable == False)
            .Elif(
                self.counter_select < 4,
                self.adr.eq(
                    sdram_offset + (row + self.counter_select *
                                    16) * collumns + self.collumn
                ))
        ]


class RowModule(Module):
    def __init__(
        self,
        start: Signal(1),
        clk: Signal(1),
        collumns: int = 64,
    ):
        pipeline_delay = 2
        output_delay = 16
        delay = pipeline_delay + output_delay
        counter_max = collumns * 16 + delay
        self.counter = counter = Signal(max=counter_max)
        self.counter_select = counter_select = Signal(4)
        buffer_counter = Signal(max=counter_max)
        self.buffer_select = buffer_select = Signal(4)
        output_counter = Signal(max=collumns * 16)
        output_select = Signal(4)
        self.collumn = collumn = Signal(max=collumns)
        self.shifting_done = shifting_done = Signal(1)
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
            If(counter < counter_max - delay, collumn.eq(counter >> 4)).Else(
                collumn.eq(0),
            ),
        ]

        self.sync += [
            If((counter == 0) & start,
                counter.eq(1))
            .Elif((counter == (counter_max - 1)),
                  counter.eq(0))
            .Elif((counter > 0),
                  counter.eq(counter + 1)),
            shifting_done.eq(counter == (counter_max - 1))
        ]


class Output(Module):
    def __init__(self, hub75_common, outputs_specific, img_data):
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

        self.submodules.r_color = RowColorOutput(
            r_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            img_data,
            0,
        )
        self.submodules.g_color = RowColorOutput(
            g_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            img_data,
            8,
        )
        self.submodules.b_color = RowColorOutput(
            b_pins,
            hub75_common.bit,
            hub75_common.row.buffer_select,
            img_data,
            16,
        )


class RowColorOutput(Module):
    def __init__(
        self,
        outputs: Array(Signal(1)),
        bit: Signal(3),
        buffer_select: Signal(4),
        rgb_input: Signal(24),
        color_offset: int,
    ):
        while len(outputs) < 16:
            outputs.append(Signal())

        outputs_buffer = Array((Signal()) for x in range(16))
        bit_mask = Signal(24)
        self.sync += [
            outputs_buffer[buffer_select].eq(
                (rgb_input & bit_mask) != 0),
            # Leads to 1 cycle delay, but that's probably not an issue
            bit_mask.eq(1 << (color_offset + bit))
        ]

        self.sync += [If((buffer_select == 0), outputs[i].eq(outputs_buffer[i]))
                      for i in range(16)]
