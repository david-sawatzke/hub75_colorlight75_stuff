#!/usr/bin/env python3
# Protocol description https://fw.hardijzer.nl/?p=223
# Using binary code modulation (http://www.batsocks.co.uk/readme/art_bcm_1.htm)
from types import SimpleNamespace

from migen import If, Signal, Array, Memory, Module, FSM, NextValue, NextState, Mux, Cat, Case
from litex.soc.interconnect.csr import AutoCSR, CSRStorage, CSRField
from litedram.frontend.dma import LiteDRAMDMAReader

sdram_offset = 0x00400000//2//4


class Hub75(Module, AutoCSR):
    def __init__(self, pins_common, pins, sdram):
        # Registers
        self.ctrl = CSRStorage(fields=[
            CSRField("indexed", description="Display an indexed image"),
            CSRField("enabled", description="Enable the output"),
            CSRField("width", description="Width of the image", size=16),
        ])
        chain_length_2 = 2
        panel_config = Array()
        for panel_output in range(8):
            for chain_pos in range(1 << chain_length_2):
                name = "panel" + str(panel_output) + "_" + str(chain_pos)
                csr = CSRStorage(name=name,
                                 fields=[
                                     CSRField(
                                         "x", description="x position in multiples of 32", size=8, offset=0),
                                     CSRField(
                                         "y", description="y position in multiples of 32", size=8, offset=8),
                                     CSRField(
                                         "rot", description="rotation in clockwise 90°", size=2, offset=16),
                                 ])
                setattr(self, name, csr)
                panel_config.append(csr)

        read_port = sdram.crossbar.get_port(mode="read", data_width=32)
        output_config = SimpleNamespace(
            indexed=self.ctrl.fields.indexed, width=self.ctrl.fields.width
        )
        self.submodules.common = FrameController(
            pins_common,
            self.ctrl.fields.enabled,
            brightness_psc=16,
        )
        self.submodules.specific = RowController(
            self.common, pins, output_config, panel_config, read_port,
            chain_length_2=chain_length_2
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
        self.clk = outputs_common.clk
        counter_max = 8

        counter = Signal(max=counter_max)
        self.output_bit = brightness_bit = Signal(max=brightness_bits)
        brightness_counter = Signal(
            max=(1 << brightness_bits) * brightness_psc)
        row_active = Signal(4)
        self.row_select = row_shifting = Signal(4)
        self.submodules.fsm = fsm = FSM(reset_state="RST")
        fsm.act("RST",
                start_shifting.eq(1),
                NextState("WAIT"))
        fsm.act("WAIT",
                If((brightness_counter == 0) & shifting_done & enable,
                    NextValue(counter, counter_max - 1),
                    NextState("LATCH")))
        fsm.act("LATCH",
                outputs_common.lat.eq(1),
                If(
                    counter == 0,
                    NextValue(brightness_counter,
                              (1 << brightness_bit) * brightness_psc),
                    start_shifting.eq(1),
                    If(brightness_bit != 0,
                        NextValue(row_active, row_shifting),
                        NextValue(brightness_bit, brightness_bit - 1),)
                    .Else(
                        NextValue(row_shifting, row_shifting + 1),
                        NextValue(brightness_bit, brightness_bits - 1),
                    ),
                    NextValue(counter, counter_max - 1),
                    NextState("WAIT"),
                ))

        self.sync += [
            If(counter != 0,
               counter.eq(counter - 1)),
            If((brightness_counter != 0) & (counter == 0),
                brightness_counter.eq(brightness_counter - 1)),
        ]

        self.comb += [
            outputs_common.oe.eq((brightness_counter == 0) | (counter != 0)),
            outputs_common.row.eq(row_active),
        ]


class RowController(Module):
    def __init__(self, hub75_common, outputs_specific, output_config,
                 panel_config, read_port, collumns_2=6, chain_length_2=0):
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
                    width=32, depth=1 << (collumns_2 + chain_length_2 + 1),
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
        row_start = Signal()
        self.submodules.buffer_reader = RamToBufferReader(
            mem_start, (hub75_common.row_select + 1) & 0xF,
            output_config.indexed, output_config.width, panel_config,
            read_port, row_writers[~shifting_buffer], palette_memory,
            collumns_2, chain_length_2)
        self.submodules.row_module = RowModule(
            row_start, hub75_common.clk, collumns_2, chain_length_2
        )

        self.submodules.output = Output(outputs_specific,
                                        row_readers[shifting_buffer], self.row_module.counter,
                                        hub75_common.output_bit, self.row_module.buffer_select
                                        )

        self.submodules.fsm = FSM(reset_state="IDLE")
        self.fsm.act("IDLE",
                     If((hub75_common.start_shifting & (hub75_common.output_bit == 7)),
                        mem_start.eq(True),
                        row_start.eq(True),
                        NextState("WAIT_TILL_START"))
                     .Elif((hub75_common.start_shifting & (hub75_common.output_bit != 7)),
                           row_start.eq(True),
                           NextState("WAIT_TILL_START"))
                     .Else(
                         hub75_common.shifting_done.eq(True),
                     ))
        self.fsm.act("WAIT_TILL_START",
                     If(self.row_module.shifting,
                        NextState("SHIFT_OUT")))
        self.fsm.act("SHIFT_OUT",
                     If((hub75_common.output_bit == 0) & ~self.row_module.shifting
                        & self.buffer_reader.done,
                        NextValue(shifting_buffer, ~shifting_buffer),
                        NextState("IDLE")),
                     If((hub75_common.output_bit != 0) & ~self.row_module.shifting,
                         NextState("IDLE"))
                     )


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
            chain_length_2=0,
    ):
        self.done = Signal()
        # If ram bandwidth is needed for something else
        self.prevent_read = Signal()
        done = Signal()
        # Eliminate the delay
        self.comb += self.done.eq(~start & done)
        self.sync += If(start, done.eq(False))

        # RAM Reader
        self.submodules.reader = LiteDRAMDMAReader(mem_read_port, 16)
        self.submodules.ram_adr = RamAddressGenerator(
            start, self.reader.sink.ready & ~self.prevent_read, row, image_width, panel_config,
            collumns_2, chain_length_2)

        # Generate rsv_level which was removed
        rsv_level = Signal(max=16 + 1)
        self.sync += [
            If(self.reader.sink.valid & self.reader.sink.ready,
               If(~(self.reader.source.valid & self.reader.source.ready),
                  rsv_level.eq(rsv_level + 1)
            )).Elif(self.reader.source.valid & self.reader.source.ready,
                rsv_level.eq(rsv_level - 1)
            )
        ]
        ram_valid = self.reader.source.valid
        ram_data = self.reader.source.data
        ram_done = Signal()
        self.comb += [
            self.reader.sink.address.eq(self.ram_adr.adr),
            self.reader.sink.valid.eq(self.ram_adr.valid & ~self.prevent_read),
            ram_done.eq((self.ram_adr.started == False)
                        & (rsv_level == 0)
                        & (self.reader.source.valid == False))
        ]
        self.sync += [
            If(self.reader.source.valid,
                self.reader.source.ready.eq(True),
               )
            .Elif(
                (self.ram_adr.started == False)
                & (rsv_level == 0),
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
        gamma_data = Signal().like(palette_data)
        self.sync += [
            gamma_data.eq(Cat(gamma_lut[palette_data[:8]],
                              gamma_lut[palette_data[8:16]],
                              gamma_lut[palette_data[16:24]])),
            gamma_data_valid.eq(palette_data_valid),
            gamma_data_done.eq(palette_data_done),
        ]

        # Buffer Writer
        buffer_done = Signal()
        buffer_counter = Signal(collumns_2 + 1 + chain_length_2 + 3)
        buffer_select = Signal(3)
        buffer_address = Signal(collumns_2 + 1 + chain_length_2)

        for i in range(8):
            self.sync += [
                If(gamma_data_valid,
                    buffer_write_port[i].dat_w.eq(gamma_data),
                    buffer_write_port[i].adr.eq(buffer_address),
                   )
            ]
        self.comb += [
            buffer_select.eq(buffer_counter[collumns_2 + 1 + chain_length_2:]),
            buffer_address.eq(
                Cat(buffer_counter[collumns_2],
                    buffer_counter[:collumns_2],
                    buffer_counter[collumns_2 + 1:collumns_2 + 1 + chain_length_2])
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
        chain_length_2,
    ):
        outputs_2 = 3
        counter = Signal(collumns_2 + 1 + chain_length_2 + outputs_2)
        running = Signal(1)
        self.started = Signal()
        delay = 2
        en = Signal()
        counter_select = Signal(chain_length_2 + outputs_2)

        # Started
        self.comb += [
            en.eq((counter < delay) | enable),
            counter_select.eq(counter[(collumns_2 + 1):]),
            running.eq(start | (counter != 0)),
        ]
        self.sync += [
            If(start, self.started.eq(True)),
            If((counter == 0) & start,
                self.started.eq(True),
                counter.eq(1))
            .Elif(counter == 0)
            .Elif((counter == (
                (1 << (collumns_2 + 1 + chain_length_2 + outputs_2)) - 1)) & en,
                counter.eq(0))
            .Elif((counter > 0) & en,
                  counter.eq(counter + 1)),
        ]

        # Delay 1
        cur_panel_config = Signal().like(panel_config[0].storage)
        config_lookup_valid = Signal()
        counter_previous = Signal().like(counter)
        collumn = counter_previous[:collumns_2]
        half_select = counter_previous[collumns_2]
        self.sync += [
            If(en,
                cur_panel_config.eq(panel_config[counter_select].storage),
                config_lookup_valid.eq(running),
                counter_previous.eq(counter))
        ]

        # Delay 2
        self.adr = Signal(32)
        self.valid = Signal(1)
        row_comb = Signal(6)
        x_offset = Signal(6)
        y_offset = Signal(6)
        self.comb += [
            row_comb.eq(half_select * 16 + row),
            Case((cur_panel_config >> 16) & 0x3, {
                 0b00: [x_offset.eq(collumn),
                        y_offset.eq(row_comb)],
                 0b01: [x_offset.eq(31 - row_comb),
                        y_offset.eq(collumn)],
                 0b10: [x_offset.eq(63 - collumn),
                        y_offset.eq(31 - row_comb)],
                 0b11:[x_offset.eq(row_comb),
                       y_offset.eq(63 - collumn)],
                 })
        ]
        self.sync += [
            If(en,
               self.valid.eq(config_lookup_valid),
                self.adr.eq(
                    sdram_offset
                    + (y_offset +
                        ((cur_panel_config >> 8) & 0xFF) * 32)
                    * image_width + x_offset
                    + (cur_panel_config & 0xFF) * 32),
                If(self.valid & (~config_lookup_valid),
                    self.started.eq(False)))
        ]


class RowModule(Module):
    def __init__(
        self,
        start: Signal(1),
        clk: Signal(1),
        collumns_2,
        chain_length_2,
    ):
        pipeline_delay = 1  # Can't change
        output_delay = 2
        delay = pipeline_delay + output_delay
        counter_max = (1 << (collumns_2 + chain_length_2 + 1)) + delay
        self.counter = counter = Signal(max=counter_max)
        buffer_counter = Signal(max=counter_max)
        self.buffer_select = buffer_select = Signal(1)
        self.shifting = Signal(1)
        self.comb += [
            buffer_select.eq(buffer_counter[0]),
        ]

        self.sync += [
            If(buffer_counter < output_delay, clk.eq(0)).Else(
                clk.eq(buffer_counter[0])
            ),
            buffer_counter.eq(counter),
            If((counter == 0) & start,
                counter.eq(1),
                self.shifting.eq(True))
            .Elif((counter == (counter_max - 1)),
                  counter.eq(0),
                  self.shifting.eq(False))
            .Elif((counter > 0),
                  counter.eq(counter + 1)),
        ]


class Output(Module):
    def __init__(self, outputs_specific, buffer_readers, address, output_bit, buffer_select):
        for i in range(8):
            out = outputs_specific[i]
            r_pins = Array([out.r0, out.r1])
            g_pins = Array([out.g0, out.g1])
            b_pins = Array([out.b0, out.b1])
            buffer_reader = buffer_readers[i]

            self.submodules += RowColorOutput(
                r_pins,
                output_bit,
                buffer_select,
                buffer_reader.dat_r[0:8],
            )
            self.submodules += RowColorOutput(
                g_pins,
                output_bit,
                buffer_select,
                buffer_reader.dat_r[8:16],
            )
            self.submodules += RowColorOutput(
                b_pins,
                output_bit,
                buffer_select,
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
