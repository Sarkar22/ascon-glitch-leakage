# SPDX-License-Identifier: Apache-2.0
"""End-to-end check of the live (Colab) path, with wall times: does a fresh machine reproduce
the shipped results?

Steps, each timed and compared with the cached data in notebook/data/:
  1. python3 gen/make_variants.py      netlists; dut.sp hashes vs data/variants.csv
  2. python3 tb/run_iverilog.py        functional check with the PDK's Verilog models
  3. python3 model/probing.py          flagged nets per variant vs data/probing_nets.csv
  4. model/stimulus.py                 the campaign stimuli; hashes vs data/campaigns.csv
  5. level 1 and level 2 models        max|t| of N and DA on the first K traces of the shared
                                       stimulus vs data/maxt_vs_traces_<c>.csv
  6. python3 sim/spice_campaign.py     the live SPICE demo (setup_env.DEMO: N with masks off,
                                       60 rows) vs data/demo_reference_N_masksoff.csv
                                       (ngspice-42): current, charge, registered outputs, TVLA

    python3 notebook/colab_check.py [--install] [--model-traces 5000] [--jobs 2]
                                    [--skip-spice] [--out report.json]
Needs live mode (setup_env): the repository, ngspice and the pinned sky130A PDK. Work files go
to runs/colab/ (git-ignored). Exit status 0 when every check passes.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import setup_env  # noqa: E402

TOL_T = 0.002              # max|t| of the models (the CSVs have 3 decimals)
# (the SPICE demo's tolerances are in setup_env.spice_demo)


def timed(report, name, fn, *args, **kw):
    t0 = time.time()
    res = fn(*args, **kw)
    dt = round(time.time() - t0, 2)
    report["steps"].append({"step": name, "seconds": dt, **(res or {})})
    ok = (res or {}).get("ok", True)
    print("[%7.1f s] %-28s %s  %s" % (dt, name, "ok  " if ok else "FAIL",
                                      (res or {}).get("summary", "")), flush=True)
    return res


def sh(cmd, repo):
    p = subprocess.run(cmd, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError("%s failed:\n%s" % (" ".join(cmd), p.stdout[-3000:]))
    return p.stdout


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def step_netlists(repo):
    sh([sys.executable, "gen/make_variants.py"], repo)
    ref = setup_env.read_csv("variants.csv")
    got = {v: sha256(os.path.join(repo, "build", v, "dut.sp")) for v in ref["variant"]}
    same = {v: got[v] == h for v, h in zip(ref["variant"], ref["dut_sp_sha256"])}
    return {"ok": all(same.values()), "identical": same,
            "summary": "dut.sp identical to the campaigns': %s" % " ".join(
                "%s=%s" % (v, "yes" if s else "NO") for v, s in same.items())}


def step_iverilog(repo):
    out = sh([sys.executable, "tb/run_iverilog.py"], repo)
    ok = "ALL PASS" in out
    return {"ok": ok, "summary": "ALL PASS" if ok else out[-300:]}


def step_probing(repo):
    sh([sys.executable, "model/probing.py"], repo)
    ref = setup_env.read_csv("probing_nets.csv")
    res, ok = {}, True
    for v in ("N", "D", "DA"):
        with open(os.path.join(repo, "results", "probing", v + ".json")) as f:
            got = len(json.load(f)["glitch_fail"])
        want = int(ref["glitch_extended_fail"][ref["variant"] == v].sum())
        res[v] = got
        ok &= got == want
    return {"ok": ok, "glitch_extended_fails": res,
            "summary": "glitch-extended flagged nets N %d, D %d, DA %d" % (res["N"], res["D"], res["DA"])}


def step_stimuli(repo, work):
    import numpy as np
    from stimulus import make_stimulus
    camp = setup_env.read_csv("campaigns.csv")
    res, ok = {}, True
    for stem in ("M_tvla", "N_masksoff"):
        i = list(camp["stimulus"]).index(stem)
        mode, seed = str(camp["stimulus_mode"][i]), int(camp["stimulus_seed"][i])
        n = int(camp["stimulus_rows_in_file"][i])
        stim, meta = make_stimulus(os.path.join(repo, "build", "N"), mode, n, seed)
        h = hashlib.sha256(np.ascontiguousarray(stim.astype(np.uint8)).tobytes()).hexdigest()
        res[stem] = h == camp["stimulus_sha256"][i]
        ok &= res[stem]
        np.save(os.path.join(work, stem + ".npy"), stim)
        np.savez(os.path.join(work, stem + ".meta.npz"), **meta)
    return {"ok": ok, "identical": res,
            "summary": "stimuli identical to the campaigns': %s" % " ".join(
                "%s=%s" % (k, "yes" if v else "NO") for k, v in res.items())}


def step_models(repo, work, k_traces, jobs):
    import numpy as np
    import kill_test as kt
    from spice_campaign import DEFAULTS
    from tvla import tvla_curve
    kt.JOBS = jobs
    man = {"params": dict(DEFAULTS)}
    stim = np.load(os.path.join(work, "M_tvla.npy"))
    meta = np.load(os.path.join(work, "M_tvla.meta.npz"))
    res, ok = {}, True
    for name, v in (("N_tvla", "N"), ("DA_tvla", "DA")):
        ref = setup_env.read_csv("maxt_vs_traces_%s.csv" % name)
        with open(os.path.join(repo, "build", v, "ports.json")) as f:
            skip = json.load(f)["latency"] + 1      # rows dropped as in the kill test
        for level in (1, 2):
            rows = kt.model_rows(v, stim, skip + k_traces, level, man)["weighted"]
            lab = meta["label"][skip:skip + k_traces]
            got = float(tvla_curve(rows, lab, [k_traces])["max_abs_t"][-1])
            key = "%s_level%d" % (name, level)
            j = np.where(ref["traces"] == k_traces)[0]
            want = float(ref["level%d_weighted" % level][j[0]]) if len(j) else None
            res[key] = {"max_abs_t": round(got, 3), "shipped": want}
            if want is not None:
                ok &= abs(got - want) <= TOL_T
    return {"ok": ok, "models": res, "summary": "max|t| at %d traces: " % k_traces + ", ".join(
        "%s %.2f" % (k, r["max_abs_t"]) for k, r in res.items())}


def step_spice(jobs):
    r = setup_env.spice_demo(jobs=jobs, verbose=False)
    keep = {k: v for k, v in r.items() if k not in ("times", "traces", "reference", "label")}
    keep["summary"] = ("%s, %d rows: |dI| <= %.2g uA, charge rel %.1e, outputs %s, max|t| %.2f "
                       "(ref %.2f) at %d traces" % (
                           r["ngspice"], r["rows"], r["max_abs_diff_uA"], r["max_charge_rel_diff"],
                           "match" if r["outputs_equal_sbox"] and r["outputs_equal_reference"]
                           else "DIFFER", r["tvla_max_abs_t_live"], r["tvla_max_abs_t_reference"],
                           r["tvla_traces"]))
    return keep


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--install", action="store_true", help="install the tools first")
    ap.add_argument("--model-traces", type=int, default=5000,
                    help="traces for the level-1/2 check (a multiple of 500 is compared)")
    ap.add_argument("--jobs", type=int, default=setup_env.DEMO["jobs"])
    ap.add_argument("--skip-iverilog", action="store_true")
    ap.add_argument("--skip-spice", action="store_true")
    ap.add_argument("--out", default=None, help="write the report here (JSON)")
    a = ap.parse_args()
    report = {"steps": []}
    t0 = time.time()
    env = setup_env.setup(mode="live", install_tools=True if a.install else None)
    report["env"] = {k: getattr(env, k) for k in ("mode", "ngspice", "iverilog", "numpy",
                                                  "pdk_version", "install_times", "colab")}
    report["env"]["python"] = sys.version.split()[0]
    repo = env.repo
    work = os.path.join(repo, "runs", "colab", "stim")
    os.makedirs(work, exist_ok=True)
    timed(report, "netlists (gen)", step_netlists, repo)
    if not a.skip_iverilog:
        timed(report, "iverilog check (tb)", step_iverilog, repo)
    timed(report, "probing (model)", step_probing, repo)
    timed(report, "stimuli (model)", step_stimuli, repo, work)
    timed(report, "level 1 + level 2 models", step_models, repo, work, a.model_traces, a.jobs)
    if not a.skip_spice:
        timed(report, "SPICE demo (sim)", step_spice, a.jobs)
    report["total_seconds"] = round(time.time() - t0, 1)
    report["ok"] = all(s.get("ok", True) for s in report["steps"])
    print("total %.1f s: %s" % (report["total_seconds"], "ALL OK" if report["ok"] else "FAILED"))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(report, f, indent=1)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
