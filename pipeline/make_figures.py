"""Cross-topology result figure (computed from results/summary.json; nothing typed in)."""
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import vgrid, summarize

S = summarize.main()
tops = [t for t in vgrid.TOPOLOGIES if S[t].get("p2")]
short = {"oberrhein": "oberrhein\n(MV, 179 bus)", "cigre_mv": "CIGRE MV\n(15 bus)", "kerber_dorf": "Kerber dorf\n(LV, 116 bus)",
         "kerber_vorstadt": "Kerber vorstadt\n(LV, 294 bus)"}
fig, ax = plt.subplots(2, 2, figsize=(14, 9.5))
x = np.arange(len(tops))

a = ax[0, 0]
for k, (key, lab, off) in enumerate([("V@100", "voltage only (original)", -.27), ("VTI@100", "V + angle + current", -.09),
                                       ("V@30", "voltage only, 30% sensors", .09), ("VTI@30", "V+angle+current, 30% sensors", .27)]):
    a.bar(x + off, [S[t]["p2"]["results"][key]["exact"] * 100 for t in tops], .18, label=lab)
a.set_xticks(x); a.set_xticklabels([short[t] for t in tops]); a.set_ylabel("exact-bus accuracy (%)")
a.set_title("Product 2: localization, 300 trials at random real 2019 states"); a.set_ylim(0, 125); a.legend(fontsize=8, ncol=2, loc="upper center")

a = ax[0, 1]
names = ["mean", "persistence", "GCN", "GBM-graph", "GBM-nolag"]
for k, m in enumerate(names):
    vals = []
    for t in tops:
        p = S[t].get("p1_de")
        vals.append(np.nan if not p else p["models"][m]["rmse_per_bus"] / p["models"]["mean"]["rmse_per_bus"])
    a.bar(x + (k - 2) * .16, vals, .16, label=m)
a.axhline(1, color="k", lw=.7, ls=":")
a.set_xticks(x); a.set_xticklabels([short[t] for t in tops]); a.set_ylabel("test RMSE / mean-baseline RMSE (lower = better)")
a.set_title("Product 1: next-hour curtailment, held-out year 2019"); a.legend(fontsize=8)

a = ax[1, 0]
vals = [S[t]["fisr"] for t in tops]
a.bar(x - .2, [v["vidyut_mean_restored_frac_of_avoidable_incl_lockouts"] * 100 for v in vals], .4, label="with Vidyut localization")
a.bar(x + .2, [v["oracle_mean_restored_frac_of_avoidable"] * 100 for v in vals], .4, label="with perfect localization")
a.set_xticks(x); a.set_xticklabels([short[t] for t in tops]); a.set_ylabel("% of avoidable outage load restored")
a.set_title("FISR (peak-load snapshot, every feeder bus faulted once)"); a.legend(fontsize=8)

a = ax[1, 1]
a.bar(x - .2, [v["localization_exact_at_snapshot"] * 100 for v in vals], .4, label="localized exactly")
a.bar(x + .2, [v["vidyut_isolated_within_3_attempts"] * 100 for v in vals], .4, label="fault isolated (<=3 attempts)")
a.set_xticks(x); a.set_xticklabels([short[t] for t in tops]); a.set_ylabel("%")
a.set_title("FISR: localization and isolation success"); a.set_ylim(0, 125); a.legend(fontsize=8, ncol=2, loc="upper center")
plt.tight_layout()
out = os.path.join(vgrid.HERE, "vidyut_prototype_results.png")
plt.savefig(out, dpi=130)
print("saved", out)
