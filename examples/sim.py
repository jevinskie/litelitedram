#!/usr/bin/env python3

# Copyright (c) 2022 Jevin Sweval <jevinsweval@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

import argparse
from pathlib import Path

from liteeth.phy.model import LiteEthPHYModel
from litescope import LiteScopeAnalyzer
from litex.build.generic_platform import *
from litex.build.sim import SimPlatform, sim_build_argdict, sim_build_args
from litex.build.sim.config import SimConfig
from litex.gen.fhdl.namer import escape_identifier_name
from litex.soc.cores import uart
from litex.soc.integration.builder import *
from litex.soc.integration.soc_core import *
from migen import *

from litelitedram.ddr3 import SlowDDR3
from litelitedram.ddr3_model import DDR3Model, DDR3PhyInterface

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk / Rst.
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
    # Ethernet
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
    # Serial.
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
]


# Platform -----------------------------------------------------------------------------------------


class Platform(SimPlatform):
    def __init__(self, sim_toolchain):
        output_dir = None
        mname = "sim"
        if sim_toolchain != "verilator":
            mname = escape_identifier_name(Path(__file__).stem)
            output_dir = os.path.join("build", mname + "_" + sim_toolchain)
        super().__init__(self, _io, name=mname, toolchain=sim_toolchain)
        self.output_dir = output_dir


# Bench SoC ----------------------------------------------------------------------------------------


class SimSoC(SoCCore):
    def __init__(
        self,
        sim_toolchain,
        sys_clk_freq=None,
        with_analyzer=False,
        with_etherbone=False,
        with_uartbone=False,
        **kwargs,
    ):
        platform = Platform(sim_toolchain)
        sys_clk_freq = int(sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCMini.__init__(
            self,
            platform,
            clk_freq=sys_clk_freq,
            ident="litelitedram sim",
            **kwargs,
        )

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # Etherbone --------------------------------------------------------------------------------
        if with_etherbone:
            self.submodules.ethphy = LiteEthPHYModel(self.platform.request("eth"))
            self.add_etherbone(phy=self.ethphy, ip_address="192.168.42.50")

        # UARTbone ---------------------------------------------------------------------------------
        if with_uartbone:
            self.submodules.uartbone_phy = uart.RS232PHYModel(platform.request("serial"))
            self.submodules.uartbone = uart.UARTBone(phy=self.uartbone_phy, clk_freq=sys_clk_freq)
            self.bus.add_master(name="uartbone", master=self.uartbone.wishbone)

        # Slow DDR3 --------------------------------------------------------------------------------
        # ddr3_pads = DDR3PhyInterface()
        # self.submodules.ddr = SlowDDR3(self.platform, ddr3_pads, sys_clk_freq, debug=True)
        # dram_base = 0x2000_0000
        # self.add_memory_region("dram", dram_base, self.ddr.bitsize // 8, type="")
        # self.bus.add_slave("dram", self.ddr.bus)
        # self.submodules.ddr_model = DDR3Model(self.platform, ddr3_pads)
        # self.register_mem("dram", dram_base, self.ddr.bus, size=self.ddr.bitsize // 8)

        # scope ------------------------------------------------------------------------------------
        if with_analyzer:
            analyzer_signals = [
                ddr3_pads.a,
                ddr3_pads.ba,
                ddr3_pads.cas_n,
                ddr3_pads.ras_n,
                ddr3_pads.we_n,
                ddr3_pads.cs_n,
                ddr3_pads.dm,
                ddr3_pads.dq,
                # ddr3_pads.dqs_p,
                self.ddr.init_state,
                self.ddr.work_state,
                self.ddr.refresh_cnt,
                self.ddr.refresh_issued,
                self.ddr.bus,
                self.ddr.sysio,
            ]
            self.submodules.analyzer = LiteScopeAnalyzer(
                analyzer_signals,
                depth=4096,
                clock_domain="sys",
                rle_nbits_min=15,
                csr_csv="analyzer.csv",
            )


#
# Main ---------------------------------------------------------------------------------------------


def sim_args(parser):
    builder_args(parser)
    soc_core_args(parser)
    sim_build_args(parser)
    parser.add_argument("--debug-soc-gen", action="store_true", help="Don't run simulation")
    parser.add_argument("--with-analyzer", action="store_true", help="Use litescope")
    parser.add_argument("--with-etherbone", action="store_true", help="Use Etherbone")
    parser.add_argument("--with-uartbone", action="store_true", help="Use UARTbone")


def main():
    parser = argparse.ArgumentParser(description="litelitedram sim")
    sim_args(parser)
    args = parser.parse_args()

    sys_clk_freq = int(100e6)

    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=sys_clk_freq)
    if args.with_etherbone:
        sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": "192.168.42.100"})
    if args.with_uartbone:
        sim_config.add_module("serial2tcp", "serial", args={"port": 2430})

    soc_kwargs = soc_core_argdict(args)
    builder_kwargs = builder_argdict(args)
    sim_build_kwargs = sim_build_argdict(args)

    soc_kwargs["sys_clk_freq"] = sys_clk_freq
    soc_kwargs["cpu_type"] = "None"
    soc_kwargs["with_uart"] = False
    soc_kwargs["ident_version"] = True

    soc = SimSoC(
        sim_toolchain=args.sim_toolchain,
        with_analyzer=args.with_analyzer,
        with_etherbone=args.with_etherbone,
        with_uartbone=args.with_uartbone,
        **soc_kwargs,
    )

    builder_kwargs["csr_csv"] = "csr.csv"
    builder_kwargs["output_dir"] = soc.platform.output_dir

    if not args.debug_soc_gen:
        builder = Builder(soc, **builder_kwargs)
        for i in range(2):
            build = i == 0
            run = i == 1 and builder.compile_gateware
            builder.build(build=build, run=run, sim_config=sim_config, **sim_build_kwargs)


if __name__ == "__main__":
    main()
