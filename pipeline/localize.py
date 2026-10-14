"""
PRODUCT 2 — fault / theft localization by fingerprint matching, evaluated on real AC power flow.

An unexplained extra draw at a bus perturbs voltage magnitude (dV), voltage angle (dTheta) and line currents (dI)
everywhere. The perturbation pattern is set by the grid's real impedances, so it identifies the origin.

Dictionary: one AC-power-flow probe per bus, built AT THE PRE-FAULT OPERATING STATE (aggregate PV output and load
level, as a SCADA/state estimator would know them). A first version used coarse state bins and was measurably
wrong on PV-heavy grids: exact-bus accuracy fell from ~98% to ~41% when the dictionary's solar level was off by
0.1. The trial's real state additionally has per-device jitter (PV +/-8%, load +/-5%) that the dictionary does
not know, and trials use RANDOM REAL OPERATING STATES (real hourly solar + demand from 2019).

Feature sets (reported separately so improvements are attributable):
  V    : dV only (the original prototype's method)
  VTI  : dV + dTheta + dI, each divided by its assumed sensor noise (whitening), cosine-matched
Assumed sensor noise (ASSUMPTIONS about a sensor suite, not measured): 0.0005 pu, 0.02 deg, 0.5 A.
"""
import numpy as np
import pandapower as pp
import vgrid

SIG_V, SIG_TH, SIG_I = 5e-4, 0.02, 0.5
SEV_LO, SEV_HI = 0.005, 0.02          # anomaly size as a fraction of the network's total nominal load


class Localizer:
    def __init__(self, T):
        self.T = T
        self.net = T.net
        self.total_load = float(T.load_base.sum())
        self.dicts = {}
        self.valid = None

    # -- operating point + fault application --------------------------------------------------
    def set_op(self, sf, lf, rng=None):
        T, net = self.T, self.net
        if rng is None:
            net.sgen["p_mw"] = T.sgen_base * sf
            net.load["p_mw"] = T.load_base * lf
        else:
            net.sgen["p_mw"] = T.sgen_base * sf * rng.uniform(0.92, 1.08, len(T.sgen_base))
            net.load["p_mw"] = T.load_base * lf * rng.uniform(0.95, 1.05, len(T.load_base))

    def measure(self):
        net, T = self.net, self.T
        pp.runpp(net, algorithm="nr")
        v = net.res_bus.loc[T.bus_ids].vm_pu.values.copy()
        th = net.res_bus.loc[T.bus_ids].va_degree.values.copy()
        i = np.nan_to_num(net.res_line.i_ka.values * 1000.0)          # amps
        return v, th, i

    def signature(self, bus_pos, mw, cos_phi_q=0.3, base=None):
        """pre-fault minus during-fault measurements for an extra draw of `mw` at dense bus position."""
        v0, th0, i0 = base if base is not None else self.measure()
        bid = self.T.bus_ids[bus_pos]
        idx = pp.create_load(self.net, bus=bid, p_mw=mw, q_mvar=mw * cos_phi_q, name="anomaly")
        try:
            v1, th1, i1 = self.measure()
        finally:
            self.net.load.drop(index=idx, inplace=True)
        return v0 - v1, th0 - th1, i1 - i0

    @staticmethod
    def features(dv, dth, di, kind):
        if kind == "V":
            return dv / SIG_V
        return np.concatenate([dv / SIG_V, dth / SIG_TH, di / SIG_I])

    # -- dictionary at a given pre-fault state ------------------------------------------------
    def build_state(self, sf, lf, kinds=("V", "VTI")):
        """Fingerprint dictionary for the pre-fault state (sf, lf). Returns ({kind: (n_bus, dim) unit rows}, valid_mask)."""
        n = self.T.n_bus
        mw = 0.0125 * self.total_load
        self.set_op(sf, lf)
        base = self.measure()
        F = {k: [None] * n for k in kinds}
        ok = np.ones(n, bool)
        for b in range(n):
            try:
                dv, dth, di = self.signature(b, mw, base=base)
                for k in kinds:
                    f = self.features(dv, dth, di, k)
                    nrm = np.linalg.norm(f)
                    if not np.isfinite(nrm) or nrm < 1e-9:
                        raise ValueError
                    F[k][b] = f / nrm
            except Exception:
                ok[b] = False
        D = {}
        for k in kinds:
            dim = next(x for x in F[k] if x is not None).shape[0]
            D[k] = np.array([x if x is not None else np.zeros(dim) for x in F[k]])
        return D, ok

    @staticmethod
    def rank(obs_feat, D, kind, valid, mask=None):
        """Bus positions ranked best-first by cosine similarity to the dictionary rows (optionally sensor-masked)."""
        M = D[kind] if mask is None else D[kind] * mask[None, :]
        o = obs_feat if mask is None else obs_feat * mask
        o = o / (np.linalg.norm(o) + 1e-12)
        s = (M @ o) / (np.linalg.norm(M, axis=1) + 1e-12)
        s[~valid] = -np.inf
        return np.argsort(-s), s

    # -- one noisy trial -----------------------------------------------------------------------
    def trial(self, true_bus, sf, lf, rng, sev=None):
        self.set_op(sf, lf, rng)
        mw = (rng.uniform(SEV_LO, SEV_HI) if sev is None else sev) * self.total_load * lf
        dv, dth, di = self.signature(true_bus, mw)
        dv = dv + rng.normal(0, SIG_V, dv.shape)
        dth = dth + rng.normal(0, SIG_TH, dth.shape)
        di = di + rng.normal(0, SIG_I, di.shape)
        return dv, dth, di, mw


def _state_worker(args):
    """One operating state: build the dictionary there, then run `per_state` noisy trials."""
    topo, sf, lf, seed, per_state, sensor_cover = args
    T = vgrid.Topo(topo)
    loc = Localizer(T)
    D, valid = loc.build_state(sf, lf)
    rng = np.random.default_rng(seed)
    cand = np.where(valid)[0]
    rows = []
    for _ in range(per_state):
        tb = int(rng.choice(cand))
        try:
            dv, dth, di, mw = loc.trial(tb, sf, lf, rng)
        except Exception:
            continue
        rec = {"true": tb, "sf": sf, "lf": lf}
        for cov in sensor_cover:
            mb = rng.random(T.n_bus) < cov          # random subset of buses / lines is instrumented
            ml = rng.random(T.n_line) < cov
            for kind in ("V", "VTI"):
                if kind == "V":
                    f = loc.features(dv * mb, dth, di, "V"); mask = mb.astype(float)
                else:
                    f = loc.features(dv * mb, dth * mb, di * ml, "VTI"); mask = np.r_[mb, mb, ml].astype(float)
                order, _ = loc.rank(f, D, kind, valid, mask)
                rec[f"{kind}@{int(cov*100)}"] = order[:5].tolist()
        rows.append(rec)
    return rows


def evaluate(topo, n_states=30, per_state=10, seed=5, sensor_cover=(1.0, 0.3), workers=4):
    """n_states random REAL 2019 (day, hour) operating states x per_state random faults each."""
    import networkx as nx
    from multiprocessing import Pool
    T = vgrid.Topo(topo)
    sc = vgrid.scenarios("de")
    sc = sc[sc.date >= "2019-01-01"].reset_index(drop=True)
    rng = np.random.default_rng(seed)
    jobs = []
    for k in range(n_states):
        d = sc.iloc[int(rng.integers(len(sc)))]
        h = int(rng.integers(24))
        jobs.append((topo, float(d.sf[h]), float(d.lf[h]), 1000 + k, per_state, sensor_cover))
    with Pool(workers) as pool:
        rows = [r for part in pool.imap(_state_worker, jobs) for r in part]
    G = T.G
    sp_cache = {}
    out = {"n": len(rows), "n_states": n_states, "per_state": per_state, "results": {}}
    for cov in sensor_cover:
        for kind in ("V", "VTI"):
            key = f"{kind}@{int(cov*100)}"
            hops = []; top3 = 0
            for r in rows:
                p = r[key][0]
                k2 = (r["true"], p)
                if k2 not in sp_cache:
                    sp_cache[k2] = nx.shortest_path_length(G, r["true"], p)
                hops.append(sp_cache[k2])
                top3 += int(r["true"] in r[key][:3])
            hops = np.array(hops)
            out["results"][key] = {"exact": float((hops == 0).mean()), "within1": float((hops <= 1).mean()),
                                    "within2": float((hops <= 2).mean()), "within5": float((hops <= 5).mean()),
                                    "top3": top3 / len(rows), "mean_hops": float(hops.mean())}
    out["rows"] = rows
    return out
