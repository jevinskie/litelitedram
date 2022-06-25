import os
import subprocess
from enum import IntEnum

from migen import *


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


class SlowDDR3(Module):
    def __init__(self, platform, pads, sys_clk_freq, debug=False):
        self.platform = platform
        self.pads = pads
        self.sys_clk_freq = sys_clk_freq
        self.debug = debug

        rd_valid = Signal()
        rd_ready = Signal()
        rd_data = Signal(16)
        wr_valid = Signal()
        wr_ready = Signal()
        wr_data = Signal(16)
        addr = Signal(27)
        initfin = Signal()
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
            o_sysIO_dataRd_valid=rd_valid,
            i_sysIO_dataRd_ready=rd_ready,
            o_sysIO_dataRd_payload=rd_data,
            i_sysIO_dataWr_valid=wr_valid,
            o_sysIO_dataWr_ready=wr_ready,
            i_sysIO_dataWr_payload=wr_data,
            i_sysIO_address=addr,
            o_sysIO_initFin=initfin,
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

    def do_finalize(self):
        verilog_dir = os.path.join(self.platform.output_dir, "gateware")
        verilog_filename = os.path.join(verilog_dir, "slowDDR3.v")
        sbt_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "3rdparty", "General-Slow-DDR3-Interface")
        )
        dbg = ""
        if self.debug:
            dbg = " --debug true"
        subprocess.check_call(
            [
                "sbt",
                f"run --odir {verilog_dir} --sys-clk {self.sys_clk_freq} --tristate true" + dbg,
            ],
            cwd=sbt_dir,
        )
        self.platform.add_source(verilog_filename)
