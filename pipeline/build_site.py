"""Export real project data for the website -> website/data/site-data.js  (window.VIDYUT = {...}).
Every number the site shows comes from here (results/summary.json, sim outputs, FISR events); none is typed into the HTML."""
import json, os
import numpy as np
import vgrid, fisr, summarize
from scada_mock import MockSCADA
from build_viz import layout

HERE = vgrid.HERE
RES = os.path.join(HERE, "results")
OUT = os.path.join(HERE, "website", "data")
os.makedirs(OUT, exist_ok=True)
NAMES = {"oberrhein": "Oberrhein", "cigre_mv": "CIGRE MV", "kerber_dorf": "Kerber Dorf", "kerber_vorstadt": "Kerber Vorstadt"}
PLACE = {"oberrhein": "MV · 2 substations", "cigre_mv": "MV benchmark", "kerber_dorf": "LV village feeder", "kerber_vorstadt": "LV suburban feeder"}
r1 = lambda x: round(float(x), 1)


def topo_block(name, S):
    T = vgrid.Topo(name)
    xy = layout(T)
    xy = xy / (np.abs(xy).max() + 1e-9)
    xy[:, 1] *= -1                                  # screen y grows downward
    meta = S[name].get("fisr_meta", {"snapshot": {}})["snapshot"]
    F = fisr.FISR(vgrid.Topo(name), meta.get("sf", 0.0), meta.get("lf", 1.0))
    pv = set(T.sgen_bus.tolist())
    events = {}
    for e in summarize.load_events(name):
        v = e.get("vidyut")
        if not v:
            continue
        b = str(e["fault_bus"])
        if v["outcome"] == "substation_bus":
            events[b] = {"o": "s"}
            continue
        st = v["stages"]
        F.reset()
        head, _ = F.feeder_head(e["fault_bus"])
        sw2 = {si: lp for lp, d in F.sw_by_line.items() for si in d.values()}
        ops = lambda L: [sw2[o["idx"]] if o["kind"] == "sw" else o["idx"] for o in (L or [])]
        ids = lambda L: [MockSCADA.op_id((o["kind"], o["idx"])) for o in (L or [])]
        ok = v["outcome"] == "restored"
        tot = v["total_load_mw"]
        ev = {"o": "r" if ok else "l", "r": v["ranked"][:3], "out": v["outage_buses"], "head": v["head_line"],
              "hid": [MockSCADA.op_id(o) for o in F.head_ops(head)] if head else [],
              "att": len(v["attempts"]), "tot": round(tot, 2),
              "s": [round(s["served_mw"], 2) for s in st], "d": [s["dead"] for s in st]}
        if ok:
            ev.update({"z": v["zone"], "iso": ops(v.get("iso_ops")), "tie": ops(v.get("tie_ops")),
                       "isoId": ids(v.get("iso_ops")), "tieId": ids(v.get("tie_ops"))})
        events[b] = ev
    return {"key": name, "name": NAMES[name], "place": PLACE[name], "nBus": T.n_bus, "nLine": T.n_line,
            "buses": [[round(float(xy[i, 0]), 4), round(float(xy[i, 1]), 4), 1 if i in pv else 0] for i in range(T.n_bus)],
            "lines": [[int(T.line_from[l]), int(T.line_to[l])] for l in range(T.n_line)],
            "ties": sorted(F.ties.keys()), "events": events, "snapshot": meta}


def main():
    S = summarize.main()
    topos = {t: topo_block(t, S) for t in vgrid.TOPOLOGIES}
    # real demo week (oberrhein, 2019-06-03..09, test year): actual vs model next-hour forecast, network total MW
    d = np.load(os.path.join(RES, "demo_oberrhein_de.npz"))
    week = {"dates": d["dates"].tolist(), "actual": [round(float(x), 2) for x in d["actual"].sum(1)],
            "pred": [round(float(x), 2) for x in d["pred"].sum(1)]}
    stats = {}
    for t in vgrid.TOPOLOGIES:
        s = S[t]
        p1, p1i, p2, f = s.get("p1_de"), s.get("p1_in"), s["p2"]["results"], s["fisr"]
        best = p1["models"][p1["best_model"]]
        stats[t] = {
            "loc_vti_full": p2["VTI@100"]["exact"], "loc_v_full": p2["V@100"]["exact"], "loc_vti_30": p2["VTI@30"]["exact"],
            "loc_vti_5hop_30": p2["VTI@30"]["within5"],
            "best_model": p1["best_model"], "p1_f1": best["event_f1"], "p1_f1_persist": p1["models"]["persistence"]["event_f1"],
            "p1_rmse_ratio": best["rmse_per_bus"] / p1["models"]["mean"]["rmse_per_bus"],
            "p1_in_f1": p1i["models"][p1i["best_model"]]["event_f1"],
            "restored": f["vidyut_mean_restored_frac_of_avoidable_incl_lockouts"], "restored_oracle": f["oracle_mean_restored_frac_of_avoidable"],
            "isolated": f["vidyut_isolated_within_3_attempts"], "lockout": f["vidyut_lockout"], "faults": f["n_faults"],
            "exact_snapshot": f["localization_exact_at_snapshot"], "ties": len(topos[t]["ties"]),
            "needing_ties": f["vidyut_events_needing_ties"], "needing_ties_ok": f["vidyut_events_needing_ties_fully_restored"],
        }
    n_de = len(vgrid.scenarios("de")); n_in = len(vgrid.scenarios("in"))
    data = {"topos": topos, "order": vgrid.TOPOLOGIES, "week": week, "stats": stats,
            "global": {"days_de": n_de, "days_in": n_in, "hours_de": n_de * 24, "grids": len(vgrid.TOPOLOGIES),
                       "events_total": sum(len([e for e in t["events"].values() if e["o"] != "s"]) for t in topos.values())}}
    js = "window.VIDYUT=" + json.dumps(data, separators=(",", ":"), allow_nan=False) + ";"
    open(os.path.join(OUT, "site-data.js"), "w", encoding="utf-8").write(js)
    print(f"wrote website/data/site-data.js ({len(js)/1e6:.2f} MB); stats keys: {list(stats['oberrhein'])[:4]}...")


if __name__ == "__main__":
    main()
