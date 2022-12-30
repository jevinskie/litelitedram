#!/usr/bin/env python3

# Copyright (c) 2022 Jevin Sweval <jevinsweval@gmail.com>
# SPDX-License-Identifier: BSD-2-Clause

from litex.build.generic_platform import *
from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig
from litex.gen.fhdl.sim import *
from litex.soc.integration.builder import *
from litex.soc.integration.soc_core import *
from migen import *
from rich import print

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk / Rst.
    ("sys_clk", 0, Pins(1)),
    ("sys_rst", 0, Pins(1)),
]


class Example(Module):
    def __init__(self):
        # self.clock_domains += ClockDomain("sys")
        self.s = Signal()
        self.counterz = Signal(8)
        x = Array(Signal(name="a") for i in range(7))

        self.submodules.myfsm = myfsm = FSM()

        myfsm.act("FOO", Display("FOO norm"), self.s.eq(1), NextState("BAR"))
        myfsm.act(
            "BAR",
            Display("BAR norm"),
            self.s.eq(0),
            NextValue(self.counterz, self.counterz + 1),
            NextValue(x[self.counterz], 89),
            NextState("FOO"),
        )

        self.be = myfsm.before_entering("FOO")
        self.ae = myfsm.after_entering("FOO")
        self.bl = myfsm.before_leaving("FOO")
        self.al = myfsm.after_leaving("FOO")


# Bench SoC ----------------------------------------------------------------------------------------


class Platform(SimPlatform):
    def __init__(self):
        super().__init__(self, _io, name="barefsmsim")


class SimSoC(SoCCore):
    def __init__(
        self,
        sys_clk_freq=None,
        **kwargs,
    ):
        platform = Platform()
        sys_clk_freq = int(sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCMini.__init__(
            self,
            platform,
            clk_freq=sys_clk_freq,
            ident="litelitedram sim",
            **kwargs,
        )

        self.submodules.example = Example()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))


#
# Main ---------------------------------------------------------------------------------------------


def main():
    from litex.soc.integration.soc import LiteXSoCArgumentParser

    parser = LiteXSoCArgumentParser(description="litelitedram sim")
    parser.set_platform(SimPlatform)
    args = parser.parse_args()

    sys_clk_freq = int(100e6)

    sim_config = SimConfig()
    sim_config.add_clocker("sys_clk", freq_hz=sys_clk_freq)
    soc_kwargs = soc_core_argdict(args)
    soc_kwargs["sys_clk_freq"] = sys_clk_freq
    soc_kwargs["cpu_type"] = "None"
    soc_kwargs["with_uart"] = False
    soc_kwargs["ident_version"] = False

    soc = SimSoC(**soc_kwargs)

    builder_argdict = parser.builder_argdict

    builder = Builder(soc, **builder_argdict)
    builder.build(build=True, run=False, sim_config=sim_config, **parser.toolchain_argdict)


if __name__ == "__main__":
    main()
