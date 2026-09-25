# SPDX-License-Identifier: Apache-2.0
"""Unit tests of sim/spice_campaign.py (stdlib unittest).

The ngspice test simulates a 3-cell DUT (flip-flop -> inverter -> flip-flop) for 8 rows and
needs ngspice and the PDK, i.e. the docker image; it is skipped elsewhere. Runtime ~20 s:
  bash sim/docker_run.sh python3 -m unittest discover -s sim -p 'test_*.py' -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spice_campaign as sc  # noqa: E402

TINY_SP = """.subckt dut_T CLK a y VPWR VGND
Xff1 CLK a VGND VGND VPWR VPWR q sky130_fd_sc_hd__dfxtp_1
Xinv q VGND VGND VPWR VPWR nq sky130_fd_sc_hd__inv_1
Xff2 CLK nq VGND VGND VPWR VPWR y sky130_fd_sc_hd__dfxtp_1
.ends dut_T
"""
TINY_PORTS = {"variant": "T", "subckt": "dut_T", "ports": ["CLK", "a", "y", "VPWR", "VGND"],
              "inputs": [{"name": "a", "role": "plain", "bit": 0}],
              "outputs": [{"name": "y", "role": "plain", "bit": 0}],
              "latency": 1, "n_cells": 3, "n_dff": 2, "wire_cap_fF": 0.0}


def write_tiny(d):
    with open(os.path.join(d, "dut.sp"), "w") as f:
        f.write(TINY_SP)
    with open(os.path.join(d, "ports.json"), "w") as f:
        json.dump(TINY_PORTS, f)


class TestBinning(unittest.TestCase):
    def test_step_charge(self):
        # step charges 1, 2, 1 (trapezoids), each spread uniformly over its step
        t = np.array([0.0, 1.0, 2.0, 3.0])
        i = np.array([0.0, 2.0, 2.0, 0.0])
        q = sc.bin_charge(t, i, np.array([0.0, 0.5, 1.5, 3.0]))
        np.testing.assert_allclose(q, [0.5, 1.5, 2.0], rtol=1e-12)

    def test_ringing_is_not_binned(self):
        # trapezoidal ringing: the samples alternate 8, 2, 8, ... but every step moves the
        # same charge, so bins that do not line up with the steps all see 5
        t = np.arange(11.0)
        i = 5.0 + 3.0 * (-1.0) ** np.arange(11)
        edges = np.array([0.0, 0.3, 1.7, 2.5, 6.1, 10.0])
        np.testing.assert_allclose(sc.bin_charge(t, i, edges) / np.diff(edges), 5.0)

    def test_bins_are_additive_and_2d(self):
        rng = np.random.default_rng(0)
        t = np.cumsum(rng.uniform(0.001, 0.05, 2000))
        i = rng.normal(size=t.size)
        fine = np.linspace(t[0], t[-1], 1001)
        qf = sc.bin_charge(t, i, fine)
        qc = sc.bin_charge(t, i, fine[::10])
        np.testing.assert_allclose(qf.reshape(-1, 10).sum(1), qc, atol=1e-12)
        q2 = sc.bin_charge(t, i, np.stack([fine[:501], fine[500:]]))
        np.testing.assert_allclose(q2.ravel(), qf, atol=1e-12)
        self.assertAlmostEqual(qf.sum(), float((0.5 * (i[1:] + i[:-1]) * np.diff(t)).sum()),
                               places=9)

    def test_repeated_timepoint(self):
        t = np.array([0.0, 1.0, 1.0, 2.0])
        i = np.array([1.0, 1.0, 3.0, 3.0])
        q = sc.bin_charge(t, i, np.array([0.0, 1.0, 2.0]))
        np.testing.assert_allclose(q, [1.0, 3.0])

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            sc.bin_charge(np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.array([0.0, 2.0]))


class TestRawfile(unittest.TestCase):
    def test_read_binary(self):
        data = np.array([[0.0, 1e-6], [1e-9, -2e-6], [2e-9, 3e-6]])
        head = ("Title: x\nDate: now\nPlotname: Transient Analysis\nFlags: real\n"
                "No. Variables: 2\nNo. Points: 3\nVariables:\n\t0\ttime\ttime\n"
                "\t1\ti(vdut)\tcurrent\nBinary:\n")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.raw")
            with open(path, "wb") as f:
                f.write(head.encode() + data.astype("<f8").tobytes())
            r = sc.read_raw(path)
        np.testing.assert_array_equal(r["time"], data[:, 0])
        np.testing.assert_array_equal(r["i(vdut)"], data[:, 1])


class TestDeck(unittest.TestCase):
    def test_timing(self):
        p = dict(sc.DEFAULTS)
        with tempfile.TemporaryDirectory() as d:
            write_tiny(d)
            ports = sc.load_dut(d)
            rows = np.array([[0], [1], [1], [0]], dtype=np.uint8)
            deck = sc.make_deck(ports, os.path.join(d, "dut.sp"), rows, p, n_rows=1)
        T = p["period"]
        # row 1 arrives at E_1 + t_in*T = 1.5T + 0.75T, row 3 at 3.5T + 0.75T
        for tc, (v0, v1) in ((1.5 * T + 0.75 * T, (0, 1.8)), (3.5 * T + 0.75 * T, (1.8, 0))):
            self.assertIn("%.6fn %g %.6fn %g" % (tc - 0.05, v0, tc + 0.05, v1), deck)
        self.assertIn("Vdut vpwr_dut 0 1.8", deck)
        self.assertIn("Xdut clk i_a o_y vpwr_dut 0 dut_T", deck)
        edges = sc.window_edges(p, 1, 1)
        self.assertAlmostEqual(edges[0, 0], sc.edge_time(p["warmup"] + 1, p) - p["pre"])
        self.assertEqual(edges.shape, (1, sc.n_samples(p, 1) + 1))


@unittest.skipUnless(shutil.which("ngspice") and os.path.isdir(sc.pdk_root()),
                     "needs ngspice and the PDK (run in the docker image)")
class TestNgspiceTiny(unittest.TestCase):
    def test_tiny_campaign(self):
        stim = np.array([[0], [1], [1], [0], [1], [0], [0], [0]], dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            write_tiny(d)
            params = dict(chunk=4, warmup=3)
            # first the first 4 rows only, then all 8: the finished chunk is reused
            tr4, _, _ = sc.run_campaign(d, stim, os.path.join(d, "a"), params, jobs=2,
                                        save_outputs=True, log=lambda m: None, rows=4)
            tr, q, man = sc.run_campaign(d, stim, os.path.join(d, "a"), params, jobs=2,
                                         save_outputs=True, log=lambda m: None)
            tr1, q1, _ = sc.run_campaign(d, stim, os.path.join(d, "b"), dict(params, chunk=8),
                                         jobs=1, log=lambda m: None)
            outputs = np.load(os.path.join(d, "a", "outputs.npy"))
        ns = sc.n_samples(sc.DEFAULTS, 1)
        self.assertEqual(tr.shape, (8, ns))
        self.assertEqual(tr.dtype, np.float32)
        self.assertEqual([bool(c.get("skipped")) for c in man["chunks"]], [True, False])
        np.testing.assert_array_equal(tr[:4], tr4)
        # function: y = ~a, registered once more (latency 1)
        np.testing.assert_array_equal(outputs[:, 0], 1 - stim[:, 0])
        # charge = sum of the bins; positive
        np.testing.assert_allclose(q, tr.astype(float).sum(1) * sc.DEFAULTS["dt"],  # uA*ns = fC
                                   rtol=1e-5)
        self.assertTrue((q > 0).all())
        # data dependence: charge in the evaluation part of the window (first 1.5 ns) follows
        # the toggles at the capturing edge: q and nq if a changed, y if the previous a changed
        ext = sc.extend_stimulus(stim, dict(sc.DEFAULTS, **params), 1)[:, 0].astype(int)
        w = params["warmup"]
        a, a1, a2 = ext[w:w + 8], ext[w - 1:w + 7], ext[w - 2:w + 6]
        activity = 2 * (a != a1) + (a1 != a2)
        early = tr[:, :150].astype(float).sum(1)
        self.assertGreater(np.corrcoef(early, activity)[0, 1], 0.9)
        # nothing happens before the capturing edge starts (window starts pre = 0.2 ns early)
        self.assertLess(np.abs(tr[:, :10]).max(), 0.05 * tr.max())
        # chunking (warm-up replays the preceding rows) matches one long simulation
        np.testing.assert_allclose(q, q1, rtol=5e-3)


if __name__ == "__main__":
    unittest.main()
