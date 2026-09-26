# SPDX-License-Identifier: Apache-2.0
"""The notebook's live path as Colab runs it, step by step, with wall times (run by colab_live.sh).

Colab is emulated by a stub google.colab module, and the working directory is an empty /content,
so the setup cell's bootstrap has to fetch the notebook folder from GitHub: sscs-ose first, then
the author's public repository at REPO_REF. The steps and what they run:
  bootstrap      the setup cell's lines up to sys.path.insert (taken from the notebook itself)
  setup          setup_env.setup(): on Colab it installs ngspice and iverilog (apt), ciel (pip)
                 and the pinned sky130 PDK (ciel), then picks the mode
  imports        the notebook's helper imports and nbdata.fmt_headline()
  spice demo     setup_env.spice_demo(): 60 clock cycles of N with its masks forced to zero in two
                 ngspice processes, compared with the shipped ngspice-42 reference
  animation      nbanim.events("live") and the GIF, as §4.2 runs them in live mode

    python3 colab_live.py --notebook <path or URL of the .ipynb> --out report.json
"""
import argparse
import json
import os
import subprocess
import sys
import time
import types
import urllib.request

END = "sys.path.insert(0, os.getcwd())"


def setup_cell(src):
    """The bootstrap part of the notebook's first code cell (through the sys.path line)."""
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src) as f:
            nb = json.load(f)
    else:
        with open(src) as f:
            nb = json.load(f)
    cell = next("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    lines = cell.splitlines()
    return "\n".join(lines[:lines.index(END) + 1]) + "\n"


def cpu_limit():
    """CPUs this container may use: the cgroup v2 quota (docker --cpus), else os.cpu_count()."""
    try:
        with open("/sys/fs/cgroup/cpu.max") as f:
            quota, period = f.read().split()
        if quota != "max":
            return round(int(quota) / int(period), 2)
    except (OSError, ValueError):
        pass
    return os.cpu_count()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--notebook", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workdir", default="/content")
    a = ap.parse_args()
    boot = setup_cell(a.notebook)
    sys.modules.setdefault("google", types.ModuleType("google"))
    sys.modules["google.colab"] = types.ModuleType("google.colab")
    os.makedirs(a.workdir, exist_ok=True)
    os.chdir(a.workdir)
    report = {"notebook": a.notebook, "steps": [], "commands": []}
    t_start = time.time()
    real_run = subprocess.run

    def logged_run(*args, **kw):
        t = time.time()
        p = real_run(*args, **kw)
        cmd = args[0] if isinstance(args[0], str) else " ".join(args[0])
        report["commands"].append({"cmd": cmd, "seconds": round(time.time() - t, 1), "rc": p.returncode})
        print("  [%6.1f s] rc %d  %s" % (time.time() - t, p.returncode, cmd), flush=True)
        return p

    def step(name, fn):
        t = time.time()
        res = fn()
        report["steps"].append({"step": name, "seconds": round(time.time() - t, 1)})
        print("== %-44s %7.1f s   (elapsed %.1f s)" % (name, time.time() - t, time.time() - t_start),
              flush=True)
        with open(a.out, "w") as f:
            json.dump(report, f, indent=1)
        return res

    def bootstrap():
        subprocess.run = logged_run
        try:
            exec(compile(boot, "setup cell", "exec"), {"__name__": "__main__"})
        finally:
            subprocess.run = real_run
        report["notebook_folder"] = os.path.relpath(os.getcwd(), a.workdir)

    step("bootstrap (fetch the notebook folder)", bootstrap)
    sys.path.insert(0, os.getcwd())
    import setup_env
    env = step("setup_env.setup() (installs on Colab)", setup_env.setup)
    report["env"] = {k: getattr(env, k) for k in ("mode", "ngspice", "iverilog", "numpy", "matplotlib",
                                                  "pdk_version", "install_times", "reasons")}
    report["env"]["python"] = sys.version.split()[0]
    report["env"]["cpus"] = cpu_limit()

    def imports():
        import nbdata
        for m in ("nbanim", "nbexplorer", "nbfigs"):
            __import__(m)
        return nbdata.fmt_headline()

    step("notebook imports and headline numbers", imports)
    res = step("setup_env.spice_demo() (2 ngspice processes)", setup_env.spice_demo)
    report["spice_demo"] = {k: v for k, v in res.items() if k not in ("times", "traces", "reference", "label")}

    def animation():
        import nbanim
        nbanim.save_gif(nbanim.events("live"), os.path.join(a.workdir, "glitch_live.gif"))

    step("live animation (level-2 events and GIF)", animation)
    report["total_seconds"] = round(time.time() - t_start, 1)
    report["ok"] = bool(env.live and res["ok"])
    with open(a.out, "w") as f:
        json.dump(report, f, indent=1)
    print("total %.1f s: %s" % (report["total_seconds"], "ok" if report["ok"] else "FAILED"))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
