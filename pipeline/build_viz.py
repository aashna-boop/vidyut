"""Build vidyut_3d_visualization.html: 4 topologies, live week playback, maintenance, localization stats, and the
interactive FISR replay (every bus precomputed by the real localization model + real AC-power-flow switching engine)."""
import json, os
import numpy as np
import networkx as nx
import vgrid, fisr, summarize
from scada_mock import MockSCADA

HERE = vgrid.HERE
RES = os.path.join(HERE, "results")
LABELS = {"oberrhein": "mv_oberrhein · German MV (2 substations, 6 real tie switches)",
          "cigre_mv": "CIGRE MV benchmark · 15 buses (3 real tie switches)",
          "kerber_dorf": "Kerber Dorfnetz · 10 kV/0.4 kV LV village feeder (radial, no ties)",
          "kerber_vorstadt": "Kerber Vorstadtnetz · 10 kV/0.4 kV LV suburban (radial, no ties)"}


def layout(T):
    net = T.net
    xy = None
    try:
        if "geo" in net.bus.columns and net.bus.geo.notna().all():
            pts = [json.loads(g)["coordinates"] for g in net.bus.loc[T.bus_ids].geo]
            xy = np.array(pts, float)
            if np.abs(xy).max() <= 180:                       # real lon/lat -> local metres
                lat0 = xy[:, 1].mean()
                xy = np.c_[(xy[:, 0] - xy[:, 0].mean()) * np.cos(np.radians(lat0)), xy[:, 1] - lat0]
    except Exception:
        xy = None
    if xy is None:
        p = nx.kamada_kawai_layout(T.G)
        xy = np.array([p[i] for i in range(T.n_bus)])
    xy = xy - xy.mean(0)
    xy = xy / (np.abs(xy).max() + 1e-9) * 165
    return xy


def build_topo(name):
    T = vgrid.Topo(name)
    xy = layout(T)
    S = summarize.main()[name]
    sim = vgrid.load_sim(name, "de")
    ll = sim["ll"]
    stress = (ll / 100.0) ** 2
    cum = stress.sum(0)
    rel = cum / (cum.max() + 1e-9) * 100
    top = np.argsort(-cum)[:8]
    import pandas as pd
    pd.DataFrame({"line_index": [int(T.net.line.index[l]) for l in top], "from_bus": [int(T.net.line.from_bus.iloc[l]) for l in top],
                  "to_bus": [int(T.net.line.to_bus.iloc[l]) for l in top], "stress_score_0_100": [round(float(rel[l]), 1) for l in top]}
                 ).to_csv(os.path.join(RES, f"predictive_maintenance_{name}.csv"), index=False)
    demo_f = os.path.join(RES, f"demo_{name}_de.npz")
    if os.path.exists(demo_f):
        d = np.load(demo_f)
        pvb = np.unique(T.sgen_bus)
        curtA = np.round(d["actual"][:, pvb], 3).tolist()
        curtP = np.round(d["pred"][:, pvb], 3).tolist()
        dll = np.round(d["ll"]).astype(int).tolist()
        dates = d["dates"].tolist()
    else:
        pvb, curtA, curtP, dll, dates = np.unique(T.sgen_bus), [], [], [], []
    p1 = S.get("p1_de")
    p1s = None
    if p1:
        p1s = {"best": p1["best_model"], "train_days": p1["train_days"], "val_days": p1["val_days"], "test_days": p1["test_days"],
               "beats_mean_mae": p1["beats_mean_mae"], "beats_persistence_rmse": p1["beats_persistence_rmse"],
               "beats_persistence_mae": p1["beats_persistence_mae"],
               "models": {k: {m: (None if v.get(m) is None else float(f"{v[m]:.4g}")) for m in
                              ("mae_per_bus", "rmse_per_bus", "corr_network_total", "event_f1", "event_precision", "event_recall", "event_rate_actual")}
                          for k, v in p1["models"].items()}}
    # FISR events (Vidyut run) + switching-op -> line-position conversion
    meta = S.get("fisr_meta", {"snapshot": {}})
    snap = meta["snapshot"]
    F = fisr.FISR(vgrid.Topo(name), snap.get("sf", 0.0), snap.get("lf", 1.0))
    m0 = F.solve()
    sw2line = {si: lp for lp, d in F.sw_by_line.items() for si in d.values()}
    def op_lines(ops):
        return [sw2line[o["idx"]] if o["kind"] == "sw" else o["idx"] for o in (ops or [])]
    events = {}
    for e in summarize.load_events(name):
        v = e.get("vidyut")
        if not v or v["outcome"] == "substation_bus":
            if v: events[str(e["fault_bus"])] = {"outcome": "substation_bus"}
            continue
        ev = {k: v[k] for k in ("true_bus", "ranked", "outcome", "attempts", "outage_buses", "head_line", "zone", "metrics",
                                 "total_load_mw", "final_metrics") if k in v}
        ev["iso_lines"] = op_lines(v.get("iso_ops"))
        ev["tie_lines"] = op_lines(v.get("tie_ops"))
        ev["iso_ids"] = [MockSCADA.op_id((o["kind"], o["idx"])) for o in v.get("iso_ops", [])]
        ev["tie_ids"] = [MockSCADA.op_id((o["kind"], o["idx"])) for o in v.get("tie_ops", [])]
        F.reset(); head, _ = F.feeder_head(e["fault_bus"])
        ev["head_ids"] = [MockSCADA.op_id(o) for o in F.head_ops(head)] if head else []
        ev["stages"] = [{"name": s["name"], "note": s["note"], "dead": s["dead"], "open": s["open_lines"], "served": s["served_mw"],
                         "vmin": s["vmin"], "vmax": s["vmax"], "maxload": s["max_loading"], "viol": s["violations"]} for s in v["stages"]]
        if "final_ll" in v: ev["final_ll"] = v["final_ll"]
        ev["score"] = round(e["top_score"], 3)
        events[str(e["fault_bus"])] = ev
    return {
        "name": name, "label": LABELS[name], "nBus": T.n_bus, "nLine": T.n_line,
        "buses": [{"x": round(float(xy[i, 0]), 2), "z": round(float(xy[i, 1]), 2),
                   "pv": bool(i in set(T.sgen_bus.tolist())), "ld": bool(i in set(T.load_bus.tolist()))} for i in range(T.n_bus)],
        "lines": [{"f": int(T.line_from[l]), "t": int(T.line_to[l]), "s": round(float(rel[l]), 1)} for l in range(T.n_line)],
        "topStress": [{"f": int(T.line_from[l]), "t": int(T.line_to[l]), "score": round(float(rel[l]), 1)} for l in top],
        "pvBuses": [int(b) for b in pvb], "curtA": curtA, "curtP": curtP, "ll": dll, "dates": dates,
        "p1": p1s, "p2": S.get("p2"),
        "fisrStats": S.get("fisr"), "snapshot": snap,
        "baseLL": [int(round(x)) for x in m0["ll"]],
        "ties": sorted(F.ties.keys()), "assumedSectionalisers": bool(F.assume_sectionalisers),
        "events": events, "pvRatio": S.get("pv_to_load_ratio"),
        "nDays": int(len(sim["dates"])),
    }


def clean(o):
    """JSON has no NaN/Infinity: turn non-finite floats into null (e.g. correlation of a constant predictor)."""
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def main():
    topos =[t for t in vgrid.TOPOLOGIES if os.path.exists(os.path.join(RES, f"fisr_events_{t}.jsonl"))]
    data = {"topos": {t: build_topo(t) for t in topos}, "order": topos}
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "viz_template.html"), encoding="utf-8").read()
    html = tpl.replace("__VIDYUT_DATA_JSON__", json.dumps(clean(data), separators=(",", ":"), allow_nan=False))
    out = os.path.join(HERE, "vidyut_3d_visualization.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"wrote {out} ({len(html)/1e6:.1f} MB) with topologies: {topos}")


if __name__ == "__main__":
    main()
