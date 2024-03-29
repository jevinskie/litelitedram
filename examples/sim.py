#!/usr/bin/env python3

# Copyright (c) 2022 Jevin Sweval <jevinsweval@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

from typing import Generator

from liteeth.phy.model import LiteEthPHYModel
from litescope import LiteScopeAnalyzer
from litex.build.generic_platform import *
from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig
from litex.gen.fhdl.sim import *
from litex.soc.cores import uart
from litex.soc.integration.builder import *
from litex.soc.integration.soc_core import *
from litex.soc.interconnect import wishbone
from migen import *
from migen.fhdl.structure import _Statement
from rich import print

from litelitedram.ddr3 import SlowDDR3
from litelitedram.ddr3_model import DDR3Model, DDR3PhyInterface
from litelitedram.utils import (
    get_signals,
    get_signals_tree,
    rename_migen_fsm,
    reverse_signal,
)

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
    # UARTbone over TCP.
    (
        "uartbone",
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
    def __init__(self):
        output_dir = None
        mname = "sim"
        super().__init__(self, _io, name=mname)
        self.output_dir = output_dir


class WBRegister(Module):
    def __init__(self, width, addr_width=16, registered=True) -> None:
        from litex.soc.interconnect import wishbone

        self.d = d = Signal(width)
        self.q = q = Signal(width)
        self.a = a = Signal(addr_width)
        self.bus = bus = wishbone.Interface(width, addr_width)
        wb_valid = Signal()
        ack = Signal()
        dat_r = Signal.like(bus.dat_r)

        # fmt: off
        self.comb += [
            d.eq(q),
            wb_valid.eq(bus.cyc & bus.stb),
            If(wb_valid,
                a.eq(bus.adr),
                ack.eq(1),
                If(bus.we,
                    d.eq(bus.dat_w),
                ).Else(
                    dat_r.eq(q),
                ),
            ),
        ]
        # fmt: on

        self.sync += q.eq(d)

        if not registered:
            # fmt: off
            self.comb += [
                bus.dat_r.eq(dat_r),
                bus.ack.eq(ack),
            ]
            # fmt: on
        else:
            # fmt: off
            self.submodules.fsm = fsm = FSM()
            fsm.act("READ_WRITE",
                bus.dat_r.eq(dat_r),
                bus.ack.eq(ack),
                NextState("WAIT"),
            )
            fsm.act("WAIT",
                If(ack,
                    NextState("READ_WRITE"),
                )
            )
            # fmt: on


def TimeoutCheck(tries):
    yield EmptyStatement()
    # yield If(tries >= 32, Display("TIMEOUT!"), Finish())


class WBInterface(wishbone.Interface):
    def controller_write_hdl(
        self,
        fsm: FSM,
        next_state,
        adr: Signal | int,
        dat: Signal | int,
        sel: Signal | int | None = None,
        cti: Signal | int | None = None,
        bte: Signal | int | None = None,
        tries: Signal | None = None,
    ) -> Generator[_Statement, None, None]:
        if sel is None:
            sel = 2 ** len(self.sel) - 1

        timeout_check = list(TimeoutCheck(tries)) if tries is not None else []

        def statements():
            for s in timeout_check:
                yield s
            yield self.adr.eq(adr)
            yield self.dat_w.eq(dat)
            yield self.sel.eq(sel)
            if cti is not None:
                yield self.cti.eq(cti)
            if bte is not None:
                yield self.bte.eq(bte)
            yield self.we.eq(1)
            yield self.cyc.eq(1)
            yield self.stb.eq(1)
            yield If(
                self.ack,
                Display(next_state + "_BUS_ACKED"),
                NextState(next_state),
            )

        for s in statements():
            yield s

    def controller_read_hdl(
        self,
        fsm: FSM,
        next_state,
        adr: Signal | int,
        dat: Signal,
        sel: Signal | int | None = None,
        cti: Signal | int | None = None,
        bte: Signal | int | None = None,
        tries: Signal | None = None,
    ) -> Generator[_Statement, None, None]:
        if sel is None:
            sel = 2 ** len(self.sel) - 1

        timeout_check = list(TimeoutCheck(tries)) if tries is not None else []

        def statements():
            for s in timeout_check:
                yield s
            yield self.adr.eq(adr)
            yield self.sel.eq(sel)
            if cti is not None:
                yield self.cti.eq(cti)
            if bte is not None:
                yield self.bte.eq(bte)
            yield self.we.eq(0)
            yield self.cyc.eq(1)
            yield self.stb.eq(1)
            yield If(
                self.ack,
                Display(next_state + "_BUS_ACKED"),
                NextValue(dat, self.dat_r),
                NextState(next_state),
            )

        for s in statements():
            yield s


class WBRegisterTester(Module):
    def __init__(self, test_addr) -> None:
        self.bus = bus = WBInterface()
        self.submodules.fsm = fsm = FSM("START")
        self.tmp = tmp = Signal(bus.data_width)
        self.tries = tries = Signal(8)

        self.sync += tries.eq(tries + 1)

        magic = 0xDEAD_BEEF

        # fmt: off
        fsm.act("START",
            *TimeoutCheck(tries),
            DisplayOnEnter("START"),
            NextState("WRITE")
        )
        fsm.act("WRITE",
            *TimeoutCheck(tries),
            DisplayOnEnter("WRITE"),
            Display("%0t WRITE tmp: %0x", Time(), tmp),
            *bus.controller_write_hdl(fsm, "READ", test_addr, magic, tries=tries),
        )
        fsm.act("READ",
            *TimeoutCheck(tries),
            DisplayOnEnter("READ"),
            Display("%0t READ tmp: %0x", Time(), tmp),
            *bus.controller_read_hdl(fsm, "READ_CHECK", test_addr, tmp, tries=tries),
        )
        fsm.act("READ_CHECK",
            *TimeoutCheck(tries),
            DisplayOnEnter("READ_CHECK"),
            Display("%0t READ_CHECK tmp: %0x", Time(), tmp),
            *Assert(tmp == magic),
            NextState("WRITE_PLUS_ONE"),
        )
        fsm.act("WRITE_PLUS_ONE",
            *TimeoutCheck(tries),
            DisplayOnEnter("WRITE_PLUS_ONE"),
            *bus.controller_write_hdl(fsm, "READ_PLUS_ONE", test_addr, tmp + 1, tries=tries),
        )
        fsm.act("READ_PLUS_ONE",
            *TimeoutCheck(tries),
            DisplayOnEnter("READ_PLUS_ONE"),
            Display("READ_PLUS_ONE tmp: %0x", tmp),
            *bus.controller_read_hdl(fsm, "READ_PLUS_ONE_CHECK", test_addr, tmp, tries=tries),
        )
        fsm.act("READ_PLUS_ONE_CHECK",
            *TimeoutCheck(tries),
            DisplayOnEnter("READ_PLUS_ONE_CHECK"),
            Display("READ_PLUS_ONE_CHECK tmp: %0x", tmp),
            *Assert(tmp == magic + 1),
            NextState("END"),
        )
        fsm.act("END",
            *TimeoutCheck(tries),
            DisplayOnEnter("END"),
            # Finish()
        )
        # fmt: on

        # rename_migen_fsm(fsm, "wb_test_fsm")


# Bench SoC ----------------------------------------------------------------------------------------


class SimSoC(SoCCore):
    def __init__(
        self,
        sys_clk_freq=None,
        with_analyzer=False,
        with_etherbone=False,
        with_uartbone=False,
        with_dram=False,
        trace=False,
        **kwargs,
    ):
        platform = Platform()
        sys_clk_freq = int(sys_clk_freq)

        self.comb += platform.trace.eq(trace)

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
            eth_pads = self.platform.request("eth")
            self.submodules.ethphy = LiteEthPHYModel(eth_pads)
            self.add_etherbone(phy=self.ethphy, ip_address="192.168.42.50")

        # UARTbone ---------------------------------------------------------------------------------
        if with_uartbone:
            uart_pads = platform.request("uartbone")
            self.submodules.uartbone_phy = uart.RS232PHYModel(uart_pads)
            self.submodules.uartbone = uart.UARTBone(phy=self.uartbone_phy, clk_freq=sys_clk_freq)
            self.bus.add_master(name="uartbone", master=self.uartbone.wishbone)

        # Slow DDR3 --------------------------------------------------------------------------------
        if with_dram:
            ddr3_pads = DDR3PhyInterface()
            self.submodules.ddr = SlowDDR3(self.platform, ddr3_pads, sys_clk_freq, debug=True)
            dram_base = 0x2000_0000
            self.add_memory_region("dram", dram_base, self.ddr.bitsize // 8, type="")
            self.bus.add_slave("dram", self.ddr.bus)
            self.submodules.ddr_model = DDR3Model(self.platform, ddr3_pads)
            # self.register_mem("dram", dram_base, self.ddr.bus, size=self.ddr.bitsize // 8)

        if not with_dram:
            self.submodules.wb_reg32 = WBRegister(32)
            wb_reg32_base = 0x3000_0000
            self.add_memory_region("wb_reg32", wb_reg32_base, 8, type="")
            self.bus.add_slave("wb_reg32", self.wb_reg32.bus)

            # self.submodules.wb_reg16 = WBRegister(16)
            # wb_reg16_base = 0x4000_0000
            # self.add_memory_region("wb_reg16", wb_reg16_base, 8, type="")
            # self.bus.add_slave("wb_reg16", self.wb_reg16.bus)

            self.submodules.wb_reg_tester = WBRegisterTester(wb_reg32_base // 4)
            self.bus.add_master("wb_reg_tester", self.wb_reg_tester.bus)

            self.submodules.sys_clk_counter = Cycles()
            cyc = MonitorArg(self.sys_clk_counter.count, on_change=False)
            for i, kv in enumerate(self.bus.masters.items()):
                k, v = kv
                self.submodules += Monitor(
                    f"%0d M[{i}] {k} adr: %0x cyc: %0b stb: %0b ack: %0b dat_w: %0x dat_r: %0x",
                    cyc,
                    v.adr * 4,
                    v.cyc,
                    v.stb,
                    v.ack,
                    v.dat_w,
                    v.dat_r,
                )
            bus_wb32 = self.wb_reg32.bus
            self.submodules += Monitor(
                "%0d S32 adr: %0x cyc: %0b stb: %0b ack: %0b dat_w: %0x dat_r: %0x q: %0x",
                cyc,
                bus_wb32.adr * 4,
                bus_wb32.cyc,
                bus_wb32.stb,
                bus_wb32.ack,
                bus_wb32.dat_w,
                bus_wb32.dat_r,
                self.wb_reg32.q,
            )
            # self.bus.finalize()
            # decoder_master = self.bus._interconnect.decoder.master
            # decoder_slaves = self.bus._interconnect.decoder.slaves
            # print(decoder_slaves)
            # self.submodules += Monitor(
            #     "%0d DEC M dat_r: %0x ",
            #     cyc,
            #     decoder_master.dat_r,
            # )
            # bus_wb16 = self.wb_reg16.bus
            # self.submodules += Monitor(
            #     "%0d S16 adr: %0x cyc: %0b stb: %0b dat_w: %0x dat_r: %0x ack: %0b q: %0x",
            #     cyc,
            #     bus_wb16.adr * 4,
            #     bus_wb16.cyc,
            #     bus_wb16.stb,
            #     bus_wb16.dat_w,
            #     bus_wb16.dat_r,
            #     bus_wb16.ack,
            #     self.wb_reg16.q,
            # )

        # scope ------------------------------------------------------------------------------------
        if with_analyzer:
            analyzer_signals = []
            if with_dram:
                analyzer_signals += [
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
                    self.bus.slaves["dram"],
                ]
            # analyzer_signals = [phy_pads]
            if not with_dram:
                # rev = reverse_signal(bus_master.adr)
                # self.submodules += Monitor("BR(adr): %0x", rev)
                analyzer_signals += [
                    self.wb_reg32.d,
                    self.wb_reg32.q,
                    self.wb_reg32.a,
                    self.wb_reg32.bus,
                    self.bus.slaves["wb_reg32"],
                    self.wb_reg16.d,
                    self.wb_reg16.q,
                    self.wb_reg16.a,
                    self.wb_reg16.bus,
                    self.bus.slaves["wb_reg16"],
                    bus_master,
                ]
            self.submodules.analyzer = LiteScopeAnalyzer(
                analyzer_signals,
                depth=4096,
                clock_domain="sys",
                csr_csv="analyzer.csv",
            )


#
# Main ---------------------------------------------------------------------------------------------


def sim_args(parser):
    parser.add_argument("--debug-soc-gen", action="store_true", help="Don't run simulation")
    parser.add_argument("--with-analyzer", action="store_true", help="Use litescope")
    parser.add_argument("--with-etherbone", action="store_true", help="Use Etherbone")
    parser.add_argument("--with-uartbone", action="store_true", help="Use UARTbone")
    parser.add_argument(
        "--with-dram", action="store_true", help="Use slowDDR3 controller and Micron model"
    )


def main():
    from litex.soc.integration.soc import LiteXSoCArgumentParser

    parser = LiteXSoCArgumentParser(description="litelitedram sim")
    parser.set_platform(SimPlatform)
    sim_args(parser)
    args = parser.parse_args()

    sys_clk_freq = int(100e6)

    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=sys_clk_freq)
    if args.with_etherbone:
        sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": "192.168.42.100"})
    if args.with_uartbone:
        sim_config.add_module("serial2tcp", "uartbone", args={"port": 2430})

    soc_kwargs = soc_core_argdict(args)

    soc_kwargs["sys_clk_freq"] = sys_clk_freq
    soc_kwargs["cpu_type"] = "None"
    soc_kwargs["with_uart"] = False
    soc_kwargs["ident_version"] = True

    soc = SimSoC(
        with_analyzer=args.with_analyzer,
        with_etherbone=args.with_etherbone,
        with_uartbone=args.with_uartbone,
        with_dram=args.with_dram,
        trace=args.trace,
        **soc_kwargs,
    )

    builder_argdict = parser.builder_argdict
    builder_argdict["csr_csv"] = "csr.csv"
    builder_argdict["output_dir"] = soc.platform.output_dir

    toolchain_argdict = parser.toolchain_argdict
    toolchain_argdict["regular_comb"] = False

    if not args.debug_soc_gen:
        builder = Builder(soc, **builder_argdict)
        for i in range(2):
            build = i == 0
            run = i == 1 and builder.compile_gateware
            builder.build(build=build, run=run, sim_config=sim_config, **toolchain_argdict)


if __name__ == "__main__":
    main()
