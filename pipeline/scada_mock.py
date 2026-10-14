"""
VIDYUT <-> SCADA/DERMS integration layer  —  A MOCK. IT IS NOT CONNECTED TO ANY REAL UTILITY SYSTEM.

Standard chosen: IEC 61850 object naming  (LogicalDevice/LogicalNode.DataObject.DataAttribute).
Why 61850 (and not DNP3 as the primary model):
  * It is a *semantic* model: a tag says what a thing is (XSWI = switch, MMXU = measurement unit, DPVC-like =
    PV controller) rather than an anonymous "analog input #412". Vidyut publishes predictions and events that
    have no natural DNP3 point, and a self-describing name space fits that.
  * It is a widely used substation/DER integration standard (IEC 61850, with 7-420 / 90-7 covering DER). Which
    standard a *given* utility requires is something to confirm with them; this repo does not assume it.
  * Legacy RTUs speak DNP3/IEC 104. So `dnp3_point_map()` emits the same tag list as a DNP3-style point table
    (binary input / analog input / CROB / analog output with indexes), the view a protocol gateway would use.

What is real here: the point database, message envelope (value/quality/timestamp/origin), command handshake
(select-before-operate style ctlVal -> stVal), and that the state it publishes comes from an actual AC power
flow and the FISR switching engine. What is NOT real: there is no MMS/GOOSE/DNP3 wire protocol, no security
(IEC 62351), no real RTU, and the exact DO/DA names below follow 61850 *conventions* — they must be checked
against a utility's SCL/ICD files before any real deployment. Vidyut's own LNs (VDY*) are a private namespace.
"""
import json, time, threading
import numpy as np
import pandapower as pp
from http.server import BaseHTTPRequestHandler, HTTPServer

Q_GOOD, Q_INVALID = "good", "invalid"
DBPOS = {"open": 1, "closed": 2}          # 61850 Dbpos: intermediate=0, off=1, on=2, bad=3


def now_ms():
    return int(time.time() * 1000)


class TagDB:
    """Thread-safe point database. Tag = '<LD>/<LN>.<DO>.<DA>'."""

    def __init__(self):
        self.pts, self.lock, self.log = {}, threading.Lock(), []

    def publish(self, tag, value, origin, unit="", q=Q_GOOD):
        with self.lock:
            self.pts[tag] = {"tag": tag, "v": value, "q": q, "t": now_ms(), "origin": origin, "unit": unit}
            self.log.append(self.pts[tag])
        return self.pts[tag]

    def read(self, tag):
        with self.lock:
            return dict(self.pts[tag]) if tag in self.pts else None

    def read_prefix(self, prefix):
        with self.lock:
            return [dict(v) for k, v in self.pts.items() if k.startswith(prefix)]


class Tags:
    """IEC 61850 object-reference builders:  <LD>/<LN>.<DO>.<DA>  (LD = logical device per feeder/bus)."""

    def __init__(self, topo_name):
        self.name = topo_name
        self.ld = lambda kind, i: f"{topo_name}_{kind}{i:03d}"

    # a switch id is "SW<idx>" for a real pandapower switch object or "VSW<line>" for an ASSUMED sectionaliser
    def tag_switch_pos(self, sw_id): return f"{self.name}_{sw_id}/XSWI1.Pos.stVal"
    def tag_switch_ctl(self, sw_id): return f"{self.name}_{sw_id}/CSWI1.Pos.ctlVal"
    def tag_bus_v(self, b): return f"{self.ld('BUS', b)}/MMXU1.PhV.phsA.cVal.mag.f"
    def tag_bus_ang(self, b): return f"{self.ld('BUS', b)}/MMXU1.PhV.phsA.cVal.ang.f"
    def tag_line_i(self, l): return f"{self.ld('FDR', l)}/MMXU1.A.phsA.cVal.mag.f"
    def tag_pv_limit(self, b): return f"{self.ld('BUS', b)}/DPVC1.WMaxLim.setMag.f"
    def tag_curt_forecast(self, b): return f"{self.ld('BUS', b)}/VDYCRT1.NxtHrCrtlMW.mag.f"
    def tag_loc(self): return f"{self.name}_VIDYUT/VDYFLC1.LocBus.stVal"
    def tag_fisr_stage(self): return f"{self.name}_VIDYUT/VDYFSR1.Stage.stVal"


class MockSCADA(Tags):
    """Plays the utility side: owns the switches/breakers of the grid model, publishes measurements + status,
    and executes control commands (select-before-operate style) against the real switching model."""

    def __init__(self, fisr_engine, topo_name):
        self.F = fisr_engine
        self.T = fisr_engine.T
        Tags.__init__(self, topo_name)
        self.db = TagDB()
        self.selected = {}

    def publish_state(self):
        """Publish switch positions + measurements from a real AC power flow of the current switch state."""
        F, T, net = self.F, self.T, self.F.net
        m = F.solve()
        for sid in self.switch_ids():
            self.db.publish(self.tag_switch_pos(sid), DBPOS["open" if self.is_open(sid) else "closed"], "SCADA", "Dbpos")
        vn = net.bus.loc[T.bus_ids].vn_kv.values
        for b in range(T.n_bus):
            ok = m is not None and m["alive"][b]
            self.db.publish(self.tag_bus_v(b), float(m["vm"][b] * vn[b] * 1000 / np.sqrt(3)) if ok else 0.0, "SCADA", "V",
                            Q_GOOD if ok else Q_INVALID)
            self.db.publish(self.tag_bus_ang(b), float(net.res_bus.va_degree.loc[T.bus_ids[b]]) if ok else 0.0, "SCADA", "deg",
                            Q_GOOD if ok else Q_INVALID)
        for li in range(T.n_line):
            self.db.publish(self.tag_line_i(li), float(np.nan_to_num(net.res_line.i_ka.values[li]) * 1000), "SCADA", "A")
        return m

    # -- switch bookkeeping ---------------------------------------------------------------------
    def switch_ids(self):
        F = self.F
        ids = [f"SW{si:03d}" for si in F.net.switch.index if F.net.switch.et.at[si] == "l"]
        ids += [f"VSW{li:03d}" for li in range(self.T.n_line) if li not in F.sw_by_line]
        return ids

    def is_open(self, sid):
        net = self.F.net
        if sid.startswith("VSW"):
            return not bool(net.line.in_service.iat[int(sid[3:])])
        return not bool(net.switch.closed.at[int(sid[2:])])

    @staticmethod
    def op_id(op):
        kind, idx = op
        return f"SW{int(idx):03d}" if kind == "sw" else f"VSW{int(idx):03d}"

    # -- control: select-before-operate on ONE switch (what FISR uses) --------------------------
    def select(self, sid, client):
        self.selected[sid] = client
        return {"ok": True, "cause": "selected"}

    def operate(self, sid, want_closed, client):
        """Executes on the real switch model. Returns a 61850-style command termination."""
        if self.selected.get(sid) != client:
            return {"ok": False, "cause": "object-not-selected"}
        net = self.F.net
        if sid.startswith("VSW"):
            net.line.at[net.line.index[int(sid[3:])], "in_service"] = bool(want_closed)
        else:
            net.switch.at[int(sid[2:]), "closed"] = bool(want_closed)
        self.selected.pop(sid, None)
        self.db.publish(self.tag_switch_ctl(sid), DBPOS["closed" if want_closed else "open"], client, "Dbpos")
        self.db.publish(self.tag_switch_pos(sid), DBPOS["closed" if want_closed else "open"], "SCADA", "Dbpos")
        return {"ok": True, "cause": "operated"}

    # -- DERMS side: curtailment setpoints ----------------------------------------------------
    def derms_set_limit(self, bus, mw, client):
        self.db.publish(self.tag_pv_limit(bus), float(mw), client, "MW")
        return {"ok": True, "cause": "accepted-not-enforced-in-mock"}

    def dnp3_point_map(self):
        """Gateway-style DNP3 point table for every published tag (indexes assigned in order)."""
        rows, idx = [], {"BI": 0, "AI": 0, "CROB": 0, "AO": 0}
        for tag in sorted(self.db.pts):
            if tag.endswith("Pos.stVal"): g, cls = 1, "BI"; desc = "Binary Input (switch status, 2-bit dbpos)"
            elif tag.endswith("Pos.ctlVal"): g, cls = 12, "CROB"; desc = "Control Relay Output Block"
            elif tag.endswith("setMag.f"): g, cls = 41, "AO"; desc = "Analog Output (setpoint)"
            else: g, cls = 30, "AI"; desc = "Analog Input"
            rows.append({"dnp3_group": g, "dnp3_class": cls, "dnp3_index": idx[cls], "description": desc, "iec61850_tag": tag})
            idx[cls] += 1
        return rows


class VidyutAdapter:
    """Vidyut's side: READS state from SCADA, PUBLISHES predictions/events, ISSUES switching commands."""
    ORIGIN = "VIDYUT"

    def __init__(self, scada):
        self.s = scada
        self.db = scada.db

    def read_state(self):
        return {sid: self.db.read(self.s.tag_switch_pos(sid))["v"] == DBPOS["open"] for sid in self.s.switch_ids()}

    def publish_curtailment_forecast(self, bus_pred_mw):
        for b, mw in enumerate(bus_pred_mw):
            if self.s.T.sgen_bus.tolist().count(b):
                self.db.publish(self.s.tag_curt_forecast(b), float(mw), self.ORIGIN, "MW")

    def publish_localization(self, ranked, scores):
        base = f"{self.s.name}_VIDYUT/VDYFLC1"
        self.db.publish(self.s.tag_loc(), int(ranked[0]), self.ORIGIN)
        self.db.publish(f"{base}.Conf.mag.f", float(scores[ranked[0]]), self.ORIGIN, "cos")
        for k, b in enumerate(ranked[:3]):
            self.db.publish(f"{base}.Cand{k+1}.stVal", int(b), self.ORIGIN)

    def command(self, op, want_closed):
        """Select-before-operate one switch through SCADA; returns the termination."""
        sid = self.s.op_id(op)
        self.s.select(sid, self.ORIGIN)
        res = self.s.operate(sid, want_closed, self.ORIGIN)
        self.db.publish(f"{self.s.name}_VIDYUT/VDYFSR1.Op.general", sid, self.ORIGIN)
        return {"switch": sid, "action": "close" if want_closed else "open", **res}

    def execute_fisr(self, head_ops, iso_ops, tie_ops):
        """Replay a FISR plan through SCADA in the utility order: isolate, reclose feeder head, close ties."""
        out = [self.command(op, False) for op in iso_ops]
        out += [self.command(op, True) for op in head_ops]
        out += [self.command(op, True) for op in tie_ops]
        return out


# --------------------------------------------------------------------------------- optional HTTP face
def serve(scada, port=8765):
    """GET /points?prefix=..  ·  GET /point?tag=..  ·  GET /dnp3map  — read-only JSON view of the mock point DB."""
    class H(BaseHTTPRequestHandler):
        def _send(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path); q = parse_qs(u.query)
            if u.path == "/points": self._send(scada.db.read_prefix(q.get("prefix", [""])[0]))
            elif u.path == "/point":
                p = scada.db.read(q.get("tag", [""])[0]); self._send(p or {"error": "unknown tag"}, 200 if p else 404)
            elif u.path == "/dnp3map": self._send(scada.dnp3_point_map())
            else: self._send({"error": "not found", "mock": True}, 404)

        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
