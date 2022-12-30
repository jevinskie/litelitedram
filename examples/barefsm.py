#!/usr/bin/env python3

from litex.soc.integration.builder import *
from litex.soc.integration.soc_core import *
from litex_boards.platforms import digilent_arty
from migen import *


class Example(Module):
    def __init__(self):
        self.clock_domains += ClockDomain("sys")
        self.s = Signal()
        self.counter = Signal(8)
        x = Array(Signal(name="a") for i in range(7))

        myfsm = FSM()
        self.submodules += myfsm

        myfsm.act("FOO", Display("FOO norm"), self.s.eq(1), NextState("BAR"))
        myfsm.act(
            "BAR",
            Display("BAR norm"),
            self.s.eq(0),
            NextValue(self.counter, self.counter + 1),
            NextValue(x[self.counter], 89),
            NextState("FOO"),
        )

        self.be = myfsm.before_entering("FOO")
        self.ae = myfsm.after_entering("FOO")
        self.bl = myfsm.before_leaving("FOO")
        self.al = myfsm.after_leaving("FOO")


class BareSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(50e6)):
        platform = digilent_arty.Platform()

        # SoCMini ----------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=100_000_000, ident="bare", ident_version=False)

        self.submodules.example = Example()


def main():
    soc = BareSoC()
    builder = Builder(soc)
    builder.build(run=False)


if __name__ == "__main__":
    main()
