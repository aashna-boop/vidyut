"""
PRODUCT 1 — next-hour curtailment prediction at every bus.

Data: hourly AC-power-flow simulation driven by real hourly solar + demand (see vgrid.py).
Split (chronological, no leakage): train 2015-2017, validation 2018 (model selection/threshold), TEST 2019.
Pairs are built inside a day (hour t -> t+1); the 23h->0h boundary is night and never curtailed.

Inputs per bus at hour t: PV potential, voltage, load, mean loading of incident lines, curtailment now (lag),
PV ramp (t vs t-1), hour-of-day and day-of-year sin/cos. Target: curtailment at t+1 (MW).

Models, all evaluated on the same held-out year and reported side by side (nothing is hidden):
  baselines : mean, persistence (curtailment_t+1 = curtailment_t)
  GCN       : 2-layer graph conv net with skip connection, hand-written numpy forward/backward + Adam
  GBM-graph : HistGradientBoosting on node features + neighbour-aggregated features (A_norm X, A_norm^2 X)
  GBM-nolag : same GBM WITHOUT the curtailment-now feature, to show how much skill is more than persistence
"""
import json, os, time
import numpy as np
import vgrid

HERE = vgrid.HERE
RES = os.path.join(HERE, "results")
os.makedirs(RES, exist_ok=True)
EPS = 0.01           # MW: network-hour counts as a curtailment event above this


def build_dataset(T, sim):
    dates = np.array(sim["dates"])
    D = len(dates)
    H = D * 24
    nb = T.n_bus
    vm, curt, pot, ld = (sim[k].reshape(D, 24, nb) for k in ("vm", "curt", "pot", "load"))
    ll = sim["ll"].reshape(D, 24, -1)
    inc = np.einsum("bl,dhl->dhb", T.M, ll) / T.deg_lines[None, None, :] / 100.0
    ramp = np.zeros_like(pot); ramp[:, 1:] = pot[:, 1:] - pot[:, :-1]
    hr = np.arange(24)
    day_of_year = (np.array(dates, dtype="datetime64[D]") - np.array(dates, dtype="datetime64[Y]").astype("datetime64[D]")).astype(int)
    feats = [pot, vm, ld, inc, curt, ramp]
    F = np.stack(feats, -1)                                           # (D,24,nb,6)
    cal = np.zeros((D, 24, nb, 4), np.float32)
    cal[..., 0] = np.sin(2 * np.pi * hr / 24)[None, :, None]
    cal[..., 1] = np.cos(2 * np.pi * hr / 24)[None, :, None]
    cal[..., 2] = np.sin(2 * np.pi * day_of_year / 365.25)[:, None, None]
    cal[..., 3] = np.cos(2 * np.pi * day_of_year / 365.25)[:, None, None]
    F = np.concatenate([F, cal], -1).astype(np.float32)               # (D,24,nb,10)
    X = F[:, :-1].reshape(-1, nb, F.shape[-1])                        # hour t
    Y = curt[:, 1:].reshape(-1, nb)                                   # curtailment at t+1
    day_idx = np.repeat(np.arange(D), 23)
    years = np.array([int(d[:4]) for d in dates])[day_idx]
    return X, Y, years, dates, day_idx


def metrics(y, p, ptot_thr=None):
    """y,p: (N, nb) actual/predicted curtailment MW. Returns dict of honest metrics."""
    p = np.clip(p, 0, None)
    out = {"mae_per_bus": float(np.abs(y - p).mean()), "rmse_per_bus": float(np.sqrt(((y - p) ** 2).mean()))}
    yt, pt = y.sum(1), p.sum(1)
    out["mae_network_total_mw"] = float(np.abs(yt - pt).mean())
    out["corr_network_total"] = float(np.corrcoef(yt, pt)[0, 1]) if yt.std() > 0 and pt.std() > 0 else float("nan")
    if ptot_thr is not None:
        ev, pr = yt > EPS, pt > ptot_thr
        tp = int((ev & pr).sum()); fp = int((~ev & pr).sum()); fn = int((ev & ~pr).sum())
        out["event_precision"] = tp / max(tp + fp, 1); out["event_recall"] = tp / max(tp + fn, 1)
        out["event_f1"] = 2 * tp / max(2 * tp + fp + fn, 1)
        out["event_rate_actual"] = float(ev.mean())
    return out


def best_thr(y, p):
    yt, pt = y.sum(1), np.clip(p, 0, None).sum(1)
    ev = yt > EPS
    best, bt = -1, EPS
    for thr in np.unique(np.quantile(pt, np.linspace(0.5, 0.999, 200))):
        pr = pt > thr
        tp = (ev & pr).sum(); fp = (~ev & pr).sum(); fn = (ev & ~pr).sum()
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > best:
            best, bt = f1, float(thr)
    return bt


# ----------------------------------------------------------------------------- numpy GCN
class GCN:
    """2-layer graph conv net + skip connection. float32; graph propagation is one BLAS matmul (n x n) @ (n x B*f)."""

    def __init__(self, A, fin, hid=32, seed=0):
        r = np.random.default_rng(seed)
        self.A = A.astype(np.float32)
        f32 = lambda a: a.astype(np.float32)
        self.p = {"W1": f32(r.normal(0, 0.3, (fin, hid))), "Ws": f32(r.normal(0, 0.3, (fin, hid))), "b1": np.zeros(hid, np.float32),
                  "W2": f32(r.normal(0, 0.3, (hid, 1))), "Wo": f32(r.normal(0, 0.3, (hid, 1))), "b2": np.zeros(1, np.float32)}
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.t = 0

    def prop(self, X):                       # A @ X for every sample in the batch
        B, n, f = X.shape
        return (self.A @ X.transpose(1, 0, 2).reshape(n, B * f)).reshape(n, B, f).transpose(1, 0, 2)

    def forward(self, X):
        p = self.p
        AX = self.prop(X)
        Z1 = AX @ p["W1"] + X @ p["Ws"] + p["b1"]
        H1 = np.maximum(Z1, 0)
        AH = self.prop(H1)
        out = (AH @ p["W2"] + H1 @ p["Wo"] + p["b2"])[..., 0]
        return out, (X, AX, Z1, H1, AH)

    def step(self, X, y, lr):
        p = self.p
        out, (X, AX, Z1, H1, AH) = self.forward(X)
        B, n = y.shape
        err = out - y
        loss = float((err ** 2).mean())
        d = ((2.0 / (B * n)) * err[..., None]).astype(np.float32)
        g = {"W2": np.einsum("bih,bio->ho", AH, d), "Wo": np.einsum("bih,bio->ho", H1, d), "b2": d.sum((0, 1))}
        dH1 = self.prop(d @ p["W2"].T) + d @ p["Wo"].T           # A is symmetric
        dZ1 = dH1 * (Z1 > 0)
        g["W1"] = np.einsum("bif,bih->fh", AX, dZ1); g["Ws"] = np.einsum("bif,bih->fh", X, dZ1); g["b1"] = dZ1.sum((0, 1))
        self.t += 1
        for k in p:
            self.m[k] = 0.9 * self.m[k] + 0.1 * g[k]
            self.v[k] = 0.999 * self.v[k] + 0.001 * g[k] ** 2
            mh = self.m[k] / (1 - 0.9 ** self.t); vh = self.v[k] / (1 - 0.999 ** self.t)
            p[k] -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
        return loss

    def predict(self, X, bs=256):
        return np.concatenate([self.forward(X[i:i + bs])[0] for i in range(0, len(X), bs)])


def train_gcn(T, Xtr, Ytr, Xva, Yva, epochs=30, bs=128, lr=3e-3, log=print):
    mu = Xtr.reshape(-1, Xtr.shape[-1]).mean(0); sd = Xtr.reshape(-1, Xtr.shape[-1]).std(0) + 1e-6
    ys = float(Ytr.std() + 1e-9)
    nz = lambda X: ((X - mu) / sd).astype(np.float32)
    net = GCN(T.A_norm, Xtr.shape[-1])
    r = np.random.default_rng(0)
    best, best_p, hist = 1e9, None, []
    for ep in range(epochs):
        perm = r.permutation(len(Xtr)); tl = []
        for s in range(0, len(perm), bs):
            i = perm[s:s + bs]
            tl.append(net.step(nz(Xtr[i]), (Ytr[i] / ys).astype(np.float32), lr))
        pv = net.predict(nz(Xva)) * ys
        vmse = float(((pv - Yva) ** 2).mean())
        hist.append((ep, float(np.mean(tl)), vmse))
        if vmse < best:
            best, best_p = vmse, {k: v.copy() for k, v in net.p.items()}
        if ep % 5 == 0 or ep == epochs - 1:
            log(f"    GCN epoch {ep:2d} train MSE(scaled) {np.mean(tl):.4f}  val MSE {vmse:.6f}")
    net.p = best_p
    return (lambda X: np.clip(net.predict(nz(X)) * ys, 0, None)), hist


# ----------------------------------------------------------------------------- GBM on graph-aggregated features
def gbm_features(T, X, drop_lag=False):
    A = T.A_norm
    A2 = A @ A
    A1X = np.einsum("ij,bjf->bif", A, X)
    A2X = np.einsum("ij,bjf->bif", A2, X)
    tot = X[:, :, :1].sum(1, keepdims=True).repeat(X.shape[1], 1)     # network-wide PV potential
    F = np.concatenate([X, A1X, A2X, tot], -1)
    if drop_lag:
        cols = [i for i in range(F.shape[-1]) if not (i < 3 * X.shape[-1] and i % X.shape[-1] == 4)]
        F = F[..., cols]
    return F


def train_gbm(T, Xtr, Ytr, drop_lag, max_rows=800_000, seed=0):
    from sklearn.ensemble import HistGradientBoostingRegressor
    pv_mask = np.zeros(T.n_bus, bool); pv_mask[T.sgen_bus] = True
    F = gbm_features(T, Xtr, drop_lag)[:, pv_mask]                    # only PV buses can be curtailed
    y = Ytr[:, pv_mask]
    F = F.reshape(-1, F.shape[-1]); y = y.reshape(-1)
    r = np.random.default_rng(seed)
    if len(y) > max_rows:
        keep = r.random(len(y)) < max_rows / len(y)
        F, y = F[keep], y[keep]
    m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08, max_leaf_nodes=48, l2_regularization=1.0,
                                       random_state=seed)
    m.fit(F, y)

    def predict(X):
        Fx = gbm_features(T, X, drop_lag)[:, pv_mask]
        n = Fx.shape[0]
        pr = m.predict(Fx.reshape(-1, Fx.shape[-1])).reshape(n, -1)
        out = np.zeros((n, T.n_bus)); out[:, pv_mask] = np.clip(pr, 0, None)
        return out
    return predict


def run(topo_name, dataset="de", log=print):
    outf = os.path.join(RES, f"p1_{topo_name}_{dataset}.json")
    T = vgrid.Topo(topo_name)
    sim = vgrid.load_sim(topo_name, dataset)
    X, Y, years, dates, day_idx = build_dataset(T, sim)
    tr, va, te = years <= 2017, years == 2018, years == 2019
    log(f"  [{topo_name}/{dataset}] {len(dates)} real days | train {tr.sum()//23} d, val {va.sum()//23} d, test {te.sum()//23} d | "
        f"curtailment hours in test: {(Y[te].sum(1) > EPS).mean()*100:.1f}%")
    res = {"topology": topo_name, "dataset": dataset, "n_days": int(len(dates)), "train_days": int(tr.sum() // 23),
           "val_days": int(va.sum() // 23), "test_days": int(te.sum() // 23), "n_bus": T.n_bus,
           "pv_mw": float(T.sgen_base.sum()), "pv_to_load": float(T.sgen_base.sum() / T.load_base.sum()),
           "test_year": 2019, "models": {}}
    preds = {}
    preds["mean"] = lambda Z: np.full((len(Z), T.n_bus), Y[tr].mean())
    preds["persistence"] = lambda Z: Z[:, :, 4].copy()
    t0 = time.time()
    preds["GCN"], hist = train_gcn(T, X[tr], Y[tr], X[va], Y[va], log=log)
    res["gcn_history"] = hist
    log(f"    GCN trained in {time.time()-t0:.0f}s"); t0 = time.time()
    preds["GBM-graph"] = train_gbm(T, X[tr], Y[tr], drop_lag=False)
    preds["GBM-nolag"] = train_gbm(T, X[tr], Y[tr], drop_lag=True)
    log(f"    GBMs trained in {time.time()-t0:.0f}s")
    for name, f in preds.items():
        pva = f(X[va]); thr = best_thr(Y[va], pva)
        m = metrics(Y[te], f(X[te]), thr)
        m["event_thr_from_validation_mw"] = thr
        res["models"][name] = m
        log(f"    {name:12s} test MAE {m['mae_per_bus']:.5f}  RMSE {m['rmse_per_bus']:.5f}  net-total corr {m['corr_network_total']:.3f}  "
            f"event F1 {m['event_f1']:.3f} (P {m['event_precision']:.2f} R {m['event_recall']:.2f})")
    ms = res["models"]
    best = min((k for k in ms if k not in ("mean", "persistence")), key=lambda k: ms[k]["rmse_per_bus"])
    res["best_model"] = best
    res["beats_mean_mae"] = bool(ms[best]["mae_per_bus"] < ms["mean"]["mae_per_bus"])
    res["beats_persistence_rmse"] = bool(ms[best]["rmse_per_bus"] < ms["persistence"]["rmse_per_bus"])
    res["beats_persistence_mae"] = bool(ms[best]["mae_per_bus"] < ms["persistence"]["mae_per_bus"])
    # demo week from the TEST year for the 3D view: (168 h) actual vs best-model next-hour prediction
    wk = np.where(dates == "2019-06-03")[0]
    if len(wk) and wk[0] + 7 <= len(dates):
        d0 = int(wk[0]); sl = np.arange(d0, d0 + 7)
        Xw = X[np.isin(day_idx, sl)]
        pw = preds[best](Xw).reshape(7, 23, T.n_bus)
        pred_full = np.zeros((7, 24, T.n_bus)); pred_full[:, 1:] = pw          # prediction made for hour h (from h-1)
        res["_demo"] = {"dates": dates[sl].tolist(), "pred": pred_full.reshape(168, -1).astype(np.float32),
                        "actual": sim["curt"].reshape(-1, 24, T.n_bus)[sl].reshape(168, -1),
                        "ll": sim["ll"].reshape(-1, 24, T.n_line)[sl].reshape(168, -1), "vm": sim["vm"].reshape(-1, 24, T.n_bus)[sl].reshape(168, -1)}
        np.savez_compressed(os.path.join(RES, f"demo_{topo_name}_{dataset}.npz"), **{k: v for k, v in res["_demo"].items() if k != "dates"},
                            dates=np.array(res["_demo"]["dates"]))
    res.pop("_demo", None)
    json.dump(res, open(outf, "w"), indent=1)
    return res


if __name__ == "__main__":
    import sys
    topos = sys.argv[1].split(",") if len(sys.argv) > 1 else vgrid.TOPOLOGIES
    ds = sys.argv[2] if len(sys.argv) > 2 else "de"
    for t in topos:
        run(t, ds)
