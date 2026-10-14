"""Markdown tables for the README, generated from results/summary.json (run summarize.py first)."""
import json, os
import vgrid, summarize

S = summarize.main()
NAMES = {"oberrhein": "mv_oberrhein", "cigre_mv": "CIGRE MV", "kerber_dorf": "Kerber Dorfnetz", "kerber_vorstadt": "Kerber Vorstadtnetz"}
pct = lambda x: "n/a" if x is None else f"{x*100:.1f}%"
sig = lambda x: "n/a" if x is None or x != x else f"{x:.3g}"
out = []

out.append("### Topologies and stress calibration\n")
out.append("| Topology | Buses | Lines | Real tie switches | PV nameplate / total load (calibrated) | Test-year curtailment hours (DE / IN-solar) |")
out.append("|---|---|---|---|---|---|")
for t in vgrid.TOPOLOGIES:
    T = vgrid.Topo(t)
    d = S[t]
    ties = {"oberrhein": 6, "cigre_mv": 3}.get(t, 0)
    ev_de = d["p1_de"]["models"]["persistence"]["event_rate_actual"] if d.get("p1_de") else None
    ev_in = d["p1_in"]["models"]["persistence"]["event_rate_actual"] if d.get("p1_in") else None
    out.append(f"| {NAMES[t]} | {T.n_bus} | {T.n_line} | {ties} | {d['pv_to_load_ratio']:.2f}x | {pct(ev_de)} / {pct(ev_in)} |")

for ds, title in (("de", "German real data (OPSD hourly solar + demand)"), ("in", "Indian solar (NASA POWER, Rajasthan) + German demand shape")):
    out.append(f"\n### Product 1 — {title}\n")
    out.append("Test = 2019 (never seen in training). Errors in MW per bus-hour over all hours. Event F1 = does the network curtail next hour (>0.01 MW), threshold picked on 2018 validation.\n")
    out.append("| Topology | Model | MAE | RMSE | Network-total correlation | Event F1 (P / R) |")
    out.append("|---|---|---|---|---|---|")
    for t in vgrid.TOPOLOGIES:
        p = S[t].get(f"p1_{ds}")
        if not p: continue
        for m, v in p["models"].items():
            star = " **(best)**" if m == p["best_model"] else ""
            out.append(f"| {NAMES[t]} | {m}{star} | {sig(v['mae_per_bus'])} | {sig(v['rmse_per_bus'])} | {sig(v['corr_network_total'])} | {v['event_f1']:.3f} ({v['event_precision']:.2f} / {v['event_recall']:.2f}) |")
    out.append("")
    out.append("| Topology | Train / val / test days | Best model beats mean (MAE) | beats persistence (RMSE) | beats persistence (MAE) |")
    out.append("|---|---|---|---|---|")
    for t in vgrid.TOPOLOGIES:
        p = S[t].get(f"p1_{ds}")
        if not p: continue
        out.append(f"| {NAMES[t]} | {p['train_days']} / {p['val_days']} / {p['test_days']} | {p['beats_mean_mae']} | {p['beats_persistence_rmse']} | {p['beats_persistence_mae']} |")

out.append("\n### Product 2 — localization accuracy (300 trials per topology, random real 2019 operating states)\n")
out.append("| Topology | Feature set / sensor coverage | Exact bus | ≤2 hops | ≤5 hops | True bus in top 3 |")
out.append("|---|---|---|---|---|---|")
lab = {"V@100": "voltage only (original method), all buses instrumented", "VTI@100": "voltage + angle + line current, all instrumented",
       "V@30": "voltage only, 30% of sensors", "VTI@30": "voltage + angle + current, 30% of sensors"}
for t in vgrid.TOPOLOGIES:
    for k in ("V@100", "VTI@100", "V@30", "VTI@30"):
        r = S[t]["p2"]["results"][k]
        out.append(f"| {NAMES[t]} | {lab[k]} | {pct(r['exact'])} | {pct(r['within2'])} | {pct(r['within5'])} | {pct(r['top3'])} |")

out.append("\n### FISR — every feeder bus faulted once at the 2019 peak-load hour\n")
out.append("| Topology | Faults | Localized exactly | Isolated ≤3 attempts | Lockout | Avoidable load restored (Vidyut) | (perfect localization) | Events needing ties → fully restored | Violations after − before (mean) |")
out.append("|---|---|---|---|---|---|---|---|---|")
for t in vgrid.TOPOLOGIES:
    f = S[t]["fisr"]
    nt = f["vidyut_events_needing_ties"]
    out.append(f"| {NAMES[t]} | {f['n_faults']} | {pct(f['localization_exact_at_snapshot'])} | {pct(f['vidyut_isolated_within_3_attempts'])} | {pct(f['vidyut_lockout'])} | "
               f"{pct(f['vidyut_mean_restored_frac_of_avoidable_incl_lockouts'])} | {pct(f['oracle_mean_restored_frac_of_avoidable'])} | "
               f"{f['vidyut_events_needing_ties_fully_restored']} / {nt} | {sig(f['vidyut_mean_violation_delta_vs_prefault'])} |")
open(os.path.join(vgrid.HERE, "results", "tables.md"), "w", encoding="utf-8").write("\n".join(out))
print("\n".join(out))
