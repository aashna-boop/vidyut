/* Canvas grid renderer. Draws the REAL topologies from window.VIDYUT and replays REAL precomputed fault/restore events. */
(function () {
  const C = { sand: '#F2ECDF', bone: '#FAF7F0', moss: '#5C6B4F', sage: '#C9D2BC', ink: '#22281F', brass: '#C08A3E', dead: '#D6CDB8' };
  const V = window.VIDYUT;
  const views = [];
  const hash = (i) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`; };
  const mix = (h1, h2, t) => { const a = parseInt(h1.slice(1), 16), b = parseInt(h2.slice(1), 16);
    const r = lerp(a >> 16, b >> 16, t) | 0, g = lerp((a >> 8) & 255, (b >> 8) & 255, t) | 0, bl = lerp(a & 255, b & 255, t) | 0; return `rgb(${r},${g},${bl})`; };

  class GridView {
    constructor(cv, key, o = {}) {
      this.cv = cv; this.ctx = cv.getContext('2d');
      this.o = Object.assign({ hero: false, pointer: false, flows: true, fillX: .44, fillY: .42, cx: .5, cy: .5, ambient: true, showTies: true }, o);
      this.mx = -1e4; this.my = -1e4; this.visible = true; this.lockT = 0; this.lock = 0; this.hoverBus = -1; this.time = 0;
      this.onStage = null; this.onDone = null;
      this.setTopo(key); this.resize(); views.push(this);
      if ('IntersectionObserver' in window) new IntersectionObserver((e) => { this.visible = e[0].isIntersecting; }).observe(cv);
      if (this.o.pointer) {
        window.addEventListener('pointermove', (e) => { const r = cv.getBoundingClientRect(); this.mx = e.clientX - r.left; this.my = e.clientY - r.top; });
        cv.addEventListener('pointerleave', () => { this.mx = this.my = -1e4; });
      }
      window.addEventListener('resize', () => this.resize());
    }
    setTopo(key) {
      this.key = key; this.T = V.topos[key]; const n = this.T.buses.length;
      this.alive = new Float32Array(n).fill(1); this.target = new Uint8Array(n).fill(1);
      this.rate = new Float32Array(n); for (let i = 0; i < n; i++) this.rate[i] = 2.5 + hash(i) * 5;
      this.px = new Float32Array(n); this.py = new Float32Array(n);
      const nl = this.T.lines.length;
      this.flows = []; const nf = this.o.flows ? Math.min(70, Math.round(nl * .45)) : 0;
      for (let i = 0; i < nf; i++) this.flows.push({ li: (hash(i + 9) * nl) | 0, p: hash(i + 3), v: .18 + hash(i + 5) * .4, d: hash(i + 1) > .5 ? 1 : -1 });
      this.tieSet = new Set(this.T.ties); this.reset();
    }
    reset() { this.ev = null; this.stage = -1; this.openL = new Set(); this.closedTie = new Set(); this.tieP = 0; this.fault = -1; this.reticle = -1;
      this.zone = new Set(); this.pulses = []; this.alive.fill(1); this.target.fill(1); this.running = false; }
    resize() {
      const cv = this.cv, dpr = Math.min(window.devicePixelRatio || 1, 2); const w = cv.clientWidth, h = cv.clientHeight;
      if (!w || !h) return; cv.width = w * dpr; cv.height = h * dpr; this.w = w; this.h = h; this.dpr = dpr; this.layout(1);
    }
    layout(force) {
      const o = this.o, w = this.w, h = this.h, T = this.T; if (!w) return;
      let s, cx, cy;
      if (o.hero) { const k = this.lockT; s = Math.min(w * lerp(.47, .36, k), h * lerp(.42, .40, k)); cx = w * lerp(.5, .6, k); cy = h * lerp(.47, .53, k); }
      else { s = Math.min(w * o.fillX, h * o.fillY); cx = w * o.cx; cy = h * o.cy; }
      for (let i = 0; i < T.buses.length; i++) { this.px[i] = cx + T.buses[i][0] * s; this.py[i] = cy + T.buses[i][1] * s; }
    }
    pick(x, y) { let b = -1, bd = 26 * 26; for (let i = 0; i < this.px.length; i++) { const dx = this.px[i] - x, dy = this.py[i] - y, d = dx * dx + dy * dy; if (d < bd) { bd = d; b = i; } } return b; }

    /* ---------- event playback ---------- */
    run(bus) {
      const ev = this.T.events[String(bus)];
      if (!ev) return { ok: false, why: 'No precomputed run for this bus.' };
      if (ev.o === 's') return { ok: false, why: 'Substation / HV bus — distribution FISR doesn’t apply. Pick a feeder bus.' };
      this.reset(); this.ev = ev; this.fault = bus; this.running = true; this.seq = ev.o === 'r' ? [1, 1.5, 2, 3, 4] : [1, 1.5, 2];
      this.stage = -1; this.stageT = 0; this.stageDur = 1.9; this.enter(0); return { ok: true, ev };
    }
    setDead(list) { this.target.fill(1); for (const b of list) this.target[b] = 0; }
    enter(k) {
      const ev = this.ev, T = this.T; this.stage = k; this.stageT = 0;
      const idx = ev.o === 'r' ? [1, 1, 2, 3, 4][k] : [1, 1, 2][k];
      this.setDead(ev.d[idx]);
      if (k === 0) { this.pulses.push({ t: 0 }); this.openL.add(ev.head); }
      if (k === 1) { this.reticle = ev.r[0]; }
      if (ev.o === 'r' && k >= 2) { this.zone = new Set(ev.z); for (const l of ev.iso) this.openL.add(l); if (k >= 3) this.openL.delete(ev.head); }
      if (ev.o === 'r' && k === 4) { for (const l of ev.tie) this.closedTie.add(l); this.tieP = 0; }
      if (ev.o === 'l' && k === 2) { this.lockout = true; }
      if (this.onStage) this.onStage(k, ev, this);
    }
    update(dt) {
      this.time += dt; this.lockT = lerp(this.lockT, this.lock, 1 - Math.exp(-dt * 5));
      for (let i = 0; i < this.alive.length; i++) { const t = this.target[i]; this.alive[i] += (t - this.alive[i]) * (1 - Math.exp(-dt * this.rate[i] * (t ? .6 : 1.4))); }
      for (const f of this.flows) { f.p += f.v * dt * f.d; if (f.p > 1) f.p -= 1; if (f.p < 0) f.p += 1; }
      if (this.tieP < 1) this.tieP = Math.min(1, this.tieP + dt * .9);
      this.pulses.forEach((p) => p.t += dt); this.pulses = this.pulses.filter((p) => p.t < 2.4 || this.stage < 2);
      if (this.running) { this.stageT += dt; if (this.stageT > this.stageDur) { if (this.stage < this.seq.length - 1) this.enter(this.stage + 1); else { this.running = false; if (this.onDone) this.onDone(this.ev, this); } } }
    }

    /* ---------- drawing ---------- */
    draw() {
      const ctx = this.ctx, T = this.T, w = this.w, h = this.h, dpr = this.dpr; if (!w) return;
      this.layout();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
      const n = T.buses.length, R = 150, r0 = clamp(w / 520, 1.8, 3.4) * Math.min(1, Math.sqrt(190 / n)) * (this.o.hero ? 1 : 1.5);
      const px = this.px, py = this.py, mx = this.mx, my = this.my, t = this.time;
      if (this.o.pointer && mx > -1000) { const g = ctx.createRadialGradient(mx, my, 0, mx, my, 240); g.addColorStop(0, rgba(C.sage, .7)); g.addColorStop(1, rgba(C.sage, 0)); ctx.fillStyle = g; ctx.fillRect(mx - 240, my - 240, 480, 480); }
      // lines
      for (let li = 0; li < T.lines.length; li++) {
        const [a, b] = T.lines[li], life = Math.min(this.alive[a], this.alive[b]); const ax = px[a], ay = py[a], bx = px[b], by = py[b];
        const isOpen = this.openL.has(li), isTie = this.tieSet.has(li), closed = this.closedTie.has(li);
        let k = 0; if (this.o.pointer && mx > -1000) { const d = Math.hypot((ax + bx) / 2 - mx, (ay + by) / 2 - my); k = clamp(1 - d / R, 0, 1); }
        ctx.beginPath();
        if (isTie && this.o.showTies && !closed) { ctx.setLineDash([5, 5]); ctx.strokeStyle = rgba(C.brass, .75); ctx.lineWidth = 1.4; ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]); continue; }
        if (isOpen) { const mxp = (ax + bx) / 2, myp = (ay + by) / 2, dx = (bx - ax) * .16, dy = (by - ay) * .16;
          ctx.strokeStyle = rgba(C.ink, .25); ctx.lineWidth = 1.2; ctx.moveTo(ax, ay); ctx.lineTo(mxp - dx, myp - dy); ctx.moveTo(mxp + dx, myp + dy); ctx.lineTo(bx, by); ctx.stroke();
          ctx.beginPath(); ctx.strokeStyle = C.ink; ctx.lineWidth = 2; const q = 5; ctx.moveTo(mxp - q, myp - q); ctx.lineTo(mxp + q, myp + q); ctx.moveTo(mxp - q, myp + q); ctx.lineTo(mxp + q, myp - q); ctx.stroke(); continue; }
        if (closed) { const p = this.tieP; ctx.strokeStyle = rgba(C.brass, .95); ctx.lineWidth = 3; ctx.moveTo(ax, ay); ctx.lineTo(lerp(ax, bx, p), lerp(ay, by, p)); ctx.stroke(); continue; }
        ctx.strokeStyle = life > .5 ? mix(C.moss, C.brass, k) : rgba(C.ink, .1);
        ctx.globalAlpha = life > .5 ? (.32 + .5 * life + .3 * k) : .8; ctx.lineWidth = 1 + k * 1.7 + (this.o.hero ? 0 : .3); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke(); ctx.globalAlpha = 1;
      }
      // flowing energy
      if (this.o.ambient) for (const f of this.flows) { const [a, b] = T.lines[f.li]; if (this.openL.has(f.li) || this.tieSet.has(f.li)) continue; const life = Math.min(this.alive[a], this.alive[b]); if (life < .6) continue;
        const x = lerp(px[a], px[b], f.p), y = lerp(py[a], py[b], f.p); ctx.fillStyle = rgba(C.brass, .9 * life); ctx.beginPath(); ctx.arc(x, y, r0 * .8, 0, 6.283); ctx.fill(); }
      // nodes
      this.hoverBus = -1; let best = 1e9;
      for (let i = 0; i < n; i++) {
        const life = this.alive[i], pv = T.buses[i][2]; let k = 0;
        if (this.o.pointer && mx > -1000) { const d = Math.hypot(px[i] - mx, py[i] - my); k = clamp(1 - d / R, 0, 1); if (d < best && d < 26) { best = d; this.hoverBus = i; } }
        const rr = r0 * (1 + k * 1.9) * (i === this.fault ? 1.5 : 1);
        ctx.beginPath(); ctx.arc(px[i], py[i], rr, 0, 6.283); ctx.fillStyle = life > .5 ? mix(C.moss, C.brass, k) : C.dead; ctx.globalAlpha = .35 + .65 * life; ctx.fill(); ctx.globalAlpha = 1;
        if (pv && life > .5) { ctx.beginPath(); ctx.arc(px[i], py[i], rr + 2.2, 0, 6.283); ctx.strokeStyle = rgba(C.brass, .7); ctx.lineWidth = 1; ctx.stroke(); }
      }
      if (this.hoverBus >= 0 && this.lock) { const i = this.hoverBus; ctx.beginPath(); ctx.arc(px[i], py[i], r0 * 3.4, 0, 6.283); ctx.strokeStyle = C.ink; ctx.lineWidth = 1.5; ctx.stroke(); }
      // event overlays
      if (this.ev) {
        for (const i of this.zone) { ctx.beginPath(); ctx.arc(px[i], py[i], r0 * 3.6, 0, 6.283); ctx.strokeStyle = C.ink; ctx.lineWidth = 2; ctx.stroke(); }
        if (this.fault >= 0) { const f = this.fault, fx = px[f], fy = py[f];
          if (this.stage < 2) for (const p of this.pulses) { const q = p.t % 1.2 / 1.2; ctx.beginPath(); ctx.arc(fx, fy, r0 * 2 + q * 70, 0, 6.283); ctx.strokeStyle = rgba(C.brass, 1 - q); ctx.lineWidth = 2.5; ctx.stroke(); }
          ctx.beginPath(); ctx.arc(fx, fy, r0 * 2.4, 0, 6.283); ctx.fillStyle = C.brass; ctx.fill();
          if (this.stage >= 2) { const q = 8; ctx.beginPath(); ctx.strokeStyle = C.ink; ctx.lineWidth = 2.6; ctx.moveTo(fx - q, fy - q); ctx.lineTo(fx + q, fy + q); ctx.moveTo(fx - q, fy + q); ctx.lineTo(fx + q, fy - q); ctx.stroke(); } }
        if (this.reticle >= 0 && this.stage >= 1) { const i = this.reticle, x = px[i], y = py[i], rot = t * 1.6, rr = r0 * 5 + Math.sin(t * 6) * 1.5;
          ctx.save(); ctx.translate(x, y); ctx.rotate(rot); ctx.strokeStyle = C.ink; ctx.lineWidth = 2; for (let a = 0; a < 4; a++) { ctx.beginPath(); ctx.arc(0, 0, rr, a * 1.5708, a * 1.5708 + .9); ctx.stroke(); } ctx.restore(); }
      }
    }
  }

  let last = performance.now();
  function frame(now) { const dt = Math.min(.05, (now - last) / 1000); last = now;
    for (const v of views) if (v.visible) { v.update(dt); v.draw(); }
    requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
  window.GridView = GridView; window.GridColors = C;
})();
