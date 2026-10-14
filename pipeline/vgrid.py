"""
VIDYUT core: topologies, real-data scenarios, and the checkpointed hourly AC-power-flow simulator.

REAL:      grid topologies + impedances (pandapower benchmark nets), AC power flow (Newton-Raphson),
           hourly solar + demand time series (OPSD Germany 2015-2019 / NASA POWER India 2015-2020).
ASSUMED:   PV capacity (scaled to one common PV-to-peak-load ratio on every topology),
           per-device +/-8% / +/-5% jitter, the 1.05 pu / 100% loading curtailment rule.
"""
import os, warnings
import numpy as np
import pandas as pd
import networkx as nx
import pandapower as pp
import pandapower.networks as pn

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # project root (this file lives in pipeline/)
DATA = os.path.join(HERE, "data")
CKPT = os.path.join(HERE, "checkpoints")
os.makedirs(CKPT, exist_ok=True)

TOPOLOGIES = ["oberrhein", "cigre_mv", "kerber_dorf", "kerber_vorstadt"]
DATASETS = ["de", "in"]
# PV capacity as a multiple of the network's total nominal load. mv_oberrhein at the original 5x scaling:
PV_TO_LOAD_OBERRHEIN = 22.07 * 5.0 / 61.86     # = 1.784, the original 5x scenario on mv_oberrhein
V_MAX = 1.05
RATIO_FILE = os.path.join(DATA, "pv_ratios.json")


def pv_ratio(name):
    """PV nameplate / total nominal load for a topology. Calibrated per topology by calibrate_pv.py so every
    grid sits at the same *stress level* (same curtailed share of potential PV energy on a reference
    summer day) as the original mv_oberrhein scenario. An assumption, documented in the README."""
    import json
    if os.path.exists(RATIO_FILE):
        r = json.load(open(RATIO_FILE))
        if name in r:
            return r[name]
    return PV_TO_LOAD_OBERRHEIN


# ------------------------------------------------------------------ topologies
def load_topology(name, ratio=None):
    """Return a fresh pandapower net with PV sgens scaled to `ratio` x total nominal load."""
    PV_TO_LOAD = pv_ratio(name) if ratio is None else ratio
    if name == "oberrhein":
        net = pn.mv_oberrhein(scenario="generation")
    elif name == "cigre_mv":
        net = pn.create_cigre_network_mv(with_der="pv_wind")
        net.sgen = net.sgen[net.sgen.type == "PV"].copy()      # PV only; drop the single wind unit
    elif name == "kerber_dorf":
        net = pn.create_kerber_dorfnetz()
    elif name == "kerber_vorstadt":
        net = pn.create_kerber_vorstadtnetz_kabel_1()
    else:
        raise KeyError(name)
    total_load = net.load.p_mw.sum()
    if len(net.sgen):
        net.sgen["p_mw"] = net.sgen.p_mw * (PV_TO_LOAD * total_load / net.sgen.p_mw.sum())
    else:
        # Kerber nets ship with no generation: rooftop PV on ~50% of load buses (seeded), sized
        # proportionally to the load at that bus. ASSUMPTION, not data.
        r = np.random.default_rng(7)
        lb = net.load.groupby("bus").p_mw.sum()
        chosen = lb.index[r.random(len(lb)) < 0.5]
        w = lb.loc[chosen] / lb.loc[chosen].sum()
        for b, wt in w.items():
            pp.create_sgen(net, bus=int(b), p_mw=float(PV_TO_LOAD * total_load * wt), q_mvar=0.0, name="rooftop PV", type="PV")
    return net


class Topo:
    """Dense bus indexing + graph helpers around a pandapower net."""

    def __init__(self, name, ratio=None):
        self.name = name
        self.net = load_topology(name, ratio)
        net = self.net
        self.bus_ids = sorted(net.bus.index.tolist())
        self.pos = {b: i for i, b in enumerate(self.bus_ids)}
        self.n_bus = len(self.bus_ids)
        self.n_line = len(net.line)
        self.line_from = np.array([self.pos[int(b)] for b in net.line.from_bus])
        self.line_to = np.array([self.pos[int(b)] for b in net.line.to_bus])
        self.sgen_base = net.sgen.p_mw.values.copy()
        self.load_base = net.load.p_mw.values.copy()
        self.sgen_bus = np.array([self.pos[int(b)] for b in net.sgen.bus])
        self.load_bus = np.array([self.pos[int(b)] for b in net.load.bus])
        G = nx.Graph()
        G.add_nodes_from(range(self.n_bus))
        for li, (a, b) in enumerate(zip(self.line_from, self.line_to)):
            G.add_edge(int(a), int(b), line=li)
        for _, r in net.trafo.iterrows():
            G.add_edge(self.pos[int(r.hv_bus)], self.pos[int(r.lv_bus)], line=None)
        self.G = G                                   # full physical graph (all lines, switches ignored)
        A = nx.to_numpy_array(G, nodelist=range(self.n_bus))
        Ah = A + np.eye(self.n_bus)
        d = 1.0 / np.sqrt(Ah.sum(1))
        self.A_norm = (d[:, None] * Ah) * d[None, :]  # GCN propagation matrix
        M = np.zeros((self.n_bus, self.n_line))
        M[self.line_from, np.arange(self.n_line)] = 1
        M[self.line_to, np.arange(self.n_line)] = 1
        self.M = M
        self.deg_lines = np.maximum(M.sum(1), 1)


# ------------------------------------------------------------------ real-data scenarios
def scenarios(dataset):
    """
    Returns DataFrame: one row per fully-observed real day with arrays sf[24] (solar 0..1) and lf[24] (load 0..1).
    'de': OPSD Germany hourly solar capacity factor + hourly load, 2015-2019 (capacity series ends 2019).
    'in': NASA POWER hourly irradiance at a Rajasthan site (real, India) -> PV factor; demand = OPSD Germany
          hourly load (NOT Indian; Grid-India hourly demand was unreachable) — a hybrid, flagged in the README.
    """
    de = pd.read_csv(os.path.join(DATA, "de_hourly_2015_2020.csv"), parse_dates=["utc"])
    de["utc"] = de.utc.dt.tz_localize(None)          # timestamps are UTC; keep naive UTC clock hours
    de = de.set_index("utc")
    load = de.load_mw
    lf_all = (load / load.max()).clip(0, 1)
    if dataset == "de":
        cf = de.solar_cf
        sf_all = (cf / cf.quantile(0.999)).clip(0, 1)
    elif dataset == "in":
        n = pd.read_csv(os.path.join(DATA, "in_solar_nasapower_hourly.csv"), parse_dates=["utc"]).set_index("utc")
        tcell = n.t2m_c + 0.03 * n.ghi_wm2
        cf = (n.ghi_wm2 / 1000.0) * (1 - 0.004 * (tcell - 25.0)) * 0.86   # simple PV model, PR 0.86
        cf = cf.clip(lower=0)
        sf_all = (cf / cf.quantile(0.999)).clip(0, 1)
        sf_all.index = sf_all.index + pd.Timedelta(hours=5.5)             # UTC -> IST
        sf_all.index = sf_all.index.floor("h")
        sf_all = sf_all[~sf_all.index.duplicated()]
    else:
        raise KeyError(dataset)
    df = pd.DataFrame({"sf": sf_all, "lf": lf_all}).dropna()
    df["date"] = df.index.date
    df["hour"] = df.index.hour
    rows = []
    for d, g in df.groupby("date"):
        if len(g) == 24 and (g.hour.values == np.arange(24)).all():
            rows.append({"date": str(d), "sf": g.sf.values.astype(np.float64), "lf": g.lf.values.astype(np.float64)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ hourly simulation
def simulate_hour(T, net, sf, lf, rng):
    """One hour: set potential gen + load, run the local voltage/thermal curtailment loop with real AC PF."""
    net.sgen["p_mw"] = T.sgen_base * sf * rng.uniform(0.92, 1.08, size=len(T.sgen_base))
    net.load["p_mw"] = T.load_base * lf * rng.uniform(0.95, 1.05, size=len(T.load_base))
    potential = net.sgen["p_mw"].values.copy()
    p = net.sgen["p_mw"].values.copy()
    ok = False
    for _ in range(6):
        net.sgen["p_mw"] = p
        try:
            pp.runpp(net, algorithm="nr", init="results" if ok else "auto")
            ok = True
        except Exception:
            p = p * 0.7
            ok = False
            continue
        vm = net.res_bus.vm_pu
        ll = net.res_line.loading_percent.values
        viol = np.zeros(len(p), dtype=bool)
        sb = net.sgen.bus.values
        viol |= (vm.reindex(sb).values > V_MAX)
        over = np.where(ll > 100)[0]
        if len(over):
            ends = set(net.line.from_bus.values[over]) | set(net.line.to_bus.values[over])
            viol |= np.isin(sb, list(ends))
        if not viol.any():
            break
        p = np.where(viol, p * 0.85, p)
    net.sgen["p_mw"] = p
    return potential, p


def sim_chunk(args):
    """Worker: simulate a chunk of days. Result is checkpointed to disk; existing chunks are skipped."""
    topo_name, dataset, chunk_id, day_lo, day_hi = args
    path = os.path.join(CKPT, f"sim_{topo_name}_{dataset}_{chunk_id:03d}.npz")
    if os.path.exists(path):
        return path, 0.0
    import time
    t0 = time.time()
    T = Topo(topo_name)
    net = T.net
    sc = scenarios(dataset)
    days = sc.iloc[day_lo:day_hi]
    nb, nl = T.n_bus, T.n_line
    nh = len(days) * 24
    vm = np.zeros((nh, nb), np.float32); curt = np.zeros((nh, nb), np.float32)
    pot = np.zeros((nh, nb), np.float32); ld = np.zeros((nh, nb), np.float32); ll = np.zeros((nh, nl), np.float32)
    k = 0
    for di, (_, row) in enumerate(days.iterrows()):
        rng = np.random.default_rng(1000 * (day_lo + di) + 17)
        for h in range(24):
            potential, p = simulate_hour(T, net, row.sf[h], row.lf[h], rng)
            vm[k] = net.res_bus.loc[T.bus_ids].vm_pu.values
            ll[k] = np.nan_to_num(net.res_line.loading_percent.values, nan=0.0)
            np.add.at(pot[k], T.sgen_bus, potential)
            np.add.at(curt[k], T.sgen_bus, np.maximum(potential - p, 0))
            np.add.at(ld[k], T.load_bus, net.load.p_mw.values)
            k += 1
    tmp = path + ".tmp.npz"
    np.savez_compressed(tmp, vm=vm, curt=curt, pot=pot, load=ld, ll=ll, dates=np.array(days.date.tolist()))
    os.replace(tmp, path)
    return path, time.time() - t0


def load_sim(topo_name, dataset):
    files = sorted(f for f in os.listdir(CKPT) if f.startswith(f"sim_{topo_name}_{dataset}_") and f.endswith(".npz") and ".tmp" not in f)
    parts = [np.load(os.path.join(CKPT, f)) for f in files]
    out = {k: np.concatenate([p[k] for p in parts]) for k in ("vm", "curt", "pot", "load", "ll", "dates")}
    return out
