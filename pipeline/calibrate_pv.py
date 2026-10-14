"""Calibrate each topology's PV/load ratio so it curtails the same share of potential PV energy on a reference
real summer day (2018-06-20, OPSD Germany) as the original mv_oberrhein scenario. Result -> data/pv_ratios.json"""
import json, numpy as np
import vgrid

REF_DAY = "2018-06-20"


def curtail_share(name, ratio, row, seed=1):
    T = vgrid.Topo(name, ratio)
    rng = np.random.default_rng(seed)
    pot_e = cur_e = 0.0
    for h in range(24):
        pot, p = vgrid.simulate_hour(T, T.net, row.sf[h], row.lf[h], rng)
        pot_e += pot.sum(); cur_e += (pot - p).sum()
    return cur_e / max(pot_e, 1e-9)


if __name__ == "__main__":
    sc = vgrid.scenarios("de")
    row = sc[sc.date == REF_DAY].iloc[0]
    target = curtail_share("oberrhein", vgrid.PV_TO_LOAD_OBERRHEIN, row)
    print(f"target curtailed share (mv_oberrhein original scenario): {target:.4f}")
    out = {"oberrhein": vgrid.PV_TO_LOAD_OBERRHEIN, "_target_share": target, "_ref_day": REF_DAY}
    for name in ["cigre_mv", "kerber_dorf", "kerber_vorstadt"]:
        lo, hi = 0.05, 60.0
        for _ in range(14):                       # geometric bisection on the ratio
            mid = float(np.sqrt(lo * hi))
            s = curtail_share(name, mid, row)
            if s < target: lo = mid
            else: hi = mid
        r = float(np.sqrt(lo * hi))
        out[name] = r
        print(f"{name}: ratio {r:.3f}  -> curtailed share {curtail_share(name, r, row):.4f}", flush=True)
    json.dump(out, open(vgrid.RATIO_FILE, "w"), indent=1)
