# SPDX-License-Identifier: Apache-2.0
"""sky130 PDK access for the netlist generator: paths, cell pin orders, Liberty data.

The PDK root comes from the environment variable PDK, else from ~/.ciel/sky130A
(resolved at run time; no path is stored in generated files).

  cell_pins_spice(cell)    pin order of the cell's .subckt line in the cell SPICE file
  cell_ports_verilog(cell) port names of the cell's module in the Verilog models
  Liberty(path).cell(c)    pin capacitances and NLDM timing tables of one cell

Units returned by this module: time in ps, capacitance in fF.
"""
import os
import re

LIB = "sky130_fd_sc_hd"


def pdk_root():
    root = os.environ.get("PDK") or os.path.realpath(os.path.expanduser("~/.ciel/sky130A"))
    if not os.path.isdir(os.path.join(root, "libs.ref", LIB)):
        raise FileNotFoundError("sky130A PDK not found; set PDK (tried %s)" % root)
    return root


def paths(root=None):
    root = root or pdk_root()
    ref = os.path.join(root, "libs.ref", LIB)
    return {
        "models": os.path.join(root, "libs.tech", "ngspice", "sky130.lib.spice"),
        "cells_spice": os.path.join(ref, "spice", LIB + ".spice"),
        "liberty": os.path.join(ref, "lib", LIB + "__tt_025C_1v80.lib"),
        "verilog_primitives": os.path.join(ref, "verilog", "primitives.v"),
        "verilog_cells": os.path.join(ref, "verilog", LIB + ".v"),
    }


def cell_pins_spice(cells, path=None):
    """{cell: [pins in .subckt order]} read from the PDK cell SPICE file."""
    path = path or paths()["cells_spice"]
    want = {LIB + "__" + c: c for c in cells}
    found = {}
    with open(path) as f:
        for line in f:
            if line.lower().startswith(".subckt"):
                tok = line.split()
                if tok[1] in want:
                    found[want[tok[1]]] = tok[2:]
    missing = set(cells) - set(found)
    if missing:
        raise KeyError("cells not in %s: %s" % (path, sorted(missing)))
    return found


def cell_ports_verilog(cells, path=None):
    """{cell: [ports]} of the modules without power pins in the PDK Verilog models."""
    path = path or paths()["verilog_cells"]
    with open(path) as f:
        text = f.read()
    out = {}
    for c in cells:
        # the first definition of each module is the USE_POWER_PINS one; take the last
        mods = re.findall(r"module\s+%s__%s\s*\((.*?)\);" % (LIB, re.escape(c)), text, re.S)
        if not mods:
            raise KeyError("module %s__%s not found in %s" % (LIB, c, path))
        out[c] = [p.strip() for p in mods[-1].split(",")]
    return out


# ------------------------------------------------------------------- Liberty ---
_TOK = re.compile(r'"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_.\[\]]*|-?[0-9.]+(?:[eE][-+]?[0-9]+)?|[(){}:;,]')


def _parse(tokens, i):
    """Parse statements until a closing brace; return (list of statements, index)."""
    stmts = []
    while i < len(tokens) and tokens[i] != "}":
        name = tokens[i]
        i += 1
        if tokens[i] == ":":
            j = tokens.index(";", i)
            stmts.append(("attr", name, " ".join(tokens[i + 1:j]).strip('"')))
            i = j + 1
        elif tokens[i] == "(":
            j = tokens.index(")", i)
            args = [a.strip('"') for a in tokens[i + 1:j] if a != ","]
            i = j + 1
            if i < len(tokens) and tokens[i] == "{":
                body, i = _parse(tokens, i + 1)
                stmts.append(("group", name, args, body))
                i += 1                      # skip "}"
            else:
                stmts.append(("complex", name, args))
                if i < len(tokens) and tokens[i] == ";":
                    i += 1
        else:
            raise ValueError("Liberty parse error near %r" % tokens[i - 1:i + 3])
    return stmts, i


_NLDM = ("cell_rise", "cell_fall", "rise_transition", "fall_transition")


def _table(group):
    """NLDM table group -> (index_1, index_2, values) as lists of floats."""
    d = {s[1]: s[2] for s in group[3] if s[0] == "complex"}
    idx1 = [float(v) for v in d["index_1"][0].split(",")]
    idx2 = [float(v) for v in d["index_2"][0].split(",")]
    rows = [[float(v) for v in r.split(",")] for r in d["values"]]
    return idx1, idx2, rows


def interp2(table, x, y):
    """Bilinear interpolation (linear extrapolation outside the table)."""
    idx1, idx2, rows = table

    def seg(axis, v):
        k = 0
        while k < len(axis) - 2 and v > axis[k + 1]:
            k += 1
        return k, (v - axis[k]) / (axis[k + 1] - axis[k])
    i, fx = seg(idx1, x)
    j, fy = seg(idx2, y)
    a = rows[i][j] + (rows[i][j + 1] - rows[i][j]) * fy
    b = rows[i + 1][j] + (rows[i + 1][j + 1] - rows[i + 1][j]) * fy
    return a + (b - a) * fx


class Liberty:
    """Reads the few cells we need from a Liberty file (time ns -> ps, cap pF -> fF)."""

    def __init__(self, path=None):
        self.path = path or paths()["liberty"]
        with open(self.path) as f:
            self.text = f.read()
        head = self.text[:20000]
        assert 'time_unit : "1ns"' in head and 'capacitive_load_unit(1.0000000000, "pf")' in head

    def cell(self, name):
        full = "%s__%s" % (LIB, name)
        start = self.text.find('cell ("%s")' % full)
        if start < 0:
            raise KeyError(full)
        depth, i = 0, self.text.index("{", start)
        for k in range(i, len(self.text)):
            c = self.text[k]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
        tokens = _TOK.findall(self.text[i + 1:k].replace("\\\n", " "))
        body, _ = _parse(tokens, 0)
        pins = {}
        for s in body:
            if s[0] == "group" and s[1] == "pin":
                attrs = {t[1]: t[2] for t in s[3] if t[0] == "attr"}
                timing = []
                for t in s[3]:
                    if t[0] == "group" and t[1] == "timing":
                        ta = {u[1]: u[2] for u in t[3] if u[0] == "attr"}
                        tabs = {u[1]: _table(u) for u in t[3] if u[0] == "group" and u[1] in _NLDM}
                        if ta.get("timing_type", "combinational") in ("combinational", "rising_edge"):
                            timing.append({"related_pin": ta["related_pin"],
                                           "sense": ta.get("timing_sense", ""),
                                           "type": ta.get("timing_type", "combinational"),
                                           "tables": tabs})
                pins[s[2][0]] = {"direction": attrs.get("direction"),
                                 "cap_fF": float(attrs.get("capacitance", 0.0)) * 1000.0,
                                 "function": attrs.get("function"),
                                 "timing": timing}
        area = [float(s[2]) for s in body if s[0] == "attr" and s[1] == "area"]
        return {"name": full, "pins": pins, "area_um2": area[0]}

    def arc_delays(self, cell, out_pin, slew_ps, load_fF):
        """{related_pin: {"rise": ps, "fall": ps, "rise_slew": ps, "fall_slew": ps}}.

        Output-edge delays and transitions, each averaged over all timing groups of the
        related pin (e.g. the positive- and negative-unate arcs of an XOR), at one input
        transition and one output load."""
        c = self.cell(cell) if isinstance(cell, str) else cell
        out = {}
        for t in c["pins"][out_pin]["timing"]:
            d = out.setdefault(t["related_pin"], {"rise": [], "fall": [], "rise_slew": [], "fall_slew": []})
            for key, tab in (("rise", "cell_rise"), ("fall", "cell_fall"),
                             ("rise_slew", "rise_transition"), ("fall_slew", "fall_transition")):
                d[key].append(1000.0 * interp2(t["tables"][tab], slew_ps / 1000.0, load_fF / 1000.0))
        return {p: {k: sum(v) / len(v) for k, v in d.items()} for p, d in out.items()}
