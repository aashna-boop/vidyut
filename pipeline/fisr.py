"""
FISR — Fault Isolation and Service Restoration on the real switch model of each topology.

Sequence for a fault at true bus f (all steps verified by real AC power flow, pandapower):
  0 PRE-FAULT      normal state.
  1 FAULT + TRIP   the feeder-head breaker (first line out of the substation on the path to f) opens, the whole
                   radial feeder downstream loses supply.
  2 LOCALIZE       Vidyut's fingerprint model ranks candidate buses from the noisy sag signature.
  3 ISOLATE        open the sectionalising switches around the *predicted* bus's zone. If f is not inside the
                   isolated zone the fault is still there: reclose-into-fault -> trip again -> revert -> try
                   the next-ranked candidate (max 3 attempts, mirrors utility reclose-lockout practice).
  4 UPSTREAM       feeder-head breaker recloses, buses between substation and the zone are re-energised.
  5 TIES           buses stranded downstream of the zone are re-supplied by closing normally-open tie switches.
                   Each candidate tie is evaluated by AC power flow; a tie with no voltage/thermal violation and
                   maximum restored load wins.

REAL:    switch positions & tie switches of oberrhein / CIGRE MV (from the published models); AC power flow.
ASSUMED: (a) CIGRE MV ships switches only on its 3 tie lines and the Kerber nets ship with NONE, so for those a
         sectionalising switch is assumed on every other line (isolation possible). CIGRE's 3 tie switches are real;
         Kerber has no ties at all, so its downstream customers CANNOT be restored;
         (b) a fault is modelled as a large abnormal draw at the bus (same as the localization model);
         (c) the peak-load snapshot is the operating point (worst case for restoration headroom).
"""
import numpy as np
import networkx as nx
import pandapower as pp

V_LO, V_HI, LOAD_LIM = 0.95, 1.05, 100.0
MAX_ATTEMPTS = 3


class FISR:
    def __init__(self, T, sf, lf):
        self.T = T
        self.net = T.net
        net = self.net
        # oberrhein has a full real switch model; CIGRE MV only has switches on its 3 tie lines and the Kerber nets
        # have none, so for those we ASSUME a sectionalising switch at every line that lacks one (ties stay real).
        self.assume_sectionalisers = T.name != "oberrhein"
        net.sgen["p_mw"] = T.sgen_base * sf
        net.load["p_mw"] = T.load_base * lf
        self.sources = [T.pos[int(b)] for b in net.ext_grid.bus]
        self.load_by_bus = np.zeros(T.n_bus)
        np.add.at(self.load_by_bus, T.load_bus, net.load.p_mw.values)
        self.total_load = float(self.load_by_bus.sum())
        self.base_open_sw = set(net.switch.index[~net.switch.closed]) if len(net.switch) else set()
        self._orig_service = net.line.in_service.copy()
        lp = {lab: i for i, lab in enumerate(net.line.index)}   # line label -> positional index (labels aren't contiguous)
        self.sw_by_line = {}
        for si, r in net.switch.iterrows():
            if r.et == "l":
                self.sw_by_line.setdefault(lp[int(r.element)], {})[T.pos[int(r.bus)]] = si
        # tie lines = lines that have an open switch at baseline (keyed by line position)
        self.ties = {}
        for si in self.base_open_sw:
            r = net.switch.loc[si]
            if r.et == "l":
                self.ties[lp[int(r.element)]] = si

    # ---------------------------------------------------------------- state helpers
    def reset(self):
        net = self.net
        net.line["in_service"] = self._orig_service
        if len(net.switch):
            net.switch["closed"] = ~net.switch.index.isin(self.base_open_sw)

    def line_open(self, li):
        net = self.net
        if not net.line.in_service.iat[li]:
            return True
        for pos, si in self.sw_by_line.get(li, {}).items():
            if not net.switch.closed.at[si]:
                return True
        return False

    def supply_graph(self):
        T, net = self.T, self.net
        g = nx.Graph()
        g.add_nodes_from(range(T.n_bus))
        for li in range(T.n_line):
            if not self.line_open(li):
                g.add_edge(int(T.line_from[li]), int(T.line_to[li]), line=li)
        for ti, r in net.trafo.iterrows():
            if r.in_service:
                g.add_edge(T.pos[int(r.hv_bus)], T.pos[int(r.lv_bus)], line=None)
        return g

    def supplied(self):
        g = self.supply_graph()
        s = set()
        for src in self.sources:
            s |= nx.node_connected_component(g, src)
        return s

    def solve(self, dead_buses=None):
        """AC power flow on the current switch state. Returns metrics dict; buses without supply have NaN results."""
        T, net = self.T, self.net
        try:
            pp.runpp(net, algorithm="nr", init="dc")
        except Exception:
            try:
                pp.runpp(net, algorithm="nr", init="flat", max_iteration=40)
            except Exception:
                return None
        vm = net.res_bus.loc[T.bus_ids].vm_pu.values
        alive = ~np.isnan(vm)
        ll = np.nan_to_num(net.res_line.loading_percent.values, nan=0.0)
        served = float(self.load_by_bus[alive].sum())
        vmv = vm[alive]
        viol = int((vmv > V_HI).sum() + (vmv < V_LO).sum() + (ll > LOAD_LIM).sum())
        return {"alive": alive, "vm": vm, "ll": ll, "served": served,
                "vmin": float(vmv.min()) if len(vmv) else float("nan"),
                "vmax": float(vmv.max()) if len(vmv) else float("nan"),
                "max_loading": float(ll.max()), "violations": viol}

    # ---------------------------------------------------------------- topology logic
    def feeder_head(self, f):
        """First line on the path source->f (skipping trafos). Returns (line, downstream bus set) or (None, whole comp)."""
        g = self.supply_graph()
        best = None
        for src in self.sources:
            if nx.has_path(g, src, f):
                p = nx.shortest_path(g, src, f)
                if best is None or len(p) < len(best):
                    best = p
        if best is None:
            return None, set()
        for a, b in zip(best[:-1], best[1:]):
            li = g.edges[a, b]["line"]
            if li is not None:
                g2 = g.copy(); g2.remove_edge(a, b)
                down = nx.node_connected_component(g2, b) if not nx.has_path(g2, a, b) else set(best[best.index(b):])
                return (li, a, b), down
        return None, set(nx.node_connected_component(g, best[0]))

    def zone(self, seed):
        """Bus set Z that must be de-energised to isolate `seed`, plus the switch operations that do it.
        ops = list of ('sw', switch_idx) or ('line', line_idx) [virtual sectionaliser]."""
        T = self.T
        Z = {seed}
        ops = []
        queue = [seed]
        seen_lines = set()
        while queue:
            x = queue.pop()
            for li in range(T.n_line):
                if li in seen_lines or self.line_open(li):
                    continue
                a, b = int(T.line_from[li]), int(T.line_to[li])
                if x not in (a, b):
                    continue
                seen_lines.add(li)
                y = b if x == a else a
                sw = self.sw_by_line.get(li, {})
                if not sw and self.assume_sectionalisers:
                    ops.append(("line", li))
                elif x in sw:
                    ops.append(("sw", sw[x]))
                elif y in sw:
                    ops.append(("sw", sw[y]))
                else:                       # no switch on either end: line is part of the faulted zone
                    Z.add(y)
                    queue.append(y)
        return Z, ops

    def apply(self, ops, close=False):
        net = self.net
        for kind, idx in ops:
            if kind == "sw":
                net.switch.at[idx, "closed"] = close
            else:
                net.line.at[net.line.index[idx], "in_service"] = close

    def sync(self, hops, head_open, iso=(), ties=()):
        """Derive the whole switch state from explicit lists (no incremental mutation => no drift)."""
        self.reset()
        self.apply(list(iso), close=False)
        if head_open:
            self.apply(hops, close=False)
        self.apply(list(ties), close=True)

    def head_ops(self, head):
        li, a, b = head
        sw = self.sw_by_line.get(li, {})
        if a in sw:
            return [("sw", sw[a])]
        return [("line", li)]

    # ---------------------------------------------------------------- restoration via ties
    def restore_via_ties(self, outage, zone):
        """Greedy, power-flow-verified tie closing for buses stranded downstream. Returns list of tie ops + last metrics."""
        T = self.T
        applied = []
        for _ in range(4):
            sup = self.supplied()
            orphans = {b for b in outage if b not in sup and b not in zone}
            if not orphans or not self.ties:
                break
            cands = []
            for li, si in self.ties.items():
                if self.net.switch.closed.at[si] or not self.net.line.in_service.iat[li]:
                    continue
                a, b = int(T.line_from[li]), int(T.line_to[li])
                if (a in orphans and b in sup) or (b in orphans and a in sup):
                    cands.append((li, si))
            if not cands:
                break
            best = None
            for li, si in cands:
                self.net.switch.at[si, "closed"] = True
                m = self.solve()
                self.net.switch.at[si, "closed"] = False
                if m is None:
                    continue
                key = (m["violations"] > 0, m["violations"], -m["served"])
                if best is None or key < best[0]:
                    best = (key, li, si, m)
            if best is None:
                break
            _, li, si, m = best
            self.net.switch.at[si, "closed"] = True
            applied.append(("sw", si))
        return applied

    # ---------------------------------------------------------------- the full event
    def run_event(self, f, ranked, snapshot_detail=True):
        """f: true fault bus (dense pos). ranked: localization candidates, best first. Returns event dict."""
        T = self.T
        self.reset()
        ev = {"true_bus": int(f), "ranked": [int(x) for x in ranked[:MAX_ATTEMPTS + 2]], "stages": [], "ops": [],
              "attempts": []}
        m0 = self.solve()
        if m0 is None:
            return None

        def stage(name, m, note=""):
            open_lines = [li for li in range(T.n_line) if self.line_open(li)]
            ev["stages"].append({"name": name, "note": note,
                                 "dead": [int(i) for i in np.where(~m["alive"])[0]] if m is not None else [],
                                 "open_lines": open_lines,
                                 "served_mw": round(m["served"], 4) if m else 0.0,
                                 "vmin": None if m is None else round(m["vmin"], 4),
                                 "vmax": None if m is None else round(m["vmax"], 4),
                                 "max_loading": None if m is None else round(m["max_loading"], 1),
                                 "violations": None if m is None else m["violations"]})
        stage("PRE-FAULT", m0, "normal operation, all loads served")
        ev["total_load_mw"] = round(self.total_load, 4)

        head, outage = self.feeder_head(f)
        if head is None:
            ev["outcome"] = "substation_bus"      # no feeder head on the path: needs substation/transmission protection
            self.reset()
            return ev
        hops = self.head_ops(head)
        self.sync(hops, head_open=True)
        m1 = self.solve()
        ev["outage_buses"] = sorted(int(b) for b in outage)
        ev["head_line"] = int(head[0])
        stage("FAULT + TRIP", m1, f"feeder-head breaker (line {head[0]}) trips; {len(outage)} buses de-energised")
        ev["ops"].append({"step": "trip", "line": int(head[0])})

        isolated = False
        tried_zones = []
        for g in ranked:
            if len(ev["attempts"]) >= MAX_ATTEMPTS:
                break
            self.sync(hops, head_open=False)        # zone is planned on the intact (head-closed) network
            Z, iso_ops = self.zone(int(g))
            key = frozenset(Z)
            if key in tried_zones:
                continue
            tried_zones.append(key)
            # physical test: with the feeder head reclosed, is the true fault bus inside the opened zone AND cut off
            # from the substation? (If it were merely stranded downstream, a tie would re-energise the fault.)
            self.sync(hops, head_open=False, iso=iso_ops)
            hit = (f in Z) and (f not in self.supplied())
            ev["attempts"].append({"candidate": int(g), "zone": sorted(int(z) for z in Z), "hit": bool(hit),
                                   "n_switch_ops": len(iso_ops)})
            if hit:
                isolated = True
                ev["zone"] = sorted(int(z) for z in Z)
                ev["iso_ops"] = [{"kind": k, "idx": int(i)} for k, i in iso_ops]
                self.sync(hops, head_open=True, iso=iso_ops)
                mi = self.solve()
                stage("ISOLATED", mi, f"{len(iso_ops)} sectionalising operations open around bus {g}; fault de-energised")
                break
            # reclose into a still-live fault -> trips again -> operators revert and try the next candidate
            self.sync(hops, head_open=True)
            ev["ops"].append({"step": "failed-attempt-reverted", "candidate": int(g)})
        if not isolated:
            ev["outcome"] = "isolation_failed"
            self.sync(hops, head_open=True)
            stage("LOCKOUT", self.solve(), f"fault not isolated in {MAX_ATTEMPTS} attempts; feeder stays de-energised")
            return self._finish(ev, m0)

        Z = set(ev["zone"])
        self.sync(hops, head_open=False, iso=iso_ops)      # upstream: reclose the feeder head
        m4 = self.solve()
        stage("UPSTREAM RESTORED", m4, "feeder-head breaker recloses; substation-side buses re-energised")
        tie_ops = self.restore_via_ties(outage, Z)          # downstream via ties (state left with ties closed)
        m5 = self.solve()
        ev["tie_ops"] = [{"kind": k, "idx": int(i)} for k, i in tie_ops]
        stage("TIES CLOSED", m5, (f"{len(tie_ops)} tie switch(es) closed" if tie_ops else
                                   "no tie switch available in reach — downstream customers stay out"))
        ev["outcome"] = "restored"
        ev["final_metrics"] = {k: m5[k] for k in ("served", "vmin", "vmax", "max_loading", "violations")}
        ev["final_ll"] = [int(round(x)) for x in m5["ll"]]
        ev["final_vm"] = [None if np.isnan(x) else round(float(x), 3) for x in m5["vm"]]
        return self._finish(ev, m0)

    def _finish(self, ev, m0):
        tot = ev["total_load_mw"]
        last = ev["stages"][-1]
        zone_load = sum(self.load_by_bus[b] for b in ev.get("zone", []))
        outage_load = sum(self.load_by_bus[b] for b in ev.get("outage_buses", []))
        avoidable = max(outage_load - zone_load, 0.0)
        restored = max(last["served_mw"] - ev["stages"][1]["served_mw"], 0.0)
        ev["metrics"] = {
            "outage_load_mw": round(float(outage_load), 4),
            "unavoidable_zone_load_mw": round(float(zone_load), 4),
            "restored_mw": round(float(restored), 4),
            "restored_frac_of_avoidable": (round(float(restored / avoidable), 4) if avoidable > 1e-9 else None),
            "final_served_frac": round(last["served_mw"] / tot, 4) if tot else None,
            "attempts": len(ev["attempts"]),
            "first_attempt_hit": bool(ev["attempts"][0]["hit"]) if ev["attempts"] else False,
        }
        self.reset()
        return ev
