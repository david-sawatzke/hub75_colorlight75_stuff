#!/usr/bin/env python3

#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>, David Sawatzke <david@sawatzke.dev>
# SPDX-License-Identifier: BSD-2-Clause

# Build/Use ----------------------------------------------------------------------------------------
#
# ./colorlite.py --revision=6.1 --build --load
#

import os
import argparse
import sys
import subprocess

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.io import DDROutput

from litex_boards.platforms import colorlight_5a_75b

from litex.build.lattice.trellis import trellis_args, trellis_argdict
from litex.build.generic_programmer import GenericProgrammer

from litex.soc.cores.clock import *
from litex.soc.cores import uart
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.interconnect.wishbone import SRAM, Interface

from litedram.modules import M12L16161A
from litedram.phy import GENSDRPHY, HalfRateGENSDRPHY

from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII

from litex.build.generic_platform import Subsignal, Pins, Misc, IOStandard

from litespi.modules import GD25Q16
from litespi.opcodes import SpiNorFlashOpCodes as Codes
from litespi.phy.generic import LiteSPIPHY
from litespi import LiteSPI

import hub75

import helper


class ECP5Programmer(GenericProgrammer):
    needs_bitreverse = False

    def flash(self, address, bitstream_file):
        subprocess.call(["ecpprog", "-o", str(address), bitstream_file])

    def load_bitstream(self, bitstream_file):
        subprocess.call(["ecpprog", "-S", bitstream_file])

# CRG ----------------------------------------------------------------------------------------------


class _CRG(Module):
    def __init__(
        self,
        platform,
        sys_clk_freq,
        use_internal_osc=False,
        with_usb_pll=False,
        with_rst=True,
        sdram_rate="1:1",
    ):
        self.rst = Signal()
        self.clock_domains.cd_sys = ClockDomain()
        if sdram_rate == "1:2":
            self.clock_domains.cd_sys2x = ClockDomain()
            self.clock_domains.cd_sys2x_ps = ClockDomain(reset_less=True)
        else:
            self.clock_domains.cd_sys_ps = ClockDomain(reset_less=True)

        # # #

        # Clk / Rst
        if not use_internal_osc:
            clk = platform.request("clk25")
            clk_freq = 25e6
        else:
            clk = Signal()
            div = 5
            self.specials += Instance("OSCG", p_DIV=div, o_OSC=clk)
            clk_freq = 310e6 / div

        rst_n = 1 if not with_rst else platform.request("user_btn_n", 0)

        # PLL
        self.submodules.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(~rst_n | self.rst)
        pll.register_clkin(clk, clk_freq)
        pll.create_clkout(self.cd_sys, sys_clk_freq)
        if sdram_rate == "1:2":
            pll.create_clkout(self.cd_sys2x, 2 * sys_clk_freq)
            pll.create_clkout(
                self.cd_sys2x_ps, 2 * sys_clk_freq, phase=180
            )  # Idealy 90° but needs to be increased.
        else:
            pll.create_clkout(
                self.cd_sys_ps, sys_clk_freq, phase=180
            )  # Idealy 90° but needs to be increased.

        # SDRAM clock
        sdram_clk = ClockSignal(
            "sys2x_ps" if sdram_rate == "1:2" else "sys_ps")
        self.specials += DDROutput(1, 0,
                                   platform.request("sdram_clock"), sdram_clk)


# BaseSoC ------------------------------------------------------------------------------------------


class BaseSoC(SoCCore):
    def __init__(
        self,
        revision,
        sys_clk_freq=50e6,
        sdram_rate="1:1",
        **kwargs
    ):
        platform = colorlight_5a_75b.Platform(revision=revision)
        sys_clk_freq = int(sys_clk_freq)
        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(
            self,
            platform,
            sys_clk_freq,
            cpu_type="vexriscv",
            cpu_variant="minimal",
            cpu_freq=sys_clk_freq,
            ident="LiteX SoC on Colorlight 5A-75B", ident_version=True,
            integrated_rom_size=0x10000,
            integrated_ram_size=0x4000,
            # Use with `litex_server --uart --uart-port /dev/ttyUSB1`
            uart_name="serial",
            # uart_name="crossover+bridge",
            uart_baudrate=115200,
        )
        # Spi Flash TODO Only for v6.1, replace with W25Q32JV for later
        flash = GD25Q16(Codes.READ_1_1_1)
        self.submodules.spiflash_phy    = LiteSPIPHY(
            pads    = platform.request("spiflash"),
            flash   = flash,
            device  = platform.device)
        self.submodules.spiflash_mmap   = LiteSPI(
            phy             = self.spiflash_phy,
            clk_freq        = sys_clk_freq,
            mmap_endianness = self.cpu.endianness)
        self.add_csr("spiflash_mmap")
        self.add_csr("spiflash_phy")
        spiflash_region = SoCRegion(
            origin  = self.mem_map.get("spiflash", None),
            size    = flash.total_size,
            cached  = False)
        self.bus.add_slave(
            name    = "spiflash",
            slave   = self.spiflash_mmap.bus,
            region  = spiflash_region)

        self.add_constant("SPIFLASH_PAGE_SIZE", flash.page_size)

        # Internal Litex spi support, supports flashing & stuff via bios
        # Adapted from `add_spi_flash`
        # self.submodules.spiflash = spiflash = SpiFlash(
        #     pads=self.platform.request("spiflash"),
        #     div=2, with_bitbang=True, dummy=8,
        #     endianness=self.cpu.endianness)
        # spiflash.add_clk_primitive(self.platform.device)
        # spiflash_region = SoCRegion(origin=0x80000000, size=2 * 1024 * 1024)
        # self.bus.add_slave(name="spiflash", slave=spiflash.bus, region=spiflash_region)

        # Disable memtest, it takes a bit and is thus annoying
        self.add_constant("MEMTEST_DATA_SIZE", 0)
        self.add_constant("MEMTEST_ADDR_SIZE", 0)

        # CRG --------------------------------------------------------------------------------------
        with_rst = False
        # kwargs["uart_name"] not in [
        # "serial",
        # "bridge",
        # ]  # serial_rx shared with user_btn_n.
        self.submodules.crg = _CRG(platform, sys_clk_freq, with_rst=with_rst)

        # SDR SDRAM --------------------------------------------------------------------------------
        sdrphy_cls = HalfRateGENSDRPHY if sdram_rate == "1:2" else GENSDRPHY
        self.submodules.sdrphy = sdrphy_cls(platform.request("sdram"))
        sdram_cls = M12L16161A
        sdram_size = 0x40000000
        self.add_sdram(
            "sdram",
            phy=self.sdrphy,
            module=sdram_cls(sys_clk_freq, sdram_rate),
            origin=self.mem_map["main_ram"],
            size=sdram_size,
            l2_cache_size=128,
            l2_cache_reverse=False
        )

        # Add hub75 connectors
        platform.add_extension(helper.hub75_conn(platform))
        pins_common = platform.request("hub75_common")
        pins = [platform.request("hub75_data", i) for i in range(8)]

        # TODO Workaround, for some reason T3 doesn't "exist" on CABGA381 even
        #      though it exists
        # (Also in helpers)
        pins[3].r1 = Signal()

        self.submodules.hub75 = hub75.Hub75(pins_common, pins, self.sdram)

        # Disable ethernet for now
        # Ethernet / Etherbone ---------------------------------------------------------------------
        # self.submodules.ethphy = LiteEthPHYRGMII(
        #     clock_pads=self.platform.request("eth_clocks"),
        #     pads=self.platform.request("eth"),
        # )
        # self.add_csr("ethphy")
        # self.add_ethernet(phy=self.ethphy)
        # self.add_etherbone(phy=self.ethphy)


# Build --------------------------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="LiteX SoC on Colorlight 5A-75X")
    builder_args(parser)
    # soc_core_args(parser)
    trellis_args(parser)
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load", action="store_true", help="Load bitstream")
    parser.add_argument("--flash", action="store_true", help="Flash bitstream")
    parser.add_argument(
        "--revision",
        default="7.0",
        type=str,
        help="Board revision 7.0 (default) or 6.1",
    )
    parser.add_argument("--ip-address",  default="192.168.1.20",
                        help="Ethernet IP address of the board (default: 192.168.1.20).")
    parser.add_argument("--mac-address", default="0x726b895bc2e2",
                        help="Ethernet MAC address of the board (defaullt: 0x726b895bc2e2).")
    parser.add_argument(
        "--eth-phy", default=0, type=int, help="Ethernet PHY 0 or 1 (default=0)"
    )
    parser.add_argument(
        # TODO raise it to 60e6 or whatever fits for ethernet
        "--sys-clk-freq", default=50e6, help="System clock frequency (default: 50MHz)"
    )
    args = parser.parse_args()

    soc = BaseSoC(
        revision=args.revision,
        sys_clk_freq=args.sys_clk_freq,
        **soc_core_argdict(args)
    )
    builder = Builder(soc, **builder_argdict(args))
    builder.build(**trellis_argdict(args), run=args.build)

    # If requested load the resulting bitstream onto the 5A-75B
    if args.flash or args.load:
        prog = ECP5Programmer()
        if args.load:
            prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".bit"))
        if args.flash:
            prog.flash(0x00000000, os.path.join(builder.gateware_dir, soc.build_name + ".bit"))

if __name__ == "__main__":
    main()
