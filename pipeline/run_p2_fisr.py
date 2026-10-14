"""
Product 2 (localization) + FISR evaluation for one topology. Checkpointed: localization study -> results/p2_loc_*.json,
per-bus FISR events -> results/fisr_events_*.jsonl (append-only; resumes where it stopped).

FISR sweep: every bus is faulted once at the PEAK-LOAD real hour of 2019 (worst case for restoration headroom), with
noisy sensor readings -> Vidyut's localization (dV+dTheta+dI, 100% sensor coverage) -> FISR on the real switch model.
A control run gives FISR the TRUE fault bus (perfect localization) so switching logic and localization error are
reported separately.
"""
import json, os, sys, time
import numpy as np
import vgrid, localize, fisr

RES = os.path.join(vgrid.HERE, "results")
os.makedirs(RES, exist_ok=True)


def peak_snapshot():
    sc = vgrid.scenarios("de")
    sc = sc[sc.date >= "2019-01-01"]
    best = max(((r.lf[h], r.sf[h], r.date, h) for _, r in sc.iterrows() for h in range(24)))
    return float(best[1]), float(best[0]), best[2], best[3]


def compact(ev):
    """Trim an event to what the 3D viewer needs."""
    keep = {k: ev[k] for k in ("true_bus", "ranked", "outcome", "attempts", "outage_buses", "head_line", "zone",
                                "iso_ops", "tie_ops", "metrics", "total_load_mw", "final_metrics", "final_ll", "final_vm")
            if k in ev}
    keep["stages"] = ev["stages"]
    return keep


def main(topo, n_loc_trials=300):
    T_loc = vgrid.Topo(topo)
    locf = os.path.join(RES, f"p2_loc_{topo}.json")
    if not os.path.exists(locf):
        t0 = time.time()
        r = localize.evaluate(topo, n_states=30, per_state=n_loc_trials // 30, seed=5)
        r.pop("rows")
        json.dump(r, open(locf, "w"), indent=1)
        print(f"[{topo}] localization study done ({r['n']} trials, {time.time()-t0:.0f}s)", flush=True)
        for k, v in r["results"].items():
            print(f"   {k}: exact {v['exact']*100:.1f}%  <=2hop {v['within2']*100:.1f}%  <=5hop {v['within5']*100:.1f}%", flush=True)

    sf, lf, sdate, sh = peak_snapshot()
    evf = os.path.join(RES, f"fisr_events_{topo}.jsonl")
    done = set()
    if os.path.exists(evf):
        for line in open(evf):
            done.add(json.loads(line)["fault_bus"])
    loc = localize.Localizer(vgrid.Topo(topo)); D, valid = loc.build_state(sf, lf)   # dictionary AT the pre-fault state
    F = fisr.FISR(vgrid.Topo(topo), sf, lf)
    Fo = fisr.FISR(vgrid.Topo(topo), sf, lf)          # oracle-localization control
    t0 = time.time()
    for b in range(T_loc.n_bus):
        if b in done or not valid[b]:
            if not valid[b] and b not in done:
                open(evf, "a").write(json.dumps({"fault_bus": b, "skipped": "no valid fingerprint"}) + "\n")
            continue
        rng = np.random.default_rng(10_000 + b)
        try:
            dv, dth, di, mw = loc.trial(b, sf, lf, rng, sev=None)
            feat = loc.features(dv, dth, di, "VTI")
            order, scores = loc.rank(feat, D, "VTI", valid)
            ev = F.run_event(b, order[:6].tolist())
            evo = Fo.run_event(b, [b])
        except Exception as e:
            open(evf, "a").write(json.dumps({"fault_bus": b, "error": str(e)}) + "\n")
            continue
        rec = {"fault_bus": b, "anomaly_mw": mw, "top_score": float(scores[order[0]]),
               "vidyut": compact(ev) if ev else None, "oracle_outcome": (evo or {}).get("outcome"),
               "oracle_metrics": (evo or {}).get("metrics"), "oracle_final": (evo or {}).get("final_metrics")}
        open(evf, "a").write(json.dumps(rec) + "\n")
        if b % 20 == 0:
            print(f"[{topo}] fisr sweep bus {b}/{T_loc.n_bus} ({time.time()-t0:.0f}s)", flush=True)
    meta = {"snapshot": {"date": sdate, "hour": int(sh), "sf": sf, "lf": lf}}
    json.dump(meta, open(os.path.join(RES, f"fisr_meta_{topo}.json"), "w"))
    print(f"[{topo}] FISR sweep complete.", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 300)
