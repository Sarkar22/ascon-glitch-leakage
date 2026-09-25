# SPDX-License-Identifier: Apache-2.0
"""Small structural netlist builder over a fixed sky130_fd_sc_hd cell subset.

One Netlist object is written out three ways, so all models describe the same circuit:
  dut.v      structural Verilog (explicit cell instances, optional USE_POWER_PINS)
  dut.sp     SPICE .subckt built from the PDK cell subcircuits + per-net wire caps
  graph.json gate graph for the Python models (cells, pin->net maps, nets, DFFs,
             per-net capacitance estimates and per-instance Liberty delays)
plus ports.json (the port contract with the SPICE runner).

Share domains: every net carries a domain label ("x" unmasked, "s0"/"s1" shares,
"r" fresh randomness). A gate may mix domains only when it is declared as a DOM
cross-domain term (`dom=` argument); anything else raises, so the generator cannot
silently combine shares.

Capacitance estimate per net (pre-layout, documented in ports.json/graph.json):
  wire cap  = WIRE_BASE_FF + WIRE_PER_FANOUT_FF * fanout      (written into dut.sp)
  load cap  = wire cap + Liberty input capacitance of every fanout pin (model weights;
              output ports also get EXT_OUT_LOAD_FF, the load the SPICE runner attaches)
CLK, VPWR and VGND get no wire cap.

Timing (for the level-2 model): input slew of a pin = mean rise/fall output transition
of its driver (ports and CLK: PORT_SLEW_PS); per arc, the Liberty cell_rise/cell_fall at
that slew and the net's load cap, averaged over the timing groups of the related pin.
"""
import json
import re

import pdk

WIRE_BASE_FF = 1.0
WIRE_PER_FANOUT_FF = 0.5
PORT_SLEW_PS = 50.0
EXT_OUT_LOAD_FF = 2.0      # load the SPICE runner puts on each output port (sim/ out_load_fF);
                           # added to the model load cap of output-port nets, not to dut.sp

# cell -> (input pins, output pin, function as a Python expression over 0/1 ints)
CELLS = {
    "inv_1":   (("A",), "Y", "1 ^ A"),
    "and2_1":  (("A", "B"), "X", "A & B"),
    "and2b_1": (("A_N", "B"), "X", "(1 ^ A_N) & B"),
    "xor2_1":  (("A", "B"), "X", "A ^ B"),
    "xnor2_1": (("A", "B"), "Y", "1 ^ A ^ B"),
    "dfxtp_1": (("CLK", "D"), "Q", "D"),          # rising-edge D flip-flop
}
DFF = "dfxtp_1"
POWER_MAP = {"VGND": "VGND", "VNB": "VGND", "VPB": "VPWR", "VPWR": "VPWR"}
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _write(path, text):
    with open(path, "w") as f:
        f.write(text)


def check_cells_against_pdk(lib):
    """Pin names vs the PDK SPICE and Verilog, and our functions vs Liberty's."""
    names = list(CELLS)
    spice = pdk.cell_pins_spice(names)
    vlog = pdk.cell_ports_verilog(names)
    for c, (ins, out, fn) in CELLS.items():
        logical = set(ins) | {out}
        if set(spice[c]) != logical | set(POWER_MAP):
            raise ValueError("SPICE pins of %s: %s" % (c, spice[c]))
        if set(vlog[c]) != logical:
            raise ValueError("Verilog ports of %s: %s" % (c, vlog[c]))
        if c == DFF:
            continue
        lf = lib.cell(c)["pins"][out]["function"]
        if "!(" in lf:
            raise ValueError("unsupported Liberty function %r" % lf)
        pyf = re.sub(r"!([A-Za-z_]\w*)", r"(1 ^ \1)", lf)
        for k in range(1 << len(ins)):
            env = {p: (k >> n) & 1 for n, p in enumerate(ins)}
            if eval(fn, {}, env) != eval(pyf, {}, env):
                raise ValueError("function of %s differs from Liberty %r" % (c, lf))
    return spice


class Netlist:
    def __init__(self, variant, description, latency):
        self.variant = variant
        self.module = "dut_" + variant
        self.description = description
        self.latency = latency
        self.cells = []                 # {"name", "type", "pins": {pin: net}, ...}
        self.inputs, self.outputs = [], []
        self.driver = {}                # net -> cell name, or None for an input port
        self.domain = {}                # net -> domain label

    # ---------------------------------------------------------------- building
    def _new_net(self, net, driver, domain):
        if not _NAME.match(net):
            raise ValueError("bad net name %r" % net)
        if net in self.driver:
            raise ValueError("net %s has two drivers" % net)
        self.driver[net] = driver
        self.domain[net] = domain

    def input(self, name, role, bit, domain):
        self._new_net(name, None, domain)
        self.inputs.append({"name": name, "role": role, "bit": bit})
        return name

    def gate(self, cell, out, dom=None, **pins):
        ins, opin, _ = CELLS[cell]
        if cell == DFF or set(pins) != set(ins):
            raise ValueError("bad pins for %s: %s" % (cell, pins))
        doms = {self.domain[n] for n in pins.values()}
        if dom is None:
            if len(doms) != 1:
                raise ValueError("gate %s mixes domains %s outside DOM" % (out, sorted(doms)))
            dom = doms.pop()
        name = "g_" + out
        self._new_net(out, name, dom)
        self.cells.append({"name": name, "type": cell, "pins": dict(pins, **{opin: out})})
        return out

    def dff(self, d, q):
        name = "ff_" + q
        self._new_net(q, name, self.domain[d])
        self.cells.append({"name": name, "type": DFF, "pins": {"CLK": "CLK", "D": d, "Q": q}})
        return q

    def output(self, name, role, bit, d):
        self.dff(d, name)
        self.outputs.append({"name": name, "role": role, "bit": bit})
        return name

    # ------------------------------------------------------------ analysis
    def nets(self):
        return list(self.driver)

    def fanout(self):
        fo = {n: [] for n in self.driver}
        for c in self.cells:
            ins = CELLS[c["type"]][0]
            for p in ins:
                if p != "CLK":
                    fo[c["pins"][p]].append((c["name"], p))
        return fo

    def comb_order(self):
        """Combinational cells in topological order (sources: ports and DFF outputs)."""
        ready = {n for n, d in self.driver.items() if d is None or d.startswith("ff_")}
        todo = [c for c in self.cells if c["type"] != DFF]
        order = []
        while todo:
            rest = []
            for c in todo:
                ins = CELLS[c["type"]][0]
                if all(c["pins"][p] in ready for p in ins):
                    order.append(c)
                    ready.add(c["pins"][CELLS[c["type"]][1]])
                else:
                    rest.append(c)
            if len(rest) == len(todo):
                raise ValueError("combinational loop or undriven net: %s" % [c["name"] for c in rest])
            todo = rest
        return order

    def validate(self):
        used = {c["pins"][p] for c in self.cells for p in CELLS[c["type"]][0] if p != "CLK"}
        undriven = used - set(self.driver)
        if undriven:
            raise ValueError("undriven nets: %s" % sorted(undriven))
        lower = {}
        for n in self.driver:
            if n.lower() in lower or n.upper() in ("CLK", "VPWR", "VGND"):
                raise ValueError("net name clash: %s" % n)
            lower[n.lower()] = n
        outs = {o["name"] for o in self.outputs}
        fo = self.fanout()
        dangling = [n for n, f in fo.items() if not f and n not in outs]
        if dangling:
            raise ValueError("nets without fanout: %s" % dangling)
        self.comb_order()

    # ------------------------------------------------- capacitance and timing
    def annotate(self, lib):
        """Wire/load caps per net, Liberty delays per cell instance, register timing."""
        fo = self.fanout()
        cellinfo = {c: lib.cell(c) for c in CELLS}
        by_name = {c["name"]: c for c in self.cells}
        self.net_info = {}
        for n in self.driver:
            wire = WIRE_BASE_FF + WIRE_PER_FANOUT_FF * len(fo[n])
            pins = sum(cellinfo[by_name[c]["type"]]["pins"][p]["cap_fF"] for c, p in fo[n])
            if n in {o["name"] for o in self.outputs}:
                pins += EXT_OUT_LOAD_FF
            self.net_info[n] = {"driver": self.driver[n], "domain": self.domain[n],
                                "fanout": [list(x) for x in fo[n]],
                                "wire_cap_fF": round(wire, 4), "load_cap_fF": round(wire + pins, 4)}
        slew = {n: PORT_SLEW_PS for n, d in self.driver.items() if d is None}
        slew["CLK"] = PORT_SLEW_PS
        dffs = [c for c in self.cells if c["type"] == DFF]
        for c in dffs + self.comb_order():
            ins, opin, _ = CELLS[c["type"]]
            out = c["pins"][opin]
            load = self.net_info[out]["load_cap_fF"]
            c["delay_ps"] = {}
            rs, fs = [], []
            for p in (["CLK"] if c["type"] == DFF else ins):
                d = lib.arc_delays(cellinfo[c["type"]], opin, slew[c["pins"][p]], load)[p]
                c["delay_ps"][p] = {"rise": round(d["rise"], 2), "fall": round(d["fall"], 2)}
                rs.append(d["rise_slew"])
                fs.append(d["fall_slew"])
            slew[out] = 0.5 * (max(rs) + max(fs))
            self.net_info[out]["slew_ps"] = round(slew[out], 2)
        # static timing: latest settle time of every net after the clock edge (ports: t=0)
        arr = {n: 0.0 for n, d in self.driver.items() if d is None}
        for c in dffs:
            arr[c["pins"]["Q"]] = max(c["delay_ps"]["CLK"].values())
        for c in self.comb_order():
            ins, opin, _ = CELLS[c["type"]]
            arr[c["pins"][opin]] = max(arr[c["pins"][p]] + max(c["delay_ps"][p].values()) for p in ins)
        from_reg = self._arrival_from(arr, lambda n: self.driver[n] is not None)
        from_port = self._arrival_from(arr, lambda n: self.driver[n] is None)
        self.timing = {"reg_to_reg_ps": round(from_reg, 1), "port_to_reg_ps": round(from_port, 1)}
        self.area_um2 = round(sum(cellinfo[c["type"]]["area_um2"] for c in self.cells), 3)

    def _arrival_from(self, arr, source_ok):
        """Max arrival at DFF D pins over paths that start at sources accepted by source_ok."""
        reach = {}
        for n, d in self.driver.items():
            if d is None or d.startswith("ff_"):
                reach[n] = arr[n] if source_ok(n) else None
        for c in self.comb_order():
            ins, opin, _ = CELLS[c["type"]]
            cand = [reach[c["pins"][p]] + max(c["delay_ps"][p].values())
                    for p in ins if reach[c["pins"][p]] is not None]
            reach[c["pins"][opin]] = max(cand) if cand else None
        ends = [reach[c["pins"]["D"]] for c in self.cells if c["type"] == DFF]
        ends = [e for e in ends if e is not None]
        return max(ends) if ends else 0.0

    # --------------------------------------------------------------- writers
    def port_list(self):
        return ["CLK"] + [p["name"] for p in self.inputs] + [p["name"] for p in self.outputs] + ["VPWR", "VGND"]

    def write_verilog(self, path):
        ins = [p["name"] for p in self.inputs]
        outs = [p["name"] for p in self.outputs]
        wires = [n for n in self.driver if self.driver[n] is not None and n not in outs]
        L = ["// SPDX-License-Identifier: Apache-2.0",
             "// %s: %s" % (self.module, self.description),
             "// Generated by gen/make_variants.py from explicit sky130_fd_sc_hd cells; do not edit.",
             "`default_nettype none", "module %s (" % self.module, "    input  wire CLK,"]
        L += ["    input  wire %s," % n for n in ins]
        L += ["    output wire %s%s" % (n, "," if k < len(outs) - 1 else "") for k, n in enumerate(outs)]
        L += ["`ifdef USE_POWER_PINS", "    , inout wire VPWR", "    , inout wire VGND", "`endif", ");"]
        L += ["    wire %s;" % n for n in wires]
        for c in self.cells:
            conns = ", ".join(".%s(%s)" % (p, n) for p, n in c["pins"].items())
            L += ["    %s__%s %s (" % (pdk.LIB, c["type"], c["name"]),
                  "`ifdef USE_POWER_PINS", "        .VPWR(VPWR), .VGND(VGND), .VPB(VPWR), .VNB(VGND),", "`endif",
                  "        %s);" % conns]
        L += ["endmodule", "`default_nettype wire", ""]
        _write(path, "\n".join(L))

    def write_spice(self, path, spice_pins):
        ports = self.port_list()
        L = ["* SPDX-License-Identifier: Apache-2.0",
             "* %s: %s" % (self.module, self.description),
             "* Generated by gen/make_variants.py; do not edit. Needs in the top deck:",
             "*   .lib <PDK>/libs.tech/ngspice/sky130.lib.spice tt",
             "*   .include <PDK>/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice",
             "* Cells: VNB tied to VGND, VPB to VPWR. Pre-layout wire caps to VGND:",
             "*   C = %.2f fF + %.2f fF per fanout pin, on every net except CLK/VPWR/VGND."
             % (WIRE_BASE_FF, WIRE_PER_FANOUT_FF),
             ".subckt %s %s" % (self.module, " ".join(ports[:8]))]
        for k in range(8, len(ports), 8):
            L.append("+ " + " ".join(ports[k:k + 8]))
        for c in self.cells:
            pins = [POWER_MAP.get(p) or c["pins"][p] for p in spice_pins[c["type"]]]
            L.append("X%s %s %s__%s" % (c["name"], " ".join(pins), pdk.LIB, c["type"]))
        for n in self.driver:
            L.append("Cw_%s %s VGND %.3ff" % (n, n, self.net_info[n]["wire_cap_fF"]))
        L += [".ends %s" % self.module, ""]
        _write(path, "\n".join(L))

    def write_ports(self, path):
        n_dff = sum(c["type"] == DFF for c in self.cells)
        d = {"variant": self.variant, "subckt": self.module, "ports": self.port_list(),
             "inputs": self.inputs, "outputs": self.outputs, "latency": self.latency,
             "n_cells": len(self.cells), "n_dff": n_dff, "wire_cap_fF": WIRE_BASE_FF,
             "wire_cap_per_fanout_fF": WIRE_PER_FANOUT_FF,
             "wire_cap_note": "per net: %.2f fF + %.2f fF x fanout pins, to VGND (all nets except CLK, VPWR, VGND)"
                              % (WIRE_BASE_FF, WIRE_PER_FANOUT_FF),
             "reg_to_reg_ps": self.timing["reg_to_reg_ps"], "port_to_reg_ps": self.timing["port_to_reg_ps"],
             "area_um2": self.area_um2, "description": self.description}
        _write(path, json.dumps(d, indent=1))

    def write_graph(self, path):
        d = {"variant": self.variant, "module": self.module, "description": self.description,
             "latency": self.latency, "clock": "CLK", "inputs": self.inputs, "outputs": self.outputs,
             "cell_types": {"%s__%s" % (pdk.LIB, c): {"inputs": list(v[0]), "output": v[1], "function": v[2],
                                                     "sequential": c == DFF} for c, v in CELLS.items()},
             "cells": [dict(c, type="%s__%s" % (pdk.LIB, c["type"])) for c in self.cells],
             "nets": self.net_info,
             "dffs": [c["name"] for c in self.cells if c["type"] == DFF],
             "wire_cap": {"base_fF": WIRE_BASE_FF, "per_fanout_fF": WIRE_PER_FANOUT_FF,
                          "output_port_ext_load_fF": EXT_OUT_LOAD_FF},
             "timing": dict(self.timing, liberty=pdk.LIB + "__tt_025C_1v80", port_and_clk_slew_ps=PORT_SLEW_PS,
                            method="per arc: Liberty cell_rise/cell_fall at the driver's output slew and the "
                                   "net load cap, averaged over the timing groups of the related pin"),
             "area_um2": self.area_um2}
        _write(path, json.dumps(d, indent=1))
