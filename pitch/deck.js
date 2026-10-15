// ============ Vidyut pitch — slide engine ============
(() => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const slides = $$('.slide');
  const N = slides.length;
  let cur = -1, lock = false;

  // reveal order inside every slide
  slides.forEach(s => $$('.a', s).forEach((el, i) => el.style.setProperty('--i', i)));

  // ---------- build the nav bar ----------
  const segs = $('#segs'), chips = $('#chips'), now = $('#now'), ovgrid = $('#ovgrid');
  const groups = [];
  slides.forEach((s, i) => {
    const g = s.dataset.group;
    if (!groups.length || groups[groups.length - 1].name !== g) groups.push({ name: g, first: i, idx: [] });
    groups[groups.length - 1].idx.push(i);
  });
  slides.forEach((s, i) => {
    const b = document.createElement('button');
    b.className = 'seg' + (i === groups.find(g => g.idx.includes(i)).first && i ? ' gap' : '');
    b.dataset.t = `${i + 1} · ${s.dataset.title}`;
    b.setAttribute('aria-label', `Go to slide ${i + 1}: ${s.dataset.title}`);
    b.onclick = () => go(i);
    segs.appendChild(b);
    const o = document.createElement('button');
    o.className = 'ovi'; o.innerHTML = `<small>${String(i + 1).padStart(2, '0')} · ${s.dataset.group}</small><b>${s.dataset.title}</b>`;
    o.onclick = () => { toggleOv(false); go(i); };
    ovgrid.appendChild(o);
  });
  groups.forEach(g => {
    const c = document.createElement('button');
    c.className = 'chip'; c.textContent = g.name; c.onclick = () => go(g.first);
    g.el = c; chips.appendChild(c);
  });

  // ---------- go ----------
  function go(i, instant) {
    i = Math.max(0, Math.min(N - 1, i));
    if (i === cur) return;
    slides.forEach((s, k) => { s.classList.toggle('active', k === i); s.classList.toggle('before', k < i); if (k !== i) s.scrollTop = 0; });
    cur = i;
    const s = slides[i];
    document.body.classList.toggle('dark', s.classList.contains('dark'));
    $$('.seg').forEach((b, k) => { b.classList.toggle('on', k === i); b.classList.toggle('done', k < i); });
    groups.forEach(g => g.el.classList.toggle('on', g.idx.includes(i)));
    now.innerHTML = `<b>${String(i + 1).padStart(2, '0')}</b> / ${String(N).padStart(2, '0')} · ${s.dataset.title}`;
    $$('.ovi').forEach((o, k) => o.classList.toggle('on', k === i));
    history.replaceState(null, '', '#' + (i + 1));
    runCounters(s);
  }
  const next = () => go(cur + 1), prev = () => go(cur - 1);

  // counters (re-run every time a slide appears)
  function runCounters(s) {
    $$('[data-count]', s).forEach(el => {
      const target = +el.dataset.count, after = el.dataset.after || '', k = el.dataset.k || '';
      const t0 = performance.now(), dur = 1400;
      cancelAnimationFrame(el._raf);
      const step = now => {
        const p = Math.min(1, (now - t0 - 350) / dur), e = p <= 0 ? 0 : 1 - Math.pow(1 - p, 4);
        el.textContent = Math.round(target * e).toLocaleString('en-US') + k + after;
        if (p < 1) el._raf = requestAnimationFrame(step);
      };
      el.textContent = '0' + k + after; el._raf = requestAnimationFrame(step);
    });
  }

  // ---------- input ----------
  addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key;
    if (k === 'ArrowRight' || k === 'PageDown' || k === ' ' || k === 'Enter') { e.preventDefault(); next(); }
    else if (k === 'ArrowLeft' || k === 'PageUp' || k === 'Backspace') { e.preventDefault(); prev(); }
    else if (k === 'Home') go(0);
    else if (k === 'End') go(N - 1);
    else if (k === 'f' || k === 'F') toggleFs();
    else if (k === 'o' || k === 'O') toggleOv();
    else if (k === 'Escape') toggleOv(false);
    else if (/^[1-9]$/.test(k)) go(+k - 1);
  });

  const scrollable = (s, dir) => s.scrollHeight > s.clientHeight + 4 && (dir > 0 ? s.scrollTop + s.clientHeight < s.scrollHeight - 4 : s.scrollTop > 4);
  $('.stage').addEventListener('wheel', e => {
    if (Math.abs(e.deltaY) < 25 && Math.abs(e.deltaX) < 25) return;
    const dir = (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) > 0 ? 1 : -1;
    if (scrollable(slides[cur], dir)) return;
    if (lock) return; lock = true; setTimeout(() => lock = false, 800);
    dir > 0 ? next() : prev();
  }, { passive: true });

  let tx = 0, ty = 0;
  $('.stage').addEventListener('touchstart', e => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; }, { passive: true });
  $('.stage').addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.4) dx < 0 ? next() : prev();
  }, { passive: true });

  $('#prev').onclick = prev; $('#next').onclick = next;
  function toggleFs() { document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); }
  function toggleOv(force) { $('#ov').classList.toggle('open', force === undefined ? !$('#ov').classList.contains('open') : force); }
  $('#fs').onclick = toggleFs; $('#ovbtn').onclick = () => toggleOv();
  $('#ov').addEventListener('click', e => { if (e.target.id === 'ov') toggleOv(false); });

  const start = parseInt(location.hash.slice(1), 10);
  go(Number.isFinite(start) ? start - 1 : 0);
})();
