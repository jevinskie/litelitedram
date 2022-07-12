import os
import subprocess
from enum import IntEnum
from math import ceil, log2

from litex.soc.interconnect import wishbone
from migen import *
from migen.genlib.record import DIR_M_TO_S, DIR_NONE


class DDR3ModelInterface(Record):
    def __init__(self, row_width, dq_width):
        super().__init__(
            [
                ("address", row_width, DIR_M_TO_S),
                ("bank", 3, DIR_M_TO_S),
                ("cs", 1, DIR_M_TO_S),
                ("cas", 1, DIR_M_TO_S),
                ("ras", 1, DIR_M_TO_S),
                ("we", 1, DIR_M_TO_S),
                ("clk_p", 1, DIR_M_TO_S),
                ("cke", 1, DIR_M_TO_S),
                ("odt", 1, DIR_M_TO_S),
                ("rst_n", 1, DIR_M_TO_S),
                ("cs", 1, DIR_M_TO_S),
                ("dm", dq_width // 8, DIR_M_TO_S),
                ("dq", dq_width, DIR_NONE),
                ("dqs_p", dq_width // 8, DIR_NONE),
                ("dqs_n", dq_width // 8, DIR_NONE),
            ]
        )


class DDR3Model(Module):
    def __init__(self, platform):
        self.platform = platform
        ports = {}
        self.specials += Instance("ddr3", name="ddr3_model", **ports)

    def do_finalize(self):
        model_dir = os.path.join(self.platform.output_dir, "gateware")
        verilog_filename = os.path.join(verilog_dir, "slowDDR3.v")
        slowddr3_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "3rdparty", "General-Slow-DDR3-Interface")
        )
        ddr3_model_file = os.path.join(slowddr3_dir, "model", "ddr3.v")
        subprocess.check_call(["make" "model/ddr3.v"], cwd=slowddr3_dir)
        self.platform.add_source(ddr3_model_file)
        self.platform
