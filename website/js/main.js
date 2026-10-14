(function () {
  const V = window.VIDYUT, C = window.GridColors;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const html = document.documentElement;
  const hasGsap = !!(window.gsap && window.ScrollTrigger);
  const reduce = matchMedia('(prefers-reduced-motion:reduce)').matches;
  const fine = matchMedia('(hover:hover) and (pointer:fine)').matches;
  const pad3 = (n) => String(Math.round(n)).padStart(3, '0');

  /* ---------- real numbers -> DOM ---------- */
  const F = { int: (x) => Math.round(x).toLocaleString('en-US'), f2: (x) => x.toFixed(2), pct0: (x) => Math.round(x * 100) + '%', pct1: (x) => (x * 100).toFixed(1) + '%' };
  const get = (path) => path.split('.').reduce((o, k) => (o == null ? o : o[k]), path.startsWith('global') ? V : V.stats);
  const stat = (path, fmt) => { const v = get(path); return v == null ? '—' : (F[fmt || 'int'](v)); };
  $$('[data-stat]').forEach((el) => { el.textContent = stat(el.dataset.stat, el.dataset.fmt); });

  /* ---------- hero wordmark ---------- */
  const hw = $('#hword');
  'VIDYUT'.split('').forEach((c) => { const s = document.createElement('span'); s.className = 'ch'; s.innerHTML = `<span>${c}</span>`; hw.appendChild(s); });

  const fitWord = () => { hw.style.fontSize = '100px'; const k = hw.children, w = k[k.length - 1].getBoundingClientRect().right - k[0].getBoundingClientRect().left;
    const avail = innerWidth - 2 * Math.max(18, innerWidth * .03); hw.style.fontSize = Math.min(Math.max(100 * avail / w, 90), innerHeight * .78) + 'px'; };
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(fitWord); addEventListener('resize', fitWord); addEventListener('load', fitWord); if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener('loadingdone', fitWord); fitWord();

  /* ---------- hero grid ---------- */
  const view = new GridView($('#gridcv'), 'oberrhein', { hero: true, pointer: true });
  window.__hero = view;
  let topoKey = 'oberrhein';
  const tabs = $('#tabs');
  V.order.forEach((k) => { const b = document.createElement('button'); b.className = 'tab' + (k === topoKey ? ' on' : ''); b.textContent = V.topos[k].name; b.dataset.k = k;
    b.onclick = () => loadTopo(k); tabs.appendChild(b); });
  function loadTopo(k) { topoKey = k; view.setTopo(k); $$('.tab').forEach((t) => t.classList.toggle('on', t.dataset.k === k));
    $('.hero-foot span').textContent = `Real ${V.topos[k].name} topology · ${V.topos[k].nBus} buses`; hudReset(); }

  /* HUD */
  const hud = { t: $('#hudt'), l: $$('#hudl li'), bar: $('#hudbar'), served: $('#hudserved'), tot: $('#hudtot'), msg: $('#hudmsg') };
  function hudReset() { hud.t.textContent = 'Click any bus'; hud.l.forEach((x) => x.className = ''); hud.bar.style.transform = 'scaleX(1)'; hud.served.textContent = '— MW served'; hud.tot.textContent = '—';
    hud.msg.textContent = 'Every step below was actually computed with an AC power flow on the real switch model; this is a replay.'; }
  const S_IDX = [1, 1, 2, 3, 4];
  view.onStage = (k, ev) => {
    const last = ev.o === 'r' ? 4 : 2;
    hud.l.forEach((li, i) => li.className = i < k ? 'done' : (i === k ? 'on' : ''));
    if (ev.o === 'l') { hud.l[3].style.opacity = hud.l[4].style.opacity = .3; } else { hud.l[3].style.opacity = hud.l[4].style.opacity = ''; }
    const si = ev.o === 'r' ? S_IDX[k] : [1, 1, 2][k], served = ev.s[si];
    hud.bar.style.transform = `scaleX(${Math.max(.02, served / ev.tot)})`; hud.served.textContent = `${served.toFixed(1)} MW served`; hud.tot.textContent = `of ${ev.tot.toFixed(1)} MW`;
    const m = [
      `Feeder-head breaker trips. ${ev.out.length} bus${ev.out.length === 1 ? '' : 'es'} lose supply.`,
      ev.r[0] === view.fault ? `Vidyut localizes the fault to bus ${ev.r[0]} — exact.` : `Vidyut says bus ${ev.r[0]}; the true fault is at bus ${view.fault}. A miss — it retries with the next candidate (${ev.att} attempt${ev.att === 1 ? '' : 's'} used).`,
      ev.o === 'r' ? `${ev.iso.length} sectionalising switch operation${ev.iso.length === 1 ? '' : 's'} cut out just the faulted zone (${ev.z.length} bus${ev.z.length === 1 ? '' : 'es'}).`
                   : `Not isolated within ${ev.att} attempts → lockout. The feeder stays dark until a crew arrives. (This happens in the real results too.)`,
      'Feeder head recloses: substation-side buses are re-energised.',
      ev.tie.length ? `Closed ${ev.tie.length} real tie switch${ev.tie.length === 1 ? '' : 'es'}: stranded downstream buses are re-supplied.` : 'No tie switch in reach — downstream customers stay out.'];
    hud.msg.textContent = m[k];
    if (k === 0) hud.t.textContent = `Fault at bus ${view.fault}`;
  };
  view.onDone = (ev) => { const fin = ev.s[ev.s.length - 1]; hud.t.textContent = ev.o === 'r' ? `${Math.round(fin / ev.tot * 100)}% of load served` : 'Lockout';
    if (ev.o === 'r') hud.msg.textContent += ` The fault zone's own load is unavoidably lost. Click another bus.`; else hud.msg.textContent += ' Click another bus.'; };
  $('#gridcv').addEventListener('click', () => { if (!locked || view.hoverBus < 0) return; const r = view.run(view.hoverBus); if (!r.ok) { hud.msg.textContent = r.why; } });

  /* lock mode */
  let locked = false, lenis = null;
  function setLock(on) {
    locked = on; html.classList.toggle('locked', on); view.lock = on ? 1 : 0; if (!on) { view.reset(); hudReset(); }
    $('#navlock span').textContent = on ? 'Back to scroll' : 'Tap to lock';
    if (on) { if (lenis) { lenis.scrollTo(0, { immediate: false, duration: .8 }); setTimeout(() => lenis.stop(), 500); } else window.scrollTo({ top: 0, behavior: 'smooth' }); document.body.style.overflow = 'hidden'; }
    else { if (lenis) lenis.start(); document.body.style.overflow = ''; }
  }
  ['#lockbtn', '#navlock'].forEach((s) => $(s).addEventListener('click', () => setLock(!locked)));
  $('#backbtn').addEventListener('click', () => setLock(false));
  addEventListener('keydown', (e) => { if (e.key === 'Escape') { if (menuOpen) toggleMenu(); else if (locked) setLock(false); } });
  function breakIt(key) { if (key) loadTopo(key); setLock(true); setTimeout(() => { const ks = Object.keys(view.T.events).filter((b) => view.T.events[b].o === 'r' && view.T.events[b].tie.length); if (ks.length) view.run(+ks[(ks.length * .37) | 0]); }, 900); }
  $('#tryit').addEventListener('click', () => breakIt());
  $('#fbreak').addEventListener('click', () => breakIt());

  /* ---------- fallback when CDN scripts are blocked ---------- */
  if (!hasGsap) { $('#pre').remove(); $$('.hero-word .ch>span,.rv>span,.w>i').forEach((e) => e.style.transform = 'none'); $$('.mtext .mw').forEach((e) => e.classList.add('on')); }

  /* ---------- gallery cards ---------- */
  const track = $('#gtrack');
  V.order.forEach((k) => { const t = V.topos[k], s = V.stats[k]; const el = document.createElement('article'); el.className = 'gcard'; el.dataset.cur = 'VIEW';
    el.innerHTML = `<canvas></canvas><div class="cap"><h3>${t.name}</h3><span class="mono" style="text-align:right;color:var(--moss)">${t.place}<br>${t.nBus} buses</span></div>
      <div class="facts mono"><span><b>${t.ties.length}</b> real ties</span><span><b>${stat(k + '.loc_vti_full', 'pct1')}</b> exact-bus localization</span><span><b>${stat(k + '.restored', 'pct1')}</b> restored</span></div>`;
    track.appendChild(el); const cv = $('canvas', el); requestAnimationFrame(() => { const v = new GridView(cv, k, { fillX: .47, fillY: .46, flows: true }); el._v = v; });
    el.addEventListener('click', () => breakIt(k));
    if (fine) { el.addEventListener('pointermove', (e) => { const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5; el.style.transform = `perspective(900px) rotateY(${x * 9}deg) rotateX(${-y * 9}deg) translateZ(8px)`; });
      el.addEventListener('pointerleave', () => { el.style.transform = ''; }); } });

  /* ---------- week chart (real 2019 test week, oberrhein) ---------- */
  const wc = $('#weekchart');
  function drawWeek(p) { const cv = wc, dpr = Math.min(devicePixelRatio || 1, 2), w = cv.clientWidth, h = cv.clientHeight; if (!w) return; cv.width = w * dpr; cv.height = h * dpr;
    const x = cv.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0); const a = V.week.actual, pr = V.week.pred, n = a.length, mx = Math.max(...a, ...pr) * 1.08;
    const X = (i) => i / (n - 1) * w, Y = (v) => h - 6 - v / mx * (h - 14), upto = Math.floor(p * (n - 1));
    x.beginPath(); x.moveTo(0, h); for (let i = 0; i <= upto; i++) x.lineTo(X(i), Y(a[i])); x.lineTo(X(upto), h); x.closePath(); x.fillStyle = 'rgba(92,107,79,.28)'; x.fill();
    x.beginPath(); for (let i = 0; i <= upto; i++) i ? x.lineTo(X(i), Y(a[i])) : x.moveTo(X(i), Y(a[i])); x.strokeStyle = C.ink; x.lineWidth = 2; x.stroke();
    x.beginPath(); x.setLineDash([5, 4]); for (let i = 0; i <= upto; i++) i ? x.lineTo(X(i), Y(pr[i])) : x.moveTo(X(i), Y(pr[i])); x.strokeStyle = C.brass; x.lineWidth = 2.2; x.stroke(); x.setLineDash([]);
    x.fillStyle = C.ink; x.font = '10px JetBrains Mono, monospace'; x.fillText('ACTUAL', 6, 12); x.fillStyle = C.brass; x.fillText('MODEL FORECAST · ' + V.week.dates[0] + ' → ' + V.week.dates[6], 60, 12); }
  const wk = { p: 0 }; const playWeek = () => { if (!hasGsap) { drawWeek(1); return; } gsap.fromTo(wk, { p: 0 }, { p: 1, duration: 1.8, ease: 'power2.out', onUpdate: () => drawWeek(wk.p) }); };
  $('#hp').addEventListener('pointerenter', playWeek); requestAnimationFrame(() => drawWeek(1)); addEventListener('resize', () => drawWeek(1));

  /* ---------- roster ---------- */
  const rows = $('#rows'); const peek = $('#peek'); let peekView = null;
  V.order.forEach((k, i) => { const t = V.topos[k], s = V.stats[k]; const r = document.createElement('div'); r.className = 'row'; r.dataset.cur = 'BREAK IT';
    r.innerHTML = `<span class="mono">0${i + 1}</span><div><div class="nm">${t.name}</div><span class="mono" style="opacity:.7">${t.place} · ${t.nBus} buses · ${t.ties.length} real ties</span></div>
      <div class="metric"><b>${stat(k + '.loc_vti_full', 'pct1')}</b><span class="mono">exact-bus localization</span></div><div class="metric"><b>${stat(k + '.restored', 'pct1')}</b><span class="mono">load restored</span></div>`;
    rows.appendChild(r);
    r.addEventListener('pointerenter', () => { if (!peekView) peekView = new GridView($('#peekcv'), k, { fillX: .46, fillY: .46, flows: true }); else peekView.setTopo(k); peek.classList.add('on'); });
    r.addEventListener('pointerleave', () => peek.classList.remove('on'));
    r.addEventListener('click', () => breakIt(k)); });
  if (fine) { let px = 0, py = 0, tx = 0, ty = 0; addEventListener('pointermove', (e) => { tx = e.clientX + 30; ty = e.clientY - 120; }); (function loop() { px += (tx - px) * .14; py += (ty - py) * .14; peek.style.left = px + 'px'; peek.style.top = py + 'px'; requestAnimationFrame(loop); })(); }

  /* ---------- proof tiles ---------- */
  const tiles = [
    { n: 'global.days_de', f: 'int', l: 'real days of hourly solar + demand', b: `Germany 2015–2019 (OPSD). 20× the previous prototype's 90 days. An Indian-solar variant has ${stat('global.days_in')} days — but paired with German demand, so it's a hybrid.` },
    { n: 'oberrhein.loc_vti_full', f: 'pct1', l: 'exact-bus fault localization (Oberrhein)', b: `Needs voltage + angle + current sensing. Voltage alone: ${stat('oberrhein.loc_v_full', 'pct1')}. With only 30% of sensors: ${stat('oberrhein.loc_vti_30', 'pct1')} exact (${stat('oberrhein.loc_vti_5hop_30', 'pct1')} within 5 hops).` },
    { n: 'oberrhein.restored', f: 'pct1', l: 'of avoidable outage load restored', b: `With perfect localization it would be ${stat('oberrhein.restored_oracle', 'pct1')}. ${stat('oberrhein.lockout', 'pct1')} of faults ended in lockout. Tested on ${stat('oberrhein.faults')} faults at the 2019 peak-load hour.` },
    { n: 'oberrhein.p1_f1', f: 'f2', l: 'F1 at catching next-hour curtailment', b: `Versus ${stat('oberrhein.p1_f1_persist', 'f2')} for "repeat last hour". Labels come from our own curtailment rule — it learns the simulator, not a utility's logs.` },
    { n: 'kerber_dorf.restored_oracle', f: 'pct0', l: 'ceiling on radial grids with no tie switches', b: 'Kerber low-voltage feeders ship no ties: isolation works, but downstream customers cannot be re-supplied — even with perfect localization.' },
    { n: null, warn: true, big: 'n/a', l: 'validated predictive-maintenance accuracy', b: 'No public dataset of real equipment failures exists, so no accuracy can be validly claimed. Only a physics-based stress ranking is provided.' }];
  const tg = $('#tiles');
  tiles.forEach((t, i) => { const el = document.createElement('div'); el.className = 'tile' + (t.warn ? ' warn' : ''); el.dataset.cur = 'FLIP';
    el.innerHTML = `<div class="in"><div class="face f"><span class="mono">0${i + 1}</span><div class="big" ${t.n ? `data-count="${t.n}" data-fmt="${t.f}"` : ''}>${t.big || '0'}</div><p>${t.l}</p></div><div class="face b"><span class="mono">The fine print</span><p>${t.b}</p></div></div>`;
    el.addEventListener('click', () => el.classList.toggle('flip')); tg.appendChild(el); });

  /* ---------- marquees ---------- */
  const mk = (id, arr) => { const m = $(id); const one = arr.map((x) => `<span>${x}</span>`).join(''); m.innerHTML = one + one + one; };
  mk('#mq1', ['Open Power System Data', 'NASA POWER', 'PVGIS-ERA5', 'pandapower', 'CIGRE MV benchmark', 'Kerber networks', 'IEC 61850']);
  mk('#mq2', ['NREL NSRDB — unreachable', 'Renewables.ninja — needs a token', 'Grid-India hourly demand — not obtainable']);

  /* ---------- terminal: replays a real event as 61850-style tags ---------- */
  const tl = $('#tlines'); const T0 = V.topos.oberrhein; const nm = 'oberrhein';
  const evKeys = Object.keys(T0.events).filter((b) => T0.events[b].o === 'r' && T0.events[b].tie.length && T0.events[b].isoId);
  function eventLines(ev, b) { const P = (id) => `${nm}_${id}/XSWI1.Pos.stVal`, K = (id) => `${nm}_${id}/CSWI1.Pos.ctlVal`, L = [];
    L.push(['ev', `# fault injected at bus ${b}`]); L.push(['rx', `SCADA→VIDYUT  ${P(ev.hid[0])} = 1 (open)`]);
    L.push(['tx', `VIDYUT→SCADA  ${nm}_VIDYUT/VDYFLC1.LocBus.stVal = ${ev.r[0]}`]);
    ev.isoId.forEach((id) => { L.push(['tx', `VIDYUT→SCADA  SELECT ${K(id)}`]); L.push(['tx', `VIDYUT→SCADA  OPERATE ${K(id)} = 1`]); L.push(['rx', `SCADA→VIDYUT  ${P(id)} = 1 (open) ok`]); });
    L.push(['tx', `VIDYUT→SCADA  OPERATE ${K(ev.hid[0])} = 2`]); L.push(['rx', `SCADA→VIDYUT  ${P(ev.hid[0])} = 2 (closed) ok`]);
    ev.tieId.forEach((id) => { L.push(['tx', `VIDYUT→SCADA  SELECT ${K(id)}`]); L.push(['tx', `VIDYUT→SCADA  OPERATE ${K(id)} = 2`]); L.push(['rx', `SCADA→VIDYUT  ${P(id)} = 2 (closed) ok`]); });
    L.push(['ev', `# ${(ev.s[ev.s.length - 1]).toFixed(2)} of ${ev.tot.toFixed(2)} MW served`]); return L; }
  let tq = [], ti = 0; setInterval(() => { if (!document.hidden) { if (!tq.length) { const b = evKeys[ti++ % evKeys.length]; tq = eventLines(T0.events[b], b); }
    const [c, txt] = tq.shift(); const d = document.createElement('div'); d.className = c; d.textContent = txt; tl.appendChild(d); while (tl.children.length > 13) tl.removeChild(tl.firstChild); } }, 620);

  /* ---------- footer big text ---------- */
  const bf = $('#bigfoot'); 'ALWAYS ON.'.split('').forEach((c) => { const s = document.createElement('span'); s.textContent = c === ' ' ? ' ' : c; bf.appendChild(s); });
  const bl = $$('span', bf);
  addEventListener('pointermove', (e) => { const r = bf.getBoundingClientRect(); if (e.clientY < r.top - 200 || e.clientY > r.bottom + 200) return;
    bl.forEach((s) => { const b = s.getBoundingClientRect(), d = Math.hypot(e.clientX - (b.left + b.width / 2), (e.clientY - (b.top + b.height / 2)) * .5), k = Math.max(0, 1 - d / 320);
      s.style.fontWeight = Math.round(200 + k * 700); s.style.color = k > .55 ? C.brass : ''; }); });

  if (!hasGsap) return;

  /* =================== GSAP =================== */
  gsap.registerPlugin(ScrollTrigger);
  if (!reduce && window.Lenis) { lenis = new Lenis({ duration: 1.15, easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)), smoothWheel: true });
    lenis.on('scroll', ScrollTrigger.update); gsap.ticker.add((t) => lenis.raf(t * 1000)); gsap.ticker.lagSmoothing(0); }
  const toEl = (el) => { const t = $(el); if (t) (lenis ? lenis.scrollTo(t, { offset: 0, duration: 1.6 }) : t.scrollIntoView({ behavior: 'smooth' })); };
  $$('a[href^="#"]').forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); if (locked) setLock(false); setTimeout(() => toEl(a.getAttribute('href')), locked ? 300 : 0); if (menuOpen) toggleMenu(); }));

  /* cursor */
  if (fine) { html.classList.add('has-cursor'); const ring = $('#cur'), dot = $('#curdot'), span = $('#cur .cur-ring span');
    const rx = gsap.quickTo(ring, 'x', { duration: .45, ease: 'power3' }), ry = gsap.quickTo(ring, 'y', { duration: .45, ease: 'power3' });
    let lx = -100, ly = -100;
    const label = (x, y) => { const el = document.elementFromPoint(x, y); if (!el) return; let lab = null; const t = el.closest('[data-cur],a,button,.tab');
      if (el.id === 'gridcv' && locked) lab = 'FAULT'; else if (t) lab = t.dataset.cur ? t.dataset.cur : (t.matches('a,button,.tab') ? '' : null);
      const inLabel = lab !== null && lab !== ''; ring.classList.toggle('big', inLabel); if (inLabel) span.textContent = lab; dot.style.opacity = inLabel ? 0 : 1;
      ring.classList.toggle('dark', !!el.closest('#proof,#scada,#foot,#menu')); };
    addEventListener('pointermove', (e) => { lx = e.clientX; ly = e.clientY; ring.classList.add('ready'); dot.classList.add('ready'); rx(lx); ry(ly); gsap.set(dot, { x: lx, y: ly }); label(lx, ly); });
    addEventListener('scroll', () => { if (lx > 0) label(lx, ly); }, { passive: true }); }
  /* magnetic */
  if (fine) $$('[data-mag]').forEach((b) => { const s = $('span', b) || b; b.addEventListener('pointermove', (e) => { const r = b.getBoundingClientRect(); gsap.to(b, { x: (e.clientX - r.left - r.width / 2) * .3, y: (e.clientY - r.top - r.height / 2) * .4, duration: .4, ease: 'power3' }); gsap.to(s, { x: (e.clientX - r.left - r.width / 2) * .12, duration: .4 }); });
    b.addEventListener('pointerleave', () => { gsap.to(b, { x: 0, y: 0, duration: .8, ease: 'elastic.out(1,.4)' }); gsap.to(s, { x: 0, duration: .6 }); }); });

  /* menu */
  let menuOpen = false; const menu = $('#menu'); const items = $$('#menu li a');
  function toggleMenu() { menuOpen = !menuOpen; $('#menubtn span').textContent = menuOpen ? 'Close' : 'Menu';
    if (menuOpen) { menu.style.visibility = 'visible'; if (lenis) lenis.stop(); gsap.to(menu, { clipPath: 'inset(0 0 0% 0)', duration: .9, ease: 'expo.inOut' }); gsap.fromTo(items, { yPercent: 110 }, { yPercent: 0, duration: 1, stagger: .05, ease: 'expo.out', delay: .35 }); $('#nav').classList.add('dark'); }
    else { gsap.to(menu, { clipPath: 'inset(0 0 100% 0)', duration: .8, ease: 'expo.inOut', onComplete: () => { menu.style.visibility = 'hidden'; } }); if (lenis && !locked) lenis.start(); if (!darkNow) $('#nav').classList.remove('dark'); } }
  $('#menubtn').addEventListener('click', toggleMenu);

  /* progress + section index + nav tone */
  const prog = $('#prog'), sideIdx = $('#side-idx'); let darkNow = false;
  ScrollTrigger.create({ start: 0, end: 'max', onUpdate: (s) => { gsap.set(prog, { scaleX: s.progress }); } });
  $$('section[data-idx],footer[data-idx]').forEach((sec) => ScrollTrigger.create({ trigger: sec, start: 'top 55%', end: 'bottom 55%', onToggle: (s) => { if (s.isActive) { sideIdx.textContent = sec.dataset.idx;
    darkNow = ['ink', 'moss'].includes(sec.dataset.bg); if (!menuOpen) $('#nav').classList.toggle('dark', darkNow); } } }));

  /* velocity-driven marquees */
  let vel = 0; if (lenis) lenis.on('scroll', (e) => { vel = e.velocity; });
  const mqs = [{ el: $('#mq1'), x: 0, dir: -1, sp: 70 }, { el: $('#mq2'), x: 0, dir: 1, sp: 55 }];
  gsap.ticker.add((t, dt) => { mqs.forEach((m) => { const w = m.el.scrollWidth / 3; m.x += m.dir * (m.sp + Math.abs(vel) * 22) * dt / 1000; if (m.dir < 0 && m.x < -w) m.x += w; if (m.dir > 0 && m.x > 0) m.x -= w; gsap.set(m.el, { x: m.dir > 0 ? m.x - w : m.x }); }); });

  /* reveals */
  gsap.set('.rv>span', { y: 0, yPercent: 105 }); $$('.rv>span').forEach((s) => gsap.to(s, { yPercent: 0, duration: 1.2, ease: 'expo.out', scrollTrigger: { trigger: s.closest('section'), start: 'top 72%' } }));
  gsap.from('.mnote,.g-head p,.r-head p,#sources .wrap p,.lcol', { opacity: 0, y: 40, duration: 1, stagger: .12, ease: 'power3.out', scrollTrigger: { trigger: '#manifesto', start: 'top 20%' } });
  $$('.lcol').forEach((c, i) => gsap.from(c, { opacity: 0, y: 60, duration: 1, delay: i * .1, ease: 'power3.out', scrollTrigger: { trigger: c, start: 'top 92%' } }));
  $$('.row').forEach((r, i) => gsap.from(r, { opacity: 0, y: 50, duration: .9, ease: 'power3.out', scrollTrigger: { trigger: r, start: 'top 94%' } }));
  $$('.tile').forEach((t, i) => gsap.from(t, { opacity: 0, y: 70, rotate: (i % 2 ? 2 : -2), duration: 1, delay: (i % 3) * .1, ease: 'power3.out', scrollTrigger: { trigger: t, start: 'top 92%' } }));
  gsap.from('.f-note', { opacity: 0, y: 30, duration: 1, ease: 'power3.out', scrollTrigger: { trigger: '#founders', start: 'top 65%' } });
  $$('.fcard').forEach((c, i) => gsap.from(c, { opacity: 0, y: 60, duration: 1, delay: i * .1, ease: 'power3.out', scrollTrigger: { trigger: c, start: 'top 92%' } }));
  $$('[data-count]').forEach((el) => { const path = el.dataset.count, fmt = el.dataset.fmt, v = get(path), o = { v: 0 };
    ScrollTrigger.create({ trigger: el, start: 'top 88%', once: true, onEnter: () => gsap.to(o, { v, duration: 1.8, ease: 'power3.out', onUpdate: () => { el.textContent = F[fmt](o.v); } }) }); });

  /* manifesto scrub */
  const mt = $('#mtext'); const nodes = [...mt.childNodes]; mt.innerHTML = '';
  nodes.forEach((n) => { const hl = n.nodeType === 1; (n.textContent).split(/(\s+)/).forEach((w) => { if (!w.trim()) { mt.append(' '); return; } const s = document.createElement('span'); s.className = 'mw' + (hl ? ' hl' : ''); s.textContent = w; mt.append(s); }); });
  const mw = $$('.mw', mt);
  ScrollTrigger.create({ trigger: mt, start: 'top 78%', end: 'bottom 45%', scrub: true, onUpdate: (s) => { const k = Math.floor(s.progress * (mw.length + 1)); mw.forEach((w, i) => w.classList.toggle('on', i < k)); } });

  /* horizontal gallery (desktop) — snaps so a card never stops half-shown */
  ScrollTrigger.matchMedia({ '(min-width: 901px)': () => {
    const wrap = $('.g-track-wrap'), cards = $$('.gcard'), dist = () => Math.max(1, track.scrollWidth - innerWidth + 40);
    const snapPoints = () => { const d = dist(), pts = cards.map((c) => Math.min(1, c.offsetLeft / d)); pts[0] = 0; pts[pts.length - 1] = 1; return pts; };
    const nearest = (v) => snapPoints().reduce((best, p) => (Math.abs(p - v) < Math.abs(best - v) ? p : best), 0);
    gsap.to(track, { x: () => -dist(), ease: 'none', scrollTrigger: { trigger: '#grids', start: 'top top', end: () => '+=' + dist(), pin: true, scrub: 1,
      invalidateOnRefresh: true, refreshPriority: 10, snap: { snapTo: nearest, duration: { min: .2, max: .6 }, ease: 'power2.inOut' } } });
    $$('.gcard').forEach((c, i) => gsap.from(c, { y: 120, opacity: 0, duration: 1, delay: i * .08, ease: 'power3.out', scrollTrigger: { trigger: '#grids', start: 'top 60%' } })); } });

  /* split panels: open on touch */
  ScrollTrigger.create({ trigger: '#split', start: 'top 60%', once: true, onEnter: playWeek });

  /* footer letters rise */
  gsap.from('#bigfoot span', { yPercent: 60, opacity: 0, stagger: .05, duration: 1.1, ease: 'expo.out', scrollTrigger: { trigger: '#bigfoot', start: 'top 92%' } });

  /* =================== preloader → intro =================== */
  const pre = $('#pre'); const path = $('#markp'); const len = path.getTotalLength(); path.style.strokeDasharray = len; path.style.strokeDashoffset = len;
  const counter = { v: 0 }; if (lenis) lenis.stop(); document.body.style.overflow = 'hidden';
  const intro = () => { const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
    tl.to('#pcount', { yPercent: -60, opacity: 0, duration: .7, ease: 'expo.in' }, 0).to('#pre .lbl,#pre .top', { opacity: 0, duration: .4 }, 0).to('#pre svg', { scale: 1.6, opacity: 0, duration: .8, ease: 'expo.in' }, .1)
      .to(pre, { clipPath: 'inset(0 0 100% 0)', duration: 1.2, ease: 'expo.inOut' }, .55)
      .from('#gridcv', { opacity: 0, scale: 1.08, duration: 1.8 }, 1)
      .to('.hero-word .ch>span', { y: 0, yPercent: 0, startAt: { yPercent: 105 }, duration: 1.4, stagger: .07 }, 1.05)
      .from('.eyebrow span,.hero-sub p,.hero-sub .r,.hero-foot span,#nav>*', { y: 24, opacity: 0, stagger: .05, duration: 1 }, 1.4)
      .add(() => { pre.remove(); document.body.style.overflow = ''; if (lenis) lenis.start(); ScrollTrigger.refresh(); }); };
  if (reduce) { pre.remove(); document.body.style.overflow = ''; gsap.set('.hero-word .ch>span', { yPercent: 0 }); }
  else { gsap.set('.hero-word .ch>span', { yPercent: 105 }); gsap.to(path, { strokeDashoffset: 0, duration: 1.8, ease: 'power2.inOut' });
    gsap.to(counter, { v: 100, duration: 2.6, ease: 'power2.inOut', onUpdate: () => { $('#pcount').textContent = pad3(counter.v); $('#plbl').textContent = `Energising ${Math.round(counter.v / 100 * V.topos.oberrhein.nBus)} buses`; }, onComplete: intro }); }
  addEventListener('load', () => ScrollTrigger.refresh());
})();
