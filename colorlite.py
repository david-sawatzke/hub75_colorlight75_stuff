#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# Build/Use ----------------------------------------------------------------------------------------
#
# 1) SoC with regular UART and optional Ethernet connected to the CPU:
# Connect a USB/UART to J19: TX of the FPGA is DATA_LED-, RX of the FPGA is KEY+.
# ./colorlight_5a_75x.py --revision=7.0 (or 6.1) --build (--with-ethernet to add Ethernet capability)
# Note: on revision 6.1, add --uart-baudrate=9600 to lower the baudrate.
# ./colorlight_5a_75x.py --load
# You should see the LiteX BIOS and be able to interact with it.
#
# 2) SoC with UART in crossover mode over Etherbone:
# ./colorlight_5a_75x.py --revision=7.0 (or 6.1) --uart-name=crossover --with-etherbone --csr-csv=csr.csv
# ./colorlight_5a_75x.py --load
# ping 192.168.1.50
# Get and install wishbone tool from: https://github.com/litex-hub/wishbone-utils/releases
# wishbone-tool --ethernet-host 192.168.1.50 --server terminal --csr-csv csr.csv
# You should see the LiteX BIOS and be able to interact with it.
#
# 3) SoC with USB-ACM UART (on V7.0):
# - Replace U23 with a SN74CBT3245APWR or remove U23 and place jumper wires to make the ports bi-directional.
# - Place a 15K resistor between J4 pin 2 and J4 pin 4.
# - Place a 15K resistor between J4 pin 3 and J4 pin 4.
# - Place a 1.5K resistor between J4 pin 1 and J4 pin 3.
# - Connect USB DP (Green) to J4 pin 3, USB DN (White) to J4 pin 2.
# ./colorlight_5a_75x.py --revision=7.0 --uart-name=usb_acm
# ./colorlight_5a_75x.py --load
# You should see the LiteX BIOS and be able to interact with it.
#
# Disclaimer: SoC 2) is still a Proof of Concept with large timings violations on the IP/UDP and
# Etherbone stack that need to be optimized. It was initially just used to validate the reversed
# pinout but happens to work on hardware...

import os
import argparse
import sys

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.io import DDROutput

from litex_boards.platforms import colorlight_5a_75b

from litex.build.lattice.trellis import trellis_args, trellis_argdict

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

import hub75

import helper


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

        # USB PLL
        if with_usb_pll:
            self.submodules.usb_pll = usb_pll = ECP5PLL()
            self.comb += usb_pll.reset.eq(~rst_n | self.rst)
            usb_pll.register_clkin(clk, clk_freq)
            self.clock_domains.cd_usb_12 = ClockDomain()
            self.clock_domains.cd_usb_48 = ClockDomain()
            usb_pll.create_clkout(self.cd_usb_12, 12e6, margin=0)
            usb_pll.create_clkout(self.cd_usb_48, 48e6, margin=0)

        # SDRAM clock
        sdram_clk = ClockSignal("sys2x_ps" if sdram_rate == "1:2" else "sys_ps")
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), sdram_clk)


# BaseSoC ------------------------------------------------------------------------------------------


class BaseSoC(SoCCore):
    def __init__(
        self,
        revision,
        with_ethernet=False,
        with_etherbone=False,
        sys_clk_freq=50e6,
        sdram_rate="1:1",
        **kwargs
    ):
        platform = colorlight_5a_75b.Platform(revision=revision)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(
            self,
            platform,
            sys_clk_freq,
            ident="LiteX SoC on Colorlight 5A-75B",
            ident_version=True,
            **kwargs
        )

        # TODO Remove this
        # Reduce memtest size to avoid walking over image data
        self.add_constant("MEMTEST_DATA_SIZE", 0)
        self.add_constant("MEMTEST_ADDR_SIZE", 0)

        # Use with `litex_server --uart --uart-port /dev/ttyUSB1 --uart-baudrate 9600`
        uart_bridge = uart.UARTWishboneBridge(
            pads     = platform.request("serial"),
            clk_freq = sys_clk_freq,
            baudrate = 9600)
        self.submodules += uart_bridge
        self.add_wb_master(uart_bridge.wishbone)

        # CRG --------------------------------------------------------------------------------------
        with_rst = False
        #kwargs["uart_name"] not in [
            #"serial",
            #"bridge",
        #]  # serial_rx shared with user_btn_n.
        self.submodules.crg = _CRG(platform, sys_clk_freq, with_rst=with_rst)

        # Add hub75 connectors
        platform.add_extension(helper.hub75_conn(platform))

        hub75_common = hub75.Common(
            platform.request("hub75_common"),
            # TODO Adjust later on
            brightness_psc=15,
        )
        self.submodules.hub75_common = hub75_common
        pins = [platform.request("hub75_data", 1), platform.request("hub75_data", 2)]

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
            size=kwargs.get("max_sdram_size", sdram_size),
            l2_cache_size=kwargs.get("l2_size", 8192),
            l2_cache_min_data_width=kwargs.get("min_l2_data_width", 128),
            l2_cache_reverse=True,
        )

        write_port = self.sdram.crossbar.get_port(mode="write", data_width=32)
        read_port = self.sdram.crossbar.get_port(mode="read", data_width=32)

        self.submodules.hub75_specific = specific = hub75.SpecificMemoryStuff(
            hub75_common, pins, write_port, read_port
        )

        # Now add the palette memory as ram

        self.submodules.palette_ram = palette_ram = SRAM(specific.palette_memory, bus=Interface(data_width=self.bus.data_width))
        self.bus.add_slave("palette", palette_ram.bus, SoCRegion(origin=0x90000000, size=palette_ram.mem.depth, linker=True))

        # Ethernet / Etherbone ---------------------------------------------------------------------
        # if with_ethernet or with_etherbone:
        #     self.submodules.ethphy = LiteEthPHYRGMII(
        #         clock_pads=self.platform.request("eth_clocks"),
        #         pads=self.platform.request("eth"),
        #     )
        #     self.add_csr("ethphy")
        #     if with_ethernet:
        #         self.add_ethernet(phy=self.ethphy)
        #     if with_etherbone:
        #         self.add_etherbone(phy=self.ethphy)


# Build --------------------------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Colorlight 5A-75X")
    builder_args(parser)
    soc_core_args(parser)
    trellis_args(parser)
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load", action="store_true", help="Load bitstream")
    parser.add_argument(
        "--revision",
        default="7.0",
        type=str,
        help="Board revision 7.0 (default) or 6.1",
    )
    parser.add_argument(
        "--with-ethernet", action="store_true", help="Enable Ethernet support"
    )
    parser.add_argument(
        "--with-etherbone", action="store_true", help="Enable Etherbone support"
    )
    parser.add_argument(
        "--eth-phy", default=0, type=int, help="Ethernet PHY 0 or 1 (default=0)"
    )
    parser.add_argument(
        # TODO raise it to 60e6 or whatever fits for ethernet
        "--sys-clk-freq", default=40e6, help="System clock frequency (default: 50MHz)"
    )
    args = parser.parse_args()

    assert not (args.with_ethernet and args.with_etherbone)
    soc = BaseSoC(
        revision=args.revision,
        with_ethernet=args.with_ethernet,
        with_etherbone=args.with_etherbone,
        sys_clk_freq=args.sys_clk_freq,
        **soc_core_argdict(args)
    )
    builder = Builder(soc, **builder_argdict(args))
    builder.build(**trellis_argdict(args), run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        print(os.path.join(builder.gateware_dir, soc.build_name + ".svf"))
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".svf"))


if __name__ == "__main__":
    main()
