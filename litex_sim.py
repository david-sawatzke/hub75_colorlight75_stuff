#!/usr/bin/env python3
# This isn't really kept up-to-date and may need adjustments to work

#
# This file is part of LiteX.
#
# Copyright (c) 2015-2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2020 Antmicro <www.antmicro.com>
# Copyright (c) 2017 Pierre-Olivier Vauboin <po@lambdaconcept>
# SPDX-License-Identifier: BSD-2-Clause

import argparse

from migen import *

from litex.build.generic_platform import *
from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig

from litex.soc.integration.common import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.integration.soc import *
from litex.soc.cores.bitbang import *
from litex.soc.cores.cpu import CPUS

from litedram import modules as litedram_modules
from litedram.modules import parse_spd_hexdump
from litedram.common import *
from litedram.phy.model import SDRAMPHYModel

from liteeth.phy.gmii import LiteEthPHYGMII

# from liteeth.phy.model import LiteEthPHYModel
from liteeth.mac import LiteEthMAC
from liteeth.core.arp import LiteEthARP
from liteeth.core.ip import LiteEthIP
from liteeth.common import *

from litescope import LiteScopeAnalyzer

import hub75
from artnet2ram import Artnet2RAM
from smoleth import SmolEth
import helper

# IOs ----------------------------------------------------------------------------------------------

_io = [
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
    (
        "serial",
        0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data", Pins(8)),
        Subsignal("sink_valid", Pins(1)),
        Subsignal("sink_ready", Pins(1)),
        Subsignal("sink_data", Pins(8)),
    ),
    (
        "eth_clocks",
        0,
        Subsignal("tx", Pins(1)),
        Subsignal("rx", Pins(1)),
    ),
    (
        "eth",
        0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data", Pins(8)),
        Subsignal("sink_valid", Pins(1)),
        Subsignal("sink_ready", Pins(1)),
        Subsignal("sink_data", Pins(8)),
    ),
    (
        "gmii_eth",
        0,
        Subsignal("rx_data", Pins(8)),
        Subsignal("rx_dv", Pins(1)),
        Subsignal("rx_er", Pins(1)),
        Subsignal("tx_data", Pins(8)),
        Subsignal("tx_en", Pins(1)),
        Subsignal("tx_er", Pins(1)),
    ),
    (
        "i2c",
        0,
        Subsignal("scl", Pins(1)),
        Subsignal("sda_out", Pins(1)),
        Subsignal("sda_in", Pins(1)),
    ),
    # Colorlite-specific
    (
        "hub75_data",
        0,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        1,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        2,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        3,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        4,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        5,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        6,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_data",
        7,
        Subsignal("r0", Pins(1)),
        Subsignal("g0", Pins(1)),
        Subsignal("b0", Pins(1)),
        Subsignal("r1", Pins(1)),
        Subsignal("g1", Pins(1)),
        Subsignal("b1", Pins(1)),
    ),
    (
        "hub75_common",
        0,
        Subsignal("row", Pins(4)),
        Subsignal("clk", Pins(1)),
        Subsignal("lat", Pins(1)),
        Subsignal("oe", Pins(1)),
    ),
]

# Platform -----------------------------------------------------------------------------------------


class Platform(SimPlatform):
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)


# DFI PHY model settings ---------------------------------------------------------------------------


sdram_module_nphases = {
    "SDR": 1,
    "DDR": 2,
    "LPDDR": 2,
    "DDR2": 2,
    "DDR3": 4,
    "DDR4": 4,
}


def get_sdram_phy_settings(memtype, data_width, clk_freq):
    nphases = sdram_module_nphases[memtype]

    if memtype == "SDR":
        # Settings from gensdrphy
        rdphase = 0
        wrphase = 0
        cl = 2
        cwl = None
        read_latency = 4
        write_latency = 0
    elif memtype in ["DDR", "LPDDR"]:
        # Settings from s6ddrphy
        rdphase = 0
        wrphase = 1
        cl = 3
        cwl = None
        read_latency = 5
        write_latency = 0
    elif memtype in ["DDR2", "DDR3"]:
        # Settings from s7ddrphy
        tck = 2 / (2 * nphases * clk_freq)
        cl, cwl = get_cl_cw(memtype, tck)
        cl_sys_latency = get_sys_latency(nphases, cl)
        cwl_sys_latency = get_sys_latency(nphases, cwl)
        rdphase = get_sys_phase(nphases, cl_sys_latency, cl)
        wrphase = get_sys_phase(nphases, cwl_sys_latency, cwl)
        read_latency = cl_sys_latency + 6
        write_latency = cwl_sys_latency - 1
    elif memtype == "DDR4":
        # Settings from usddrphy
        tck = 2 / (2 * nphases * clk_freq)
        cl, cwl = get_cl_cw(memtype, tck)
        cl_sys_latency = get_sys_latency(nphases, cl)
        cwl_sys_latency = get_sys_latency(nphases, cwl)
        rdphase = get_sys_phase(nphases, cl_sys_latency, cl)
        wrphase = get_sys_phase(nphases, cwl_sys_latency, cwl)
        read_latency = cl_sys_latency + 5
        write_latency = cwl_sys_latency - 1

    sdram_phy_settings = {
        "nphases": nphases,
        "rdphase": rdphase,
        "wrphase": wrphase,
        "cl": cl,
        "cwl": cwl,
        "read_latency": read_latency,
        "write_latency": write_latency,
    }

    return PhySettings(
        phytype="SDRAMPHYModel",
        memtype=memtype,
        databits=data_width,
        dfi_databits=data_width if memtype == "SDR" else 2 * data_width,
        **sdram_phy_settings,
    )


# Simulation SoC -----------------------------------------------------------------------------------


class SimSoC(SoCCore):
    mem_map = {
        "ethmac": 0xB0000000,
    }
    mem_map.update(SoCCore.mem_map)

    def __init__(
        self,
        with_ethernet=False,
        with_etherbone=False,
        etherbone_mac_address=0x10E2D5000001,
        etherbone_ip_address="192.168.1.51",
        with_analyzer=False,
        sdram_module="M12L16161A",
        sdram_init=[],
        sdram_data_width=32,
        sdram_spd_data=None,
        sdram_verbosity=0,
        with_i2c=False,
        with_sdcard=False,
        sim_debug=False,
        trace_reset_on=False,
        **kwargs
    ):
        platform = Platform()
        sys_clk_freq = int(1e6)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(
            self,
            platform,
            clk_freq=sys_clk_freq,
            ident="LiteX Simulation",
            ident_version=True,
            **kwargs,
        )

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # SDRAM ------------------------------------------------------------------------------------
        sdram_clk_freq = int(50e6)  # FIXME: use 100MHz timings
        if sdram_spd_data is None:
            sdram_module_cls = getattr(litedram_modules, sdram_module)
            sdram_rate = "1:{}".format(sdram_module_nphases[sdram_module_cls.memtype])
            sdram_module = sdram_module_cls(sdram_clk_freq, sdram_rate)
        else:
            sdram_module = litedram_modules.SDRAMModule.from_spd_data(
                sdram_spd_data, sdram_clk_freq
            )
        phy_settings = get_sdram_phy_settings(
            memtype=sdram_module.memtype,
            data_width=sdram_data_width,
            clk_freq=sdram_clk_freq,
        )
        self.submodules.sdrphy = SDRAMPHYModel(
            module=sdram_module,
            settings=phy_settings,
            clk_freq=sdram_clk_freq,
            verbosity=sdram_verbosity,
            init=sdram_init,
        )
        self.add_sdram(
            "sdram",
            phy=self.sdrphy,
            module=sdram_module,
            origin=self.mem_map["main_ram"],
            size=kwargs.get("max_sdram_size", 0x40000000),
            l2_cache_size=kwargs.get("l2_size", 128),
            # l2_cache_min_data_width=kwargs.get(
            #     "min_l2_data_width", 128),
            l2_cache_reverse=False,
        )
        # Reduce memtest size for simulation speedup
        self.add_constant("SDRAM_TEST_DISABLE")

        pins_common = platform.request("hub75_common")
        pins = [platform.request("hub75_data", i) for i in range(8)]

        self.submodules.hub75 = hub75.Hub75(pins_common, pins, self.sdram)
        #
        # assert not (with_ethernet and with_etherbone)

        if with_ethernet and with_etherbone:
            etherbone_ip_address = convert_ip(etherbone_ip_address)
            # Ethernet PHY
            self.submodules.ethphy = LiteEthPHYGMII(
                None, self.platform.request("gmii_eth", 0), model=True
            )
            self.add_csr("ethphy")
            # Ethernet MAC
            self.submodules.ethmac = SmolEth(
                phy=self.ethphy,
                udp_port=6454,
                mac_address=etherbone_mac_address,
                ip_address=etherbone_ip_address,
                dw=32,
            )

            # SoftCPU
            self.add_memory_region("ethmac", self.mem_map["ethmac"], 0x2000, type="io")
            self.add_wb_slave(
                self.mem_regions["ethmac"].origin, self.ethmac.bus, 0x2000
            )
            self.add_csr("ethmac")
            if self.irq.enabled:
                self.irq.add("ethmac", use_loc_if_exists=True)
            # HW ethernet
            self.submodules.artnet2ram = Artnet2RAM(self.sdram)
            self.comb += [self.ethmac.udp.source.connect(self.artnet2ram.sink)]

            # Etherbone
            # self.submodules.etherbone = LiteEthEtherbone(
            #     self.udp, 1234, mode="master")
            # self.add_wb_master(self.etherbone.wishbone.bus)

        # Ethernet ---------------------------------------------------------------------------------
        elif with_ethernet:
            # Ethernet PHY
            self.submodules.ethphy = LiteEthPHYModel(self.platform.request("eth", 0))
            self.add_csr("ethphy")
            # Ethernet MAC
            ethmac = LiteEthMAC(
                phy=self.ethphy,
                dw=32,
                interface="wishbone",
                endianness=self.cpu.endianness,
            )
            if with_etherbone:
                ethmac = ClockDomainsRenamer(
                    {"eth_tx": "ethphy_eth_tx", "eth_rx": "ethphy_eth_rx"}
                )(ethmac)
            self.submodules.ethmac = ethmac
            self.add_memory_region("ethmac", self.mem_map["ethmac"], 0x2000, type="io")
            self.add_wb_slave(
                self.mem_regions["ethmac"].origin, self.ethmac.bus, 0x2000
            )
            self.add_csr("ethmac")
            if self.irq.enabled:
                self.irq.add("ethmac", use_loc_if_exists=True)

        # Etherbone --------------------------------------------------------------------------------
        elif with_etherbone:
            # Ethernet PHY
            self.submodules.ethphy = LiteEthPHYModel(
                self.platform.request("eth", 0)
            )  # FIXME
            self.add_csr("ethphy")
            # Ethernet Core
            ethcore = LiteEthUDPIPCore(
                self.ethphy,
                mac_address=etherbone_mac_address,
                ip_address=etherbone_ip_address,
                clk_freq=sys_clk_freq,
            )
            self.submodules.ethcore = ethcore
            # Etherbone
            self.submodules.etherbone = LiteEthEtherbone(
                self.ethcore.udp, 1234, mode="master"
            )
            self.add_wb_master(self.etherbone.wishbone.bus)

        # Analyzer ---------------------------------------------------------------------------------
        if with_analyzer:
            analyzer_signals = [
                # IBus (could also just added as self.cpu.ibus)
                self.cpu.ibus.stb,
                self.cpu.ibus.cyc,
                self.cpu.ibus.adr,
                self.cpu.ibus.we,
                self.cpu.ibus.ack,
                self.cpu.ibus.sel,
                self.cpu.ibus.dat_w,
                self.cpu.ibus.dat_r,
                # DBus (could also just added as self.cpu.dbus)
                self.cpu.dbus.stb,
                self.cpu.dbus.cyc,
                self.cpu.dbus.adr,
                self.cpu.dbus.we,
                self.cpu.dbus.ack,
                self.cpu.dbus.sel,
                self.cpu.dbus.dat_w,
                self.cpu.dbus.dat_r,
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(
                analyzer_signals, depth=512, clock_domain="sys", csr_csv="analyzer.csv"
            )
            self.add_csr("analyzer")

        # I2C --------------------------------------------------------------------------------------
        if with_i2c:
            pads = platform.request("i2c", 0)
            self.submodules.i2c = I2CMasterSim(pads)
            self.add_csr("i2c")

        # SDCard -----------------------------------------------------------------------------------
        if with_sdcard:
            self.add_sdcard("sdcard", use_emulator=True)

        # Simulation debugging ----------------------------------------------------------------------
        if sim_debug:
            platform.add_debug(self, reset=1 if trace_reset_on else 0)
        else:
            self.comb += platform.trace.eq(1)


# Build --------------------------------------------------------------------------------------------


def sim_args(parser):
    builder_args(parser)
    soc_core_args(parser)
    parser.add_argument(
        "--threads", default=1, help="Set number of threads (default=1)"
    )
    parser.add_argument("--rom-init", default=None, help="rom_init file")
    parser.add_argument("--ram-init", default=None, help="ram_init file")
    parser.add_argument(
        "--sdram-module", default="M12L16161A", help="Select SDRAM chip"
    )
    parser.add_argument(
        "--sdram-data-width", default=32, help="Set SDRAM chip data width"
    )
    parser.add_argument("--sdram-init", default=None, help="SDRAM init file")
    parser.add_argument(
        "--sdram-from-spd-dump",
        default=None,
        help="Generate SDRAM module based on data from SPD EEPROM dump",
    )
    parser.add_argument(
        "--sdram-verbosity", default=0, help="Set SDRAM checker verbosity"
    )
    parser.add_argument(
        "--with-ethernet", action="store_true", help="Enable Ethernet support"
    )
    parser.add_argument(
        "--with-etherbone", action="store_true", help="Enable Etherbone support"
    )
    parser.add_argument(
        "--local-ip",
        default="192.168.1.50",
        help="Local IP address of SoC (default=192.168.1.50)",
    )
    parser.add_argument(
        "--remote-ip",
        default="192.168.1.100",
        help="Remote IP address of TFTP server (default=192.168.1.100)",
    )
    parser.add_argument(
        "--with-analyzer", action="store_true", help="Enable Analyzer support"
    )
    parser.add_argument("--with-i2c", action="store_true", help="Enable I2C support")
    parser.add_argument(
        "--with-sdcard", action="store_true", help="Enable SDCard support"
    )
    parser.add_argument("--trace", action="store_true", help="Enable Tracing")
    parser.add_argument(
        "--trace-fst", action="store_true", help="Enable FST tracing (default=VCD)"
    )
    parser.add_argument("--trace-start", default="0", help="Time to start tracing (ps)")
    parser.add_argument("--trace-end", default="-1", help="Time to end tracing (ps)")
    parser.add_argument(
        "--opt-level", default="O3", help="Compilation optimization level"
    )
    parser.add_argument(
        "--sim-debug", action="store_true", help="Add simulation debugging modules"
    )


def main():
    parser = argparse.ArgumentParser(description="Generic LiteX SoC Simulation")
    sim_args(parser)
    args = parser.parse_args()

    soc_kwargs = soc_core_argdict(args)
    builder_kwargs = builder_argdict(args)

    sys_clk_freq = int(50e6)
    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=sys_clk_freq)

    # Configuration --------------------------------------------------------------------------------

    cpu = CPUS[soc_kwargs.get("cpu_type", "vexriscv")]
    if soc_kwargs["uart_name"] == "serial":
        soc_kwargs["uart_name"] = "sim"
        sim_config.add_module("serial2console", "serial")
    if args.rom_init:
        soc_kwargs["integrated_rom_init"] = get_mem_data(args.rom_init, cpu.endianness)

    soc_kwargs["integrated_main_ram_size"] = 0x0
    soc_kwargs["sdram_module"] = args.sdram_module
    soc_kwargs["sdram_data_width"] = int(args.sdram_data_width)
    soc_kwargs["sdram_verbosity"] = int(args.sdram_verbosity)
    if args.sdram_from_spd_dump:
        soc_kwargs["sdram_spd_data"] = parse_spd_hexdump(args.sdram_from_spd_dump)

    if args.with_ethernet or args.with_etherbone:
        sim_config.add_module(
            "gmii_ethernet",
            "gmii_eth",
            args={"interface": "tap0", "ip": args.remote_ip},
        )
        # sim_config.add_module("ethernet", "eth", args={
        #                       "interface": "tap0", "ip": args.remote_ip})

    if args.with_i2c:
        sim_config.add_module("spdeeprom", "i2c")

    trace_start = int(float(args.trace_start))
    trace_end = int(float(args.trace_end))

    # SoC ------------------------------------------------------------------------------------------
    soc = SimSoC(
        with_ethernet=args.with_ethernet,
        with_etherbone=args.with_etherbone,
        with_analyzer=args.with_analyzer,
        with_i2c=args.with_i2c,
        with_sdcard=args.with_sdcard,
        sim_debug=args.sim_debug,
        trace_reset_on=trace_start > 0 or trace_end > 0,
        sdram_init=[]
        if args.sdram_init is None
        else get_mem_data(args.sdram_init, cpu.endianness),
        **soc_kwargs,
    )
    if args.ram_init is not None or args.sdram_init is not None:
        soc.add_constant("ROM_BOOT_ADDRESS", soc.mem_map["main_ram"])
    if args.with_ethernet:
        for i in range(4):
            soc.add_constant(
                "LOCALIP{}".format(i + 1), int(args.local_ip.split(".")[i])
            )
        for i in range(4):
            soc.add_constant(
                "REMOTEIP{}".format(i + 1), int(args.remote_ip.split(".")[i])
            )

    # Build/Run ------------------------------------------------------------------------------------
    builder_kwargs["csr_csv"] = "csr.csv"
    builder = Builder(soc, **builder_kwargs)
    for i in range(2):
        build = i == 0
        run = i == 1
        vns = builder.build(
            build=build,
            run=run,
            threads=args.threads,
            sim_config=sim_config,
            opt_level=args.opt_level,
            trace=args.trace,
            trace_fst=args.trace_fst,
            trace_start=trace_start,
            trace_end=trace_end,
        )
        if args.with_analyzer:
            soc.analyzer.export_csv(vns, "analyzer.csv")


if __name__ == "__main__":
    main()
