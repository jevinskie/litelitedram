import os
import subprocess
from enum import IntEnum
from math import ceil, log2

from litex.soc.interconnect import wishbone
from migen import *
from migen.genlib.record import DIR_M_TO_S, DIR_S_TO_M

_kbit = 1024
_mbit = _kbit * 1024
_gbit = _mbit * 1024


class InitState(IntEnum):
    WAIT0 = 0
    CKE = 1
    MRS2 = 2
    MRS3 = 3
    MRS1 = 4
    MRS0 = 5
    ZQCL = 6
    WAIT1 = 7


class WorkState(IntEnum):
    IDLE = 0
    READ = 1
    WRITE = 2
    REFRESH = 3


class SlowDDR3SysInterface(Record):
    def __init__(self, width, bitsize):
        super().__init__(
            [
                ("rd_valid", 1, DIR_S_TO_M),
                ("rd_ready", 1, DIR_M_TO_S),
                ("rd_data", width, DIR_S_TO_M),
                ("wr_valid", 1, DIR_M_TO_S),
                ("wr_ready", 1, DIR_S_TO_M),
                ("wr_data", width, DIR_M_TO_S),
                ("addr", ceil(log2(bitsize // width)), DIR_M_TO_S),
                ("sel", width // 8, DIR_M_TO_S),
                ("initfin", 1, DIR_S_TO_M),
            ]
        )


class SlowDDR3(Module):
    def __init__(self, platform, pads, sys_clk_freq, width=16, bitsize=2 * _gbit, debug=False):
        self.platform = platform
        self.pads = pads
        self.sys_clk_freq = sys_clk_freq
        self.debug = debug
        self.width = width
        assert width == 16
        self.bitsize = bitsize
        assert bitsize == 2 * _gbit

        self.sysio = sysio = SlowDDR3SysInterface(width, bitsize)

        # wishbone
        self.bus = bus = wishbone.Interface(width, len(sysio.addr))
        wb_valid = Signal()
        self.comb += [
            wb_valid.eq(bus.cyc & bus.stb),
            If(
                wb_valid,
                bus.adr.eq(sysio.addr),
                If(
                    bus.we,
                    bus.dat_w.eq(sysio.wr_data),
                    sysio.sel.eq(bus.sel),
                    bus.ack.eq(sysio.wr_ready),
                    sysio.wr_valid.eq(1),
                ).Else(
                    bus.dat_r.eq(sysio.rd_data),
                    bus.ack.eq(sysio.rd_ready),
                    sysio.rd_ready.eq(1),
                ),
            ),
        ]

        if debug:
            self.init_state = Signal(3)
            self.work_state = Signal(2)
            self.refresh_cnt = Signal(4)
            self.refresh_issued = Signal()

        cs, cas, ras, we = [Signal() for i in range(4)]
        self.comb += [
            pads.cs_n.eq(~cs),
            pads.cas_n.eq(~cas),
            pads.ras_n.eq(~ras),
            pads.we_n.eq(~we),
        ]
        dq = TSTriple(16)
        dqs_p = TSTriple(2)
        dqs_n = TSTriple(2)
        self.specials += dq.get_tristate(pads.dq)
        self.specials += dqs_p.get_tristate(pads.dqs_p)
        self.specials += dqs_n.get_tristate(pads.dqs_n)

        ports = dict(
            i_clk=ClockSignal(),
            i_inv_clk=~ClockSignal(),
            i_resetn=~ResetSignal(),
            o_phyIO_address=pads.a,
            o_phyIO_bank=pads.ba,
            o_phyIO_cs=cs,
            o_phyIO_cas=cas,
            o_phyIO_ras=ras,
            o_phyIO_we=we,
            o_phyIO_clk_p=pads.clk_p,
            o_phyIO_clk_n=pads.clk_n,
            o_phyIO_cke=pads.cke,
            o_phyIO_odt=pads.odt,
            o_phyIO_rst_n=pads.reset_n,
            o_phyIO_dm=pads.dm,
            i_phyIO_dq_i=dq.i,
            o_phyIO_dq_o=dq.o,
            o_phyIO_dq_oe=dq.oe,
            i_phyIO_dqs_p_i=dqs_p.i,
            o_phyIO_dqs_p_o=dqs_p.o,
            o_phyIO_dqs_p_oe=dqs_p.oe,
            i_phyIO_dqs_n_i=dqs_n.i,
            o_phyIO_dqs_n_o=dqs_n.o,
            o_phyIO_dqs_n_oe=dqs_n.oe,
            o_sysIO_dataRd_valid=sysio.rd_valid,
            i_sysIO_dataRd_ready=sysio.rd_ready,
            o_sysIO_dataRd_payload=sysio.rd_data,
            i_sysIO_dataWr_valid=sysio.wr_valid,
            o_sysIO_dataWr_ready=sysio.wr_ready,
            i_sysIO_dataWr_payload=sysio.wr_data,
            i_sysIO_address=sysio.addr,
            i_sysIO_sel=sysio.sel,
            o_sysIO_initFin=sysio.initfin,
        )
        if debug:
            ports.update(
                dict(
                    o_phyIO_init_state=self.init_state,
                    o_phyIO_work_state=self.work_state,
                    o_phyIO_refresh_cnt=self.refresh_cnt,
                    o_phyIO_refresh_issued=self.refresh_issued,
                )
            )

        self.specials += Instance("slowDDR3", name="slowDDR3_ctlr", **ports)

    @staticmethod
    def _needs_rebuild(target, dependencies):
        if not os.path.exists(target):
            return True
        tgt_mtime = os.path.getmtime(target)
        for dep in dependencies:
            if os.path.getmtime(dep) > tgt_mtime:
                return True
        return False

    def do_finalize(self):
        verilog_dir = os.path.join(self.platform.output_dir, "gateware")
        verilog_file = f"slowDDR3_{self.sys_clk_freq}_clk.v"
        verilog_path = os.path.join(verilog_dir, verilog_file)
        sbt_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "3rdparty", "General-Slow-DDR3-Interface")
        )
        scala_file = os.path.join(sbt_dir, "slowDDR3.scala")
        dbg = ""
        if self.debug:
            dbg = " --debug true"

        if self._needs_rebuild(verilog_path, [scala_file]):
            subprocess.check_call(
                [
                    "sbt",
                    f"run --odir {verilog_dir} --filename {verilog_file} --sys-clk {self.sys_clk_freq} --tristate true"
                    + dbg,
                ],
                cwd=sbt_dir,
            )
        self.platform.add_source(verilog_path)
