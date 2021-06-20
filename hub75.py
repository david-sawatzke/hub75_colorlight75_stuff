#!/usr/bin/env python3
# Protocol description https://fw.hardijzer.nl/?p=223
# Using binary code modulation (http://www.batsocks.co.uk/readme/art_bcm_1.htm)
from types import SimpleNamespace

from migen import If, Signal, Array, Memory, Module, FSM, NextValue, NextState, Mux, Cat
from litex.soc.interconnect.csr import AutoCSR, CSRStorage, CSRField
from litedram.frontend.dma import LiteDRAMDMAReader

sdram_offset = 0x00400000//2//4
#              0x00200000


class Hub75(Module, AutoCSR):
    def __init__(self, pins_common, pins, sdram):
        # Registers
        self.ctrl = CSRStorage(fields=[
            CSRField("indexed", description="Display an indexed image"),
            CSRField("enabled", description="Enable the output"),
            CSRField("width", description="Width of the image", size=16),
        ])
        panel_config = Array()
        for i in range(8):
            csr = CSRStorage(name="panel" + str(i), fields=[
                # CSRField("vert", description="Module is vertical if enabled"),
                CSRField("x", description="x position in multiples of 32", size=8),
                CSRField("y", description="y position in multiples of 32", size=8),
            ])
            setattr(self, "panel" + str(i), csr)
            panel_config.append(csr)

        read_port = sdram.crossbar.get_port(mode="read", data_width=32)
        output_config = SimpleNamespace(
            indexed=self.ctrl.fields.indexed, width=self.ctrl.fields.width
        )
        self.submodules.common = FrameController(
            pins_common,
            self.ctrl.fields.enabled,
            # TODO Adjust later on
            brightness_psc=8,
        )
        self.submodules.specific = RowController(
            self.common, pins, output_config, panel_config, read_port
        )
        self.palette_memory = self.specific.palette_memory


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
            self, outputs_common, enable: Signal(1), brightness_psc=1,  brightness_bits=8
    ):
        self.start_shifting = start_shifting = Signal(1)
        self.shifting_done = shifting_done = Signal(1)
        self.brightness_bits = brightness_bits
        self.clk = outputs_common.clk
        counter_max = 8

        counter = Signal(max=counter_max)
        self.output_bit = brightness_bit = Signal(max=brightness_bits)
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
                ((brightness_counter == 0) & shifting_done & enable),
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
    def __init__(self, hub75_common, outputs_specific, output_config,
                 panel_config, read_port, collumns_2=6):
        self.specials.palette_memory = palette_memory = Memory(
            width=32, depth=256, name="palette"
        )

        row_buffers = Array()
        row_readers = Array()
        row_writers = Array()
        for _ in range(2):
            row_buffers_outputs = []
            row_readers_outputs = []
            row_writers_outputs = Array()
            # TODO Change this later on, if the memory is needed
            # A quarter is not needed and (somewhat) easily used
            for _ in range(8):
                row_buffer = Memory(
                    width=32, depth=1 << (collumns_2 + 1),
                )
                row_writer = row_buffer.get_port(write_capable=True)
                row_reader = row_buffer.get_port()
                row_buffers_outputs.append(row_buffer)
                row_readers_outputs.append(row_reader)
                row_writers_outputs.append(row_writer)
                self.specials += [row_buffer, row_reader, row_writer]
            row_buffers.append(row_buffers_outputs)
            row_readers.append(row_readers_outputs)
            row_writers.append(row_writers_outputs)

        shifting_buffer = Signal()
        mem_start = Signal()
        self.submodules.buffer_reader = RamToBufferReader(
            mem_start, (hub75_common.row_select + 1) & 0xF,
            output_config.indexed, output_config.width, panel_config,
            read_port, row_writers[~shifting_buffer], palette_memory,
            collumns_2)

        row_start = Signal()
        self.submodules.row_module = hub75_common.row = RowModule(
            row_start, hub75_common.clk, collumns_2
        )

        self.submodules.specific = Output(hub75_common, outputs_specific,
                        row_readers[shifting_buffer], self.row_module.counter)
        running = Signal()

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
                If((hub75_common.start_shifting & (hub75_common.output_bit == 7)),
                   mem_start.eq(True),
                   row_start.eq(True),
                   NextState("SHIFT_OUT"))
                .Elif((hub75_common.start_shifting & (hub75_common.output_bit != 7)),
                      row_start.eq(True),
                      NextState("SHIFT_OUT")
                      )
                )
        fsm.act("SHIFT_OUT",
                running.eq(True),
                If((hub75_common.output_bit == 0) & self.row_module.shifting_done
                   & self.buffer_reader.done,
                   NextValue(shifting_buffer, ~shifting_buffer),
                   NextState("IDLE")),
                If((hub75_common.output_bit != 0) & self.row_module.shifting_done,
                   NextState("IDLE"))
                )
        self.comb += [
            # Eliminate the delay
            hub75_common.shifting_done.eq(
                ~(running | hub75_common.start_shifting)),
        ]

        self.sync += []


class RamToBufferReader(Module):
    def __init__(
            self,
            start: Signal(1),
            row: Signal(4),
            use_palette: Signal(1),
            image_width: Signal(16),
            panel_config,
            mem_read_port,
            buffer_write_port,
            palette_memory,
            collumns_2,
            strip_length_2=0,
    ):
        self.done = Signal()
        done = Signal()
        # Eliminate the delay
        self.comb += self.done.eq(~start & done)
        self.sync += If(start, done.eq(False))

        # RAM Reader
        self.submodules.reader = LiteDRAMDMAReader(mem_read_port)
        self.submodules.ram_adr = RamAddressGenerator(
            start, self.reader.sink.ready, row, image_width, panel_config,
            collumns_2, strip_length_2)

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
            palette_data_done.eq(ram_done),
        ]

        # Gamma Correction
        gamma_lut = _get_gamma_corr()
        gamma_data_done = Signal()
        gamma_data_valid = Signal()
        gamma_data = Signal(24)
        self.sync += [
            gamma_data.eq(Cat(gamma_lut[palette_data[:8]],
                              gamma_lut[palette_data[8:16]],
                              gamma_lut[palette_data[16:24]])),
            gamma_data_valid.eq(palette_data_valid),
            gamma_data_done.eq(palette_data_done),
        ]

        # Buffer Writer
        buffer_done = Signal()
        buffer_counter = Signal(collumns_2 + 1 + 3)
        buffer_select = Signal(3)
        buffer_address = Signal(collumns_2 + 1)

        for i in range(8):
            self.sync += [
                If(gamma_data_valid,
                    buffer_write_port[i].dat_w.eq(gamma_data),
                    buffer_write_port[i].adr.eq(buffer_address),
                )
            ]
        self.comb += [
            buffer_select.eq(buffer_counter[collumns_2 + 1 + strip_length_2:]),
            buffer_address.eq(
                Cat(buffer_counter[collumns_2],
                    buffer_counter[:collumns_2],
                    buffer_counter[collumns_2 + 1:collumns_2 + 1 + strip_length_2])
            ), ]
        # TODO Check if data & adress match
        self.sync += [
            If(gamma_data_valid,
                buffer_write_port[buffer_select - 1].we.eq(False),
                buffer_write_port[buffer_select].we.eq(True),
               buffer_counter.eq(buffer_counter + 1),)
            .Elif(gamma_data_done & (~buffer_done),
                  buffer_write_port[buffer_select - 1].we.eq(False),
                  buffer_counter.eq(0),
                  done.eq(True)),
            buffer_done.eq(gamma_data_done)
        ]


class RamAddressGenerator(Module):
    def __init__(
        self,
        start: Signal(1),
        enable: Signal(1),
        row: Signal(4),
        image_width: Signal(16),
        panel_config,
        collumns_2,
        strip_length_2,
    ):
        outputs_2 = 3
        counter = Signal(collumns_2 + 1 + strip_length_2 + outputs_2)
        counter_select = Signal(strip_length_2 + outputs_2)
        collumn = counter[:collumns_2]
        half_select = counter[collumns_2]
        self.adr = Signal(32)
        self.started = Signal(1)
        self.comb += [
            counter_select.eq(counter[(collumns_2 + 1):]),
        ]

        self.sync += [
            If((counter == 0) & start,
                self.started.eq(True),
                counter.eq(1))
            .Elif((counter == (
                (1 << (collumns_2 + 1 + strip_length_2 + outputs_2)) - 1))
                  & enable,
                  self.started.eq(False),
                  counter.eq(0))
            .Elif(self.started & enable,
                  counter.eq(counter + 1)
                  ),
            If(enable | start,
                self.adr.eq(
                    sdram_offset
                    + (row + half_select * 16 +
                        panel_config[counter_select].fields.y * 32)
                    * image_width + collumn
                    + panel_config[counter_select].fields.x * 32
                ))
        ]


class RowModule(Module):
    def __init__(
        self,
        start: Signal(1),
        clk: Signal(1),
        collumns_2: int = 6,
    ):
        pipeline_delay = 1
        output_delay = 2
        delay = pipeline_delay + output_delay
        counter_max = (1 << (collumns_2 + 1)) + delay
        self.counter = counter = Signal(max=counter_max)
        self.counter_select = counter_select = Signal(1)
        buffer_counter = Signal(max=counter_max)
        self.buffer_select = buffer_select = Signal(1)
        output_counter = Signal(collumns_2 + 1)
        output_select = Signal(1)
        self.collumn = collumn = Signal(collumns_2)
        self.shifting_done = shifting_done = Signal(1)
        self.comb += [
            If(counter < delay, output_counter.eq(0)).Else(
                output_counter.eq(counter - delay)
            ),
            If(counter < pipeline_delay, buffer_counter.eq(0)).Else(
                buffer_counter.eq(counter - pipeline_delay)
            ),
            output_select.eq(output_counter & 0x1),
            buffer_select.eq(buffer_counter & 0x1),
            counter_select.eq(counter & 0x1),
            If(counter < counter_max - delay, collumn.eq(counter >> 1)).Else(
                collumn.eq(0),
            ),
        ]

        self.sync += [
            If(output_select < 1, clk.eq(0)).Else(clk.eq(1)),
            If((counter == 0) & start,
                counter.eq(1))
            .Elif((counter == (counter_max - 1)),
                  counter.eq(0))
            .Elif((counter > 0),
                  counter.eq(counter + 1)),
            shifting_done.eq(counter == (counter_max - 1))
        ]


class Output(Module):
    def __init__(self, hub75_common, outputs_specific, buffer_readers, address):
        for i in range(8):
            out = outputs_specific[i]
            r_pins = Array([out.r0, out.r1])
            g_pins = Array([out.g0, out.g1])
            b_pins = Array([out.b0, out.b1])
            buffer_reader = buffer_readers[i]

            self.submodules += RowColorOutput(
                r_pins,
                hub75_common.output_bit,
                hub75_common.row.buffer_select,
                buffer_reader.dat_r[0:8],
            )
            self.submodules += RowColorOutput(
                g_pins,
                hub75_common.output_bit,
                hub75_common.row.buffer_select,
                buffer_reader.dat_r[8:16],
            )
            self.submodules += RowColorOutput(
                b_pins,
                hub75_common.output_bit,
                hub75_common.row.buffer_select,
                buffer_reader.dat_r[16:24],
            )

            self.comb += [buffer_reader.adr.eq(address)]


class RowColorOutput(Module):
    def __init__(
        self,
        outputs: Array(Signal(1)),
        output_bit: Signal(3),
        buffer_select: Signal(1),
        color_input: Signal(8),
    ):
        outputs_buffer = Array((Signal()) for x in range(2))
        self.sync += [
            outputs_buffer[buffer_select].eq(
                color_input >> output_bit),
        ]

        self.sync += [If((buffer_select == 0), outputs[i].eq(outputs_buffer[i]))
                      for i in range(2)]
