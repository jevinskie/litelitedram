import subprocess
from pathlib import Path

from migen import *
from migen.genlib.record import DIR_M_TO_S, DIR_NONE


class DDR3PhyInterface(Record):
    def __init__(self, row_width=14, dq_width=16):
        super().__init__(
            [
                ("a", row_width, DIR_M_TO_S),
                ("ba", 3, DIR_M_TO_S),
                ("ras_n", 1, DIR_M_TO_S),
                ("cas_n", 1, DIR_M_TO_S),
                ("we_n", 1, DIR_M_TO_S),
                ("dm", dq_width // 8, DIR_M_TO_S),
                ("dq", dq_width, DIR_NONE),
                ("dqs_p", dq_width // 8, DIR_NONE),
                ("dqs_n", dq_width // 8, DIR_NONE),
                ("clk_p", 1, DIR_M_TO_S),
                ("clk_n", 1, DIR_M_TO_S),
                ("cs_n", 1, DIR_M_TO_S),
                ("cke", 1, DIR_M_TO_S),
                ("odt", 1, DIR_M_TO_S),
                ("reset_n", 1, DIR_M_TO_S),
            ]
        )


class DDR3ModelInterface(Record):
    def __init__(self, row_width, dq_width):
        super().__init__(
            [
                ("addr", row_width, DIR_M_TO_S),
                ("ba", 3, DIR_M_TO_S),
                ("ras_n", 1, DIR_M_TO_S),
                ("cas_n", 1, DIR_M_TO_S),
                ("we_n", 1, DIR_M_TO_S),
                ("dm_tdqs", dq_width // 8, DIR_M_TO_S),
                ("dq", dq_width, DIR_NONE),
                ("dqs", dq_width // 8, DIR_NONE),
                ("dqs_n", dq_width // 8, DIR_NONE),
                ("ck", 1, DIR_M_TO_S),
                ("ck_n", 1, DIR_M_TO_S),
                ("cs_n", 1, DIR_M_TO_S),
                ("cke", 1, DIR_M_TO_S),
                ("odt", 1, DIR_M_TO_S),
                ("rst_n", 1, DIR_M_TO_S),
            ]
        )


class DDR3Model(Module):
    def __init__(self, platform, pads):
        self.platform = platform
        ports = dict(
            o_addr=pads.a,
            o_ba=pads.ba,
            o_ras_n=pads.ras_n,
            o_cas_n=pads.cas_n,
            o_we_n=pads.we_n,
            io_dm_tdqs=pads.dm,
            io_dq=pads.dq,
            io_dqs=pads.dqs_p,
            io_dqs_n=pads.dqs_n,
            o_ck=pads.clk_p,
            o_ck_n=pads.clk_n,
            o_cs_n=pads.cs_n,
            o_cke=pads.cke,
            o_odt=pads.odt,
            o_rst_n=pads.reset_n,
        )
        self.specials += Instance("ddr3", name="ddr3_model", **ports)

    def do_finalize(self):
        slowddr3_dir = (
            Path(__file__).parent.parent / "3rdparty" / "General-Slow-DDR3-Interface"
        ).resolve()
        ddr3_model_dir = slowddr3_dir / "model"
        ddr3_model_file = ddr3_model_dir / "ddr3.v"
        subprocess.check_call(["make", "model/ddr3.v"], cwd=slowddr3_dir)
        self.platform.add_verilog_include_path(ddr3_model_dir)
        for d in ("sg25", "x16", "den2048Mb"):
            self.platform.add_compiler_definition(d)
        self.platform.add_source(ddr3_model_file, language="verilog")
