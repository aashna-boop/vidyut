"""
Reproduce the whole pipeline. Every step is checkpointed and skips work that is already on disk, so this is safe to
interrupt and re-run.

  python run_all.py            # everything, German dataset + India-solar variant
  python run_all.py --fast     # German dataset only

Order:  data_fetch -> calibrate_pv -> run_sim (parallel, chunked) -> curtail_model (Product 1) ->
        run_p2_fisr (Product 2 + FISR, per topology) -> summarize -> make_figures -> build_viz -> test_end_to_end
Rough wall-clock on a 20-core machine: simulation ~25 min per dataset, Product 1 ~30-60 min, localization+FISR ~10 min.
"""
import os, subprocess, sys
import vgrid

PIPE = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(PIPE)
PY = sys.executable
fast = "--fast" in sys.argv
datasets = ["de"] if fast else ["de", "in"]


def run(*args):
    print("\n$", " ".join(args), flush=True)
    r = subprocess.run([PY, os.path.join(PIPE, args[0]), *args[1:]], cwd=PIPE)
    if r.returncode:
        sys.exit(f"step failed: {args}")


run("data_fetch.py")
if not os.path.exists(vgrid.RATIO_FILE):
    run("calibrate_pv.py")
for d in datasets:
    run("run_sim.py", ",".join(vgrid.TOPOLOGIES), d)
for d in datasets:
    for t in vgrid.TOPOLOGIES:
        if not os.path.exists(os.path.join(HERE, "results", f"p1_{t}_{d}.json")):
            run("curtail_model.py", t, d)
for t in vgrid.TOPOLOGIES:
    run("run_p2_fisr.py", t)
run("summarize.py")
run("make_figures.py")
run("build_viz.py")
run("test_end_to_end.py", "cigre_mv")
run("test_end_to_end.py", "oberrhein")
print("\nALL DONE")
