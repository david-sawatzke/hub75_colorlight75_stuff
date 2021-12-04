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
from litex.build.lattice.programmer import EcpprogProgrammer

from litex.soc.cores.clock import *
from litex.soc.cores import uart
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.builder import *
from litex.soc.interconnect.wishbone import SRAM, Interface
from litex.soc.interconnect import wishbone
from litex.soc.integration import export
from litedram.frontend.wishbone import LiteDRAMWishbone2Native

from litedram.modules import M12L16161A
from litedram.phy import GENSDRPHY, HalfRateGENSDRPHY

from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from liteeth.mac import LiteEthMAC
from liteeth.core.arp import LiteEthARP
from liteeth.core.ip import LiteEthIP
from liteeth.core.udp import LiteEthUDP
from liteeth.core.icmp import LiteEthICMP
from liteeth.core import LiteEthUDPIPCore
from liteeth.common import *

from litex.build.generic_platform import Subsignal, Pins, Misc, IOStandard

from litespi.modules import GD25Q16
from litespi.opcodes import SpiNorFlashOpCodes as Codes
from litespi.phy.generic import LiteSPIPHY
from litespi import LiteSPI

import hub75

from artnet2ram import Artnet2RAM

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

        # SDRAM clock
        sdram_clk = ClockSignal("sys2x_ps" if sdram_rate == "1:2" else "sys_ps")
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), sdram_clk)


# BaseSoC ------------------------------------------------------------------------------------------


class BaseSoC(SoCCore):
    def __init__(self, revision, sys_clk_freq=50e6, sdram_rate="1:1", **kwargs):
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
            ident="LiteX SoC on Colorlight 5A-75B",
            ident_version=True,
            integrated_rom_size=0x10000,
            integrated_ram_size=0x0,
            # Use with `litex_server --uart --uart-port /dev/ttyUSB1`
            uart_name="serial",
            # uart_name="crossover+bridge",
            uart_baudrate=115200,
        )
        # Spi Flash TODO Only for v6.1, replace with W25Q32JV for later
        flash = GD25Q16(Codes.READ_1_1_1)
        self.submodules.spiflash_phy = LiteSPIPHY(
            pads=platform.request("spiflash"), flash=flash, device=platform.device
        )
        self.submodules.spiflash_mmap = LiteSPI(
            phy=self.spiflash_phy,
            clk_freq=sys_clk_freq,
            mmap_endianness=self.cpu.endianness,
        )
        self.add_csr("spiflash_mmap")
        self.add_csr("spiflash_phy")
        spiflash_region = SoCRegion(
            origin=self.mem_map.get("spiflash", None),
            size=flash.total_size,
            cached=False,
        )
        self.bus.add_slave(
            name="spiflash", slave=self.spiflash_mmap.bus, region=spiflash_region
        )

        self.add_constant(
            "FLASH_BOOT_ADDRESS", self.bus.regions["spiflash"].origin + 0x100000
        )
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
        sdram_size = 4 * 1024 * 1024
        self.add_sdram(
            "sdram",
            phy=self.sdrphy,
            module=sdram_cls(sys_clk_freq, sdram_rate),
            origin=self.mem_map["main_ram"],
            size=sdram_size,
            l2_cache_size=8192,
            l2_cache_reverse=False,
            l2_cache_full_memory_we=False,
        )

        # Add special, uncached mirror of sdram
        port = self.sdram.crossbar.get_port()

        wb_sdram = wishbone.Interface()
        self.bus.add_slave("main_ram_uncached", wb_sdram,
            SoCRegion(origin=0x90000000, size=sdram_size, cached=False))
        self.submodules.wishbone_bridge = LiteDRAMWishbone2Native(
            wishbone     = wb_sdram,
            port         = port,
            base_address = self.bus.regions["main_ram_uncached"].origin)


        # Add hub75 connectors
        platform.add_extension(helper.hub75_conn(platform))
        pins_common = platform.request("hub75_common")
        pins = [platform.request("hub75_data", i) for i in range(8)]

        self.submodules.hub75 = hub75.Hub75(pins_common, pins, self.sdram)

        # Ethernet / Etherbone ---------------------------------------------------------------------
        # Use phy0
        self.submodules.ethphy = phy = LiteEthPHYRGMII(
            clock_pads=self.platform.request("eth_clocks", 0),
            pads=self.platform.request("eth", 0),
            tx_delay=0e-9,
        )

        etherbone_mac_address = 0x10e2d5000001
        etherbone_ip_address = convert_ip("192.168.1.51")

        self.submodules.ethmac = LiteEthMAC(phy=self.ethphy, dw=32,
            interface  = "hybrid",
            endianness = self.cpu.endianness,
            hw_mac     = etherbone_mac_address,
            with_sys_datapath = True)
        # SoftCPU
        self.add_memory_region("ethmac", self.mem_map.get("ethmac", None), 0x2000, type="io")
        self.add_wb_slave(self.mem_regions["ethmac"].origin, self.ethmac.bus, 0x2000)
        if self.irq.enabled:
            self.irq.add("ethmac", use_loc_if_exists=True)
        eth_rx_clk = getattr(phy, "crg", phy).cd_eth_rx.clk
        eth_tx_clk = getattr(phy, "crg", phy).cd_eth_tx.clk
        self.platform.add_period_constraint(eth_rx_clk, 1e9/phy.rx_clk_freq)
        self.platform.add_period_constraint(eth_tx_clk, 1e9/phy.tx_clk_freq)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk, eth_rx_clk, eth_tx_clk)
        # HW ethernet
        self.submodules.arp  = LiteEthARP(self.ethmac, etherbone_mac_address, etherbone_ip_address, sys_clk_freq, dw=32)
        self.submodules.ip   = LiteEthIP(self.ethmac, etherbone_mac_address, etherbone_ip_address, self.arp.table, dw=32)
        self.submodules.icmp = LiteEthICMP(self.ip, etherbone_ip_address, dw=32)
        self.submodules.udp  = LiteEthUDP(self.ip, etherbone_ip_address, dw=32)
        # self.add_ethernet(phy=self.ethphy)
        # self.add_ethip(self.ethphy)
        # self.add_etherbone(phy=self.ethphy)

        self.submodules.artnet2ram = Artnet2RAM(self.sdram, self.udp)

        ## Reduce bios size
        # Disable memtest, it takes a bit and is thus annoying
        self.add_constant("SDRAM_TEST_DISABLE")


# Build --------------------------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Colorlight 5A-75X")
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
    parser.add_argument(
        "--ip-address",
        default="192.168.1.20",
        help="Ethernet IP address of the board (default: 192.168.1.20).",
    )
    parser.add_argument(
        "--mac-address",
        default="0x726b895bc2e2",
        help="Ethernet MAC address of the board (defaullt: 0x726b895bc2e2).",
    )
    parser.add_argument(
        # TODO raise it to 60e6 or whatever fits for ethernet
        "--sys-clk-freq",
        default=50e6,
        help="System clock frequency (default: 50MHz)",
    )
    args = parser.parse_args()

    soc = BaseSoC(
        revision=args.revision, sys_clk_freq=args.sys_clk_freq, **soc_core_argdict(args)
    )
    builder_options = builder_argdict(args)
    # builder_options["csr_svd"] = "sw_rust/litex-pac/colorlight.svd"
    # builder_options["memory_x"] = "sw_rust/litex-pac/memory.x"
    builder = Builder(soc, **builder_options, bios_options=["TERM_MINI"])
    builder.build(**trellis_argdict(args), run=args.build)

    # Generate svd
    csr_svd_contents = export.get_csr_svd(soc)
    # PATCH IT
    ethmac_adr = soc.mem_regions["ethmac"].origin
    csr_svd_contents = modify_svd(csr_svd_contents, ethmac_adr)
    # Write it out!
    write_to_file("sw_rust/litex-pac/colorlight.svd", csr_svd_contents)

    # If requested load the resulting bitstream onto the 5A-75B
    if args.flash or args.load:
        prog = EcpprogProgrammer()
        if args.load:
            prog.load_bitstream(
                os.path.join(builder.gateware_dir, soc.build_name + ".bit")
            )
        if args.flash:
            prog.flash(
                0x00000000, os.path.join(builder.gateware_dir, soc.build_name + ".bit")
            )

def modify_svd(svd_contents, eth_addr):
    # Add Ethernet buffer peripheral to svd
    registers = """        <peripheral>
            <name>ETHMEM</name>
""" + "            <baseAddress>" + hex(eth_addr) + """</baseAddress>
            <groupName>ETHMEM</groupName>
            <registers>
                <register>
                    <name>RX_BUFFER_0[%s]</name>
                    <dim>2048</dim>
                    <dimIncrement>1</dimIncrement>
                    <description><![CDATA[rx buffers]]></description>
                    <addressOffset>0x0000</addressOffset>
                    <resetValue>0x00</resetValue>
                    <size>8</size>
                    <access>read-only</access>
                    <fields>
                        <field>
                            <name>rx_buffer_0</name>
                            <msb>7</msb>
                            <bitRange>[7:0]</bitRange>
                            <lsb>0</lsb>
                        </field>
                    </fields>
                </register>
                <register>
                    <name>RX_BUFFER_1[%s]</name>
                    <dim>2048</dim>
                    <dimIncrement>1</dimIncrement>
                    <description><![CDATA[rx buffers]]></description>
                    <addressOffset>0x0800</addressOffset>
                    <resetValue>0x00</resetValue>
                    <size>8</size>
                    <access>read-only</access>
                    <fields>
                        <field>
                            <name>rx_buffer_1</name>
                            <msb>7</msb>
                            <bitRange>[7:0]</bitRange>
                            <lsb>0</lsb>
                        </field>
                    </fields>
                </register>
                <register>
                    <name>TX_BUFFER_0[%s]</name>
                    <dim>2048</dim>
                    <dimIncrement>1</dimIncrement>
                    <description><![CDATA[tx buffers]]></description>
                    <addressOffset>0x1000</addressOffset>
                    <resetValue>0x00</resetValue>
                    <size>8</size>
                    <access>read-write</access>
                    <fields>
                        <field>
                            <name>tx_buffer_0</name>
                            <msb>7</msb>
                            <bitRange>[7:0]</bitRange>
                            <lsb>0</lsb>
                        </field>
                    </fields>
                </register>
                <register>
                    <name>TX_BUFFER_1[%s]</name>
                    <dim>2048</dim>
                    <dimIncrement>1</dimIncrement>
                    <description><![CDATA[tx buffers]]></description>
                    <addressOffset>0x1800</addressOffset>
                    <resetValue>0x00</resetValue>
                    <size>8</size>
                    <access>read-write</access>
                    <fields>
                        <field>
                            <name>tx_buffer_1</name>
                            <msb>7</msb>
                            <bitRange>[7:0]</bitRange>
                            <lsb>0</lsb>
                        </field>
                    </fields>
                </register>
            </registers>
            <addressBlock>
                <offset>0</offset>
                <size>0x4000</size>
                <usage>buffer</usage>
            </addressBlock>
        </peripheral>
    </peripherals>"""

    return svd_contents.replace("</peripherals>", registers)


if __name__ == "__main__":
    main()
