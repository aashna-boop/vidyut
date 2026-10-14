"""Aggregate raw results -> results/summary.json + results/summary.md (every number here is computed, none typed in)."""
import json, os
import numpy as np
import vgrid

RES = os.path.join(vgrid.HERE, "results")


def load_events(topo):
    f = os.path.join(RES, f"fisr_events_{topo}.jsonl")
    out = []
    if os.path.exists(f):
        for line in open(f):
            d = json.loads(line)
            out.append(d)
    return out


def fisr_stats(topo):
    evs = load_events(topo)
    ok = [e for e in evs if e.get("vidyut") and e["vidyut"]["outcome"] in ("restored", "isolation_failed")]
    skipped_sub = sum(1 for e in evs if e.get("vidyut") and e["vidyut"]["outcome"] == "substation_bus")
    errors = sum(1 for e in evs if "error" in e or "skipped" in e)
    n = len(ok)
    if n == 0:
        return None
    def viol_delta(e):
        v = e["vidyut"]
        return (v["final_metrics"]["violations"] - v["stages"][0]["violations"]) if v["outcome"] == "restored" else None
    rest = [e for e in ok if e["vidyut"]["outcome"] == "restored"]
    def frac(e): return e["vidyut"]["metrics"]["restored_frac_of_avoidable"]
    fr_all = [(frac(e) if e["vidyut"]["outcome"] == "restored" and frac(e) is not None else (0.0 if e["vidyut"]["metrics"]["outage_load_mw"] > 0 and e["vidyut"]["outcome"] != "restored" else None)) for e in ok]
    fr_all = [x for x in fr_all if x is not None]
    or_ok = [e for e in ok if e.get("oracle_outcome")]
    or_rest = [e for e in or_ok if e["oracle_outcome"] == "restored"]
    ofr = [e["oracle_metrics"]["restored_frac_of_avoidable"] for e in or_rest if e["oracle_metrics"]["restored_frac_of_avoidable"] is not None]
    served = lambda e: e["vidyut"]["metrics"]["final_served_frac"]
    tie_used = [bool(e["vidyut"].get("tie_ops")) for e in rest]
    # events where restoration through ties could matter (some avoidable outage remained after upstream restoration)
    stranded = [e for e in rest if len(e["vidyut"]["stages"]) >= 5 and
                (e["vidyut"]["stages"][3]["served_mw"] < e["vidyut"]["total_load_mw"] - e["vidyut"]["metrics"]["unavoidable_zone_load_mw"] - 1e-6)]
    stranded_fixed = [e for e in stranded if e["vidyut"]["metrics"]["restored_frac_of_avoidable"] is not None and e["vidyut"]["metrics"]["restored_frac_of_avoidable"] > 0.999]
    return {
        "n_faults": n, "n_substation_faults_excluded": skipped_sub, "n_errors_or_skipped": errors,
        "localization_exact_at_snapshot": float(np.mean([e["vidyut"]["ranked"][0] == e["fault_bus"] for e in ok])),
        "first_attempt_isolated": float(np.mean([e["vidyut"]["metrics"]["first_attempt_hit"] if "metrics" in e["vidyut"] else False for e in ok])),
        "vidyut_isolated_within_3_attempts": len(rest) / n,
        "vidyut_lockout": 1 - len(rest) / n,
        "vidyut_mean_restored_frac_of_avoidable_incl_lockouts": float(np.mean(fr_all)) if fr_all else None,
        "vidyut_mean_final_served_frac": float(np.mean([served(e) for e in rest])) if rest else None,
        "vidyut_mean_attempts": float(np.mean([e["vidyut"]["metrics"]["attempts"] for e in ok])),
        "vidyut_events_needing_ties": len(stranded),
        "vidyut_events_needing_ties_fully_restored": len(stranded_fixed),
        "vidyut_mean_violation_delta_vs_prefault": float(np.mean([viol_delta(e) for e in rest])) if rest else None,
        "oracle_isolated": len(or_rest) / max(len(or_ok), 1),
        "oracle_mean_restored_frac_of_avoidable": float(np.mean(ofr)) if ofr else None,
        "oracle_mean_final_served_frac": float(np.mean([e["oracle_metrics"]["final_served_frac"] for e in or_rest])) if or_rest else None,
    }


def main():
    S = {}
    for t in vgrid.TOPOLOGIES:
        d = {}
        for name in ("p2_loc_%s" % t,):
            f = os.path.join(RES, name + ".json")
            if os.path.exists(f): d["p2"] = json.load(open(f))
        for ds in ("de", "in"):
            f = os.path.join(RES, f"p1_{t}_{ds}.json")
            if os.path.exists(f): d[f"p1_{ds}"] = json.load(open(f))
        d["fisr"] = fisr_stats(t)
        mf = os.path.join(RES, f"fisr_meta_{t}.json")
        if os.path.exists(mf): d["fisr_meta"] = json.load(open(mf))
        r = json.load(open(vgrid.RATIO_FILE)) if os.path.exists(vgrid.RATIO_FILE) else {}
        d["pv_to_load_ratio"] = r.get(t)
        S[t] = d
    json.dump(S, open(os.path.join(RES, "summary.json"), "w"), indent=1)
    return S


if __name__ == "__main__":
    S = main()
    pct = lambda x: "n/a" if x is None else f"{x*100:.1f}%"
    for t, d in S.items():
        print(f"\n== {t} ==")
        if d.get("p2"):
            for k, v in d["p2"]["results"].items():
                print(f"  loc {k:8s} exact {pct(v['exact'])}  <=2hop {pct(v['within2'])}  <=5hop {pct(v['within5'])}  top3 {pct(v['top3'])}")
        if d.get("fisr"):
            print("  FISR:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d["fisr"].items()})
