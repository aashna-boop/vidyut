// ============ Vidyut pitch — interactions ============

// JS-visibility flag: all hide-until-reveal styles are gated on body.js,
// so content stays fully visible if scripts are disabled or fail.
document.body.classList.add('js');

// Headline line masks + prose reveals
const io = new IntersectionObserver(
  entries => {
    for (const e of entries) {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    }
  },
  { threshold: 0.18, rootMargin: '0px 0px -50px 0px' }
);
document.querySelectorAll('.line').forEach((el, i) => el.style.setProperty('--d', `${i * 0.09}s`));
document.querySelectorAll('.line, .lede, .aside').forEach(el => io.observe(el));

// ---- Counters (setTimeout-driven, ~60fps; no rAF dependency) ----
function animateCount(el) {
  const target = +el.dataset.count;
  const before = el.dataset.prefix || '';
  const after = el.dataset.after ?? el.dataset.suffix ?? '';
  const k = el.dataset.k || '';
  const dur = 1500, steps = 94, dt = dur / steps;
  let i = 0;
  const timer = setInterval(() => {
    i++;
    const eased = 1 - Math.pow(1 - i / steps, 4); // ease-out quart
    if (i >= steps) {
      clearInterval(timer);
      el.textContent = before + target.toLocaleString('en-US') + k + after;
      return;
    }
    el.textContent = before + Math.round(target * eased).toLocaleString('en-US') + k + after;
  }, dt);
}

function countersIn(root) {
  root.querySelectorAll('[data-count]').forEach(el => {
    if (el.dataset.done) return;
    el.dataset.done = '1';
    animateCount(el);
  });
}

// ---- Container enter: reveal container, stagger children, then counters ----
const gio = new IntersectionObserver(
  entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      gio.unobserve(e.target);
      e.target.classList.add('in');
      [...e.target.children].forEach((c, i) => {
        c.classList.add('tick');
        setTimeout(() => c.classList.add('in'), 30 + i * 70);
      });
      setTimeout(() => countersIn(e.target), 300);
    }
  },
  { threshold: 0.1 }
);
document.querySelectorAll('.ticker, .board, .ledger, .rail, .list, .bars').forEach(el => gio.observe(el));

// ---- Progress rule, header rule, scroll-spy: event-driven, no rAF loop ----
const bar = document.getElementById('bar');
const hdr = document.getElementById('top');
const navLinks = [...document.querySelectorAll('.top-links a')];
const targets = navLinks.map(a => document.querySelector(a.hash)).filter(Boolean);

function onScroll() {
  const h = document.documentElement;
  const max = h.scrollHeight - h.clientHeight;
  if (max > 0) bar.style.width = `${(h.scrollTop / max) * 100}%`;
  hdr.classList.toggle('ruled', h.scrollTop > 40);
  const y = h.scrollTop + window.innerHeight * 0.35;
  let cur = targets[0];
  for (const p of targets) if (p.offsetTop <= y) cur = p;
  navLinks.forEach(a => a.classList.toggle('active', cur && a.hash === '#' + cur.id));
}

let scheduled = false;
window.addEventListener('scroll', () => {
  if (scheduled) return;
  scheduled = true;
  setTimeout(() => { scheduled = false; onScroll(); }, 120);
}, { passive: true });

window.addEventListener('resize', onScroll, { passive: true });
onScroll();
