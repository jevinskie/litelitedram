import os
import subprocess

from migen import *


class SlowDDR3(Module):
    def __init__(self, platform, pads, sys_clk_freq):
        self.platform = platform
        self.pads = pads
        self.sys_clk_freq = sys_clk_freq

        rd_valid = Signal()
        rd_ready = Signal()
        rd_data = Signal(16)
        wr_valid = Signal()
        wr_ready = Signal()
        wr_data = Signal(16)
        addr = Signal(27)
        initfin = Signal()

        self.specials += Instance(
            "slowDDR3",
            i_clk=ClockSignal(),
            i_inv_clk=~ClockSignal(),
            i_resetn=~ResetSignal(),
            o_phyIO_address=pads.a,
            o_phyIO_bank=pads.ba,
            o_phyIO_cs=~pads.cs_n,
            o_phyIO_cas=~pads.cas_n,
            o_phyIO_ras=~pads.ras_n,
            o_phyIO_we=~pads.we_n,
            o_phyIO_clk_p=pads.clk_p,
            o_phyIO_clk_n=pads.clk_n,
            o_phyIO_cke=pads.cke,
            o_phyIO_odt=pads.odt,
            o_phyIO_rst_n=pads.reset_n,
            o_phyIO_dm=pads.dm,
            o_sysIO_dataRd_valid=rd_valid,
            i_sysIO_dataRd_ready=rd_ready,
            o_sysIO_dataRd_payload=rd_data,
            i_sysIO_dataWr_valid=wr_valid,
            o_sysIO_dataWr_ready=wr_ready,
            i_sysIO_dataWr_payload=wr_data,
            i_sysIO_address=addr,
            o_sysIO_initFin=initfin,
            name="slowDDR3_ctlr",
        )

    def do_finalize(self):
        verilog_dir = os.path.join(self.platform.output_dir, "gateware")
        verilog_filename = os.path.join(verilog_dir, "slowDDR3.v")
        sbt_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "3rdparty", "General-Slow-DDR3-Interface")
        )
        subprocess.check_call(
            ["sbt", f"run --odir {verilog_dir} --sys-clk {self.sys_clk_freq} --tristate true"],
            cwd=sbt_dir,
        )
        self.platform.add_source(verilog_filename)
