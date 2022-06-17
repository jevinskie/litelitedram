import os
import subprocess

from migen import *


class SlowDDR3(Module):
    def __init__(self, pads):
        self.pads = pads

    def do_finalize(self):
        verilog_filename = os.path.join(self.platform.output_dir, "gateware", "slowDDR3.v")
        sbt_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        subprocess.check_call(["sbt", f"run --odir {sbt_dir} --tristate true"], cwd=sbt_dir)
        bulk_streamer.USBBulkStreamerDevice.emit_verilog(
            verilog_filename,
            with_utmi=self.with_utmi,
            with_blinky=self.with_blinky,
            with_utmi_la=self.with_utmi_la,
            data_clock=self.data_clock,
        )
        self.platform.add_source(verilog_filename)
