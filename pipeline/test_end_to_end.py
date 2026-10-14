"""
End-to-end test of the mock SCADA/DERMS loop on a real switching event (no real utility system is involved).

  SCADA publishes state  ->  Vidyut reads it  ->  Vidyut localizes a fault from the signature  ->  publishes
  IEC 61850-style tags  ->  FISR plan is executed through SCADA select-before-operate  ->  SCADA republishes the
  new state  ->  the resulting AC power flow must equal what the FISR engine computed.

Run:  python test_end_to_end.py [topology]      (default: cigre_mv; needs results/fisr_events_<topo>.jsonl for the
                                                  event-replay check on the topologies that have been swept)
"""
import json, os, sys, urllib.request
import numpy as np
import vgrid, fisr, localize
from scada_mock import MockSCADA, VidyutAdapter, serve, DBPOS

topo = sys.argv[1] if len(sys.argv) > 1 else "cigre_mv"
RES = os.path.join(vgrid.HERE, "results")
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")


meta = json.load(open(os.path.join(RES, f"fisr_meta_{topo}.json")))["snapshot"]
sf, lf = meta["sf"], meta["lf"]
T = vgrid.Topo(topo)
F = fisr.FISR(T, sf, lf)
scada = MockSCADA(F, topo)
vid = VidyutAdapter(scada)
print(f"== {topo}: snapshot {meta['date']} {meta['hour']:02d}:00 (sf={sf:.3f}, lf={lf:.3f})")

# 1. SCADA publishes; Vidyut reads state
m0 = scada.publish_state()
state = vid.read_state()
n_open = sum(state.values())
check("SCADA published every switch + measurement tag",
      len(state) == len(scada.switch_ids()) and len(scada.db.read_prefix(f"{topo}_BUS")) >= 2 * T.n_bus)
check("open switches at start == the network's normally-open tie switches", n_open == len(F.ties), f"({n_open} open)")
check("bus voltage tags carry the AC-power-flow result",
      abs(scada.db.read(scada.tag_bus_v(T.n_bus - 1))["v"] / (T.net.bus.vn_kv.iloc[-1] * 1000 / np.sqrt(3)) - m0["vm"][-1]) < 1e-9)

# 2. Command without SELECT must be rejected (select-before-operate)
sid0 = scada.switch_ids()[0]
r = scada.operate(sid0, False, "VIDYUT")
check("operate without select is rejected", (not r["ok"]) and r["cause"] == "object-not-selected")

# 3. Pick a real swept fault and replay it: localization -> plan -> SCADA execution
evs = [json.loads(l) for l in open(os.path.join(RES, f"fisr_events_{topo}.jsonl"))]
evs = [e for e in evs if e.get("vidyut") and e["vidyut"]["outcome"] == "restored" and e["vidyut"]["ranked"][0] == e["fault_bus"]]
evs.sort(key=lambda e: -len(e["vidyut"].get("tie_ops", [])))          # prefer an event that needs tie switches
e = evs[0]
v = e["vidyut"]
print(f"  replaying fault at bus {e['fault_bus']} (ties used: {len(v.get('tie_ops', []))}, zone size {len(v['zone'])})")

# Vidyut localization run against the mock (fresh model + fresh dictionary at the same state)
loc = localize.Localizer(vgrid.Topo(topo))
D, valid = loc.build_state(sf, lf)
rng = np.random.default_rng(10_000 + e["fault_bus"])
dv, dth, di, mw = loc.trial(e["fault_bus"], sf, lf, rng)
order, scores = loc.rank(loc.features(dv, dth, di, "VTI"), D, "VTI", valid)
vid.publish_localization(order, scores)
check("Vidyut published LocBus tag", scada.db.read(scada.tag_loc())["v"] == int(order[0]) and scada.db.read(scada.tag_loc())["origin"] == "VIDYUT")
check("localization reproduces the swept result (deterministic seed)", int(order[0]) == v["ranked"][0])

# Vidyut forecast tags for PV buses
vid.publish_curtailment_forecast(np.full(T.n_bus, 0.05))
pvb = int(T.sgen_bus[0])
check("Vidyut published curtailment-forecast tag on a PV bus", scada.db.read(scada.tag_curt_forecast(pvb))["v"] == 0.05)

# Fault happens: protection trips the feeder head (SCADA side), Vidyut sees it, then executes the plan.
F.reset(); head, outage = F.feeder_head(e["fault_bus"]); hops = F.head_ops(head)
scada.select(scada.op_id(hops[0]), "PROTECTION"); scada.operate(scada.op_id(hops[0]), False, "PROTECTION")
m1 = scada.publish_state()
check("after trip, SCADA marks de-energised buses q=invalid",
      sum(1 for b in range(T.n_bus) if scada.db.read(scada.tag_bus_v(b))["q"] == "invalid") == len(outage))
check("Vidyut can read the tripped breaker from SCADA", vid.read_state()[scada.op_id(hops[0])] is True)

iso_ops = [(o["kind"], o["idx"]) for o in v["iso_ops"]]
tie_ops = [(o["kind"], o["idx"]) for o in v.get("tie_ops", [])]
log = vid.execute_fisr(hops, iso_ops, tie_ops)
check("every FISR switching command terminated OK", all(x["ok"] for x in log), f"({len(log)} operations)")
m5 = scada.publish_state()
expected_served = v["stages"][-1]["served_mw"]
check("post-plan state (rebuilt from SCADA-executed commands) serves the same load as the FISR engine",
      abs(m5["served"] - expected_served) < 1e-3, f"({m5['served']:.4f} vs {expected_served:.4f} MW)")
check("same set of de-energised buses", sorted(np.where(~m5["alive"])[0].tolist()) == sorted(v["stages"][-1]["dead"]))

# 4. DNP3-style point map + HTTP face
pm = scada.dnp3_point_map()
groups = {}
for r_ in pm: groups[r_["dnp3_class"]] = groups.get(r_["dnp3_class"], 0) + 1
check("DNP3-style point map generated", len(pm) > 0 and "BI" in groups and "AI" in groups and "CROB" in groups, str(groups))
srv = serve(scada, port=8765)
try:
    tag = scada.tag_loc()
    got = json.loads(urllib.request.urlopen(f"http://127.0.0.1:8765/point?tag={tag}", timeout=5).read())
    check("HTTP /point returns the published tag", got["v"] == int(order[0]))
    mp = json.loads(urllib.request.urlopen("http://127.0.0.1:8765/dnp3map", timeout=5).read())
    check("HTTP /dnp3map returns the map", len(mp) == len(pm))
finally:
    srv.shutdown()

print("\nRESULT:", "ALL PASS" if ok_all else "FAILURES PRESENT")
sys.exit(0 if ok_all else 1)
