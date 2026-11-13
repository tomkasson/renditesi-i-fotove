"""Komponentët e klikueshëm të 🌳 Pemës (st.components.v2: pa iframe, pa ringarkim faqeje, pa internet).

Regjistrohen një herë (moduli importohet një herë), jo në çdo rifreskim të faqes.
Të dhënat që hyjnë si HTML (SVG-ja) janë ndërtuar nga pema.svg me emrat të "escape-uar";
galeria përdor vetëm textContent/src, pra asnjë tekst nuk interpretohet si HTML.
"""
import streamlit as st

TREE_CSS = """
.pw { position: relative; overflow: hidden; border-radius: 20px; touch-action: none; user-select: none;
      border: 1px solid color-mix(in srgb, var(--st-text-color) 12%, transparent);
      background-color: var(--st-secondary-background-color);
      background-image: radial-gradient(color-mix(in srgb, var(--st-text-color) 13%, transparent) 1px,
                                        transparent 1.2px);
      background-size: 22px 22px; cursor: grab; }
.pw.drag { cursor: grabbing; }
.pw:fullscreen { border-radius: 0; }
.stage { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
.stage.smooth { transition: transform .28s cubic-bezier(.2,.7,.2,1); }
.stage svg { display: block; overflow: visible; }
.karta { cursor: pointer; outline: none; transform-box: fill-box; transform-origin: center;
         transition: transform .18s ease-out; }
.karta:hover { transform: translateY(-3px); }
.karta:hover > rect.bg, .karta:focus-visible > rect.bg { stroke: var(--st-primary-color); stroke-width: 3; }
.pw.anim .karta { animation: hyr .45s cubic-bezier(.2,.7,.2,1) both; animation-delay: calc(var(--i) * 22ms); }
.pw.anim .vija { animation: shfaq .6s ease-out both; animation-delay: .15s; }
@keyframes hyr { from { opacity: 0; transform: translateY(12px) scale(.96); } }
@keyframes shfaq { from { opacity: 0; } }
.tools { position: absolute; top: 12px; right: 12px; display: flex; flex-direction: column; gap: 6px; z-index: 10; }
.tools button { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--st-text-color) 14%, transparent); color: var(--st-text-color);
  background: color-mix(in srgb, var(--st-background-color) 88%, transparent); backdrop-filter: blur(6px);
  transition: color .15s, border-color .15s; padding: 0; }
.tools button:hover { color: var(--st-primary-color); border-color: var(--st-primary-color); }
.tools button:focus-visible { outline: 2px solid var(--st-primary-color); outline-offset: 2px; }
.tools svg { width: 18px; height: 18px; }
.legend { position: absolute; left: 12px; bottom: 12px; display: flex; flex-wrap: wrap; gap: 6px; z-index: 10;
  max-width: calc(100% - 320px); pointer-events: none; }
@media (max-width: 640px) { .legend { max-width: calc(100% - 24px); } }
.legend span { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 4px 10px;
  border-radius: 999px; color: var(--st-text-color);
  background: color-mix(in srgb, var(--st-background-color) 88%, transparent); backdrop-filter: blur(6px);
  border: 1px solid color-mix(in srgb, var(--st-text-color) 10%, transparent); }
.legend i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.legend i.dash { width: 16px; height: 0; border-radius: 0; border-top: 2px dashed #94A3B8; }
.hint { position: absolute; right: 14px; bottom: 16px; font-size: 12px; z-index: 10; pointer-events: none;
  color: color-mix(in srgb, var(--st-text-color) 65%, transparent); }
@media (max-width: 640px) { .hint { display: none; } }
@media (prefers-reduced-motion: reduce) {
  .karta, .stage.smooth { transition: none; }
  .pw.anim .karta, .pw.anim .vija { animation: none; }
}
"""

TREE_JS = """
const ICON = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  fit: '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
  me: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/><circle cx="12" cy="12" r="8"/>',
  full: '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
};
const LEGEND = [['#4F46E5', 'Ti / qendra'], ['#6366F1', 'Gjaku'], ['#E11D48', 'Nga martesa'],
  ['#0EA5E9', 'Shoqëria'], ['#F59E0B', 'Shkolla'], ['#10B981', 'Puna'], ['dash', 'Pa kontakt']];

function icon(name) {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
         'stroke-linejoin="round" aria-hidden="true">' + ICON[name] + '</svg>';
}

function build(wrap, setTriggerValue) {
  wrap.innerHTML = '<div class="stage"></div>' +
    '<div class="hint">Tërhiq për ta lëvizur · Ctrl + rrota = zmadho</div>' +
    '<div class="tools"></div><div class="legend"></div>';
  const st = wrap._st = { x: 0, y: 0, s: 1, w: 0, h: 0, center: null, drag: null, moved: false };
  const stage = wrap.querySelector('.stage');
  const apply = (smooth) => {
    stage.classList.toggle('smooth', !!smooth);
    stage.style.transform = 'translate(' + st.x + 'px, ' + st.y + 'px) scale(' + st.s + ')';
  };
  const clamp = (v) => Math.min(2.2, Math.max(0.2, v));
  const zoomAt = (f, px, py, smooth) => {
    const ns = clamp(st.s * f);
    st.x = px - (px - st.x) * (ns / st.s);
    st.y = py - (py - st.y) * (ns / st.s);
    st.s = ns;
    apply(smooth);
  };
  const mid = () => [wrap.clientWidth / 2, wrap.clientHeight / 2];
  wrap._fit = (smooth) => {
    const W = wrap.clientWidth, H = wrap.clientHeight;
    st.s = clamp(Math.min(1.1, (W - 48) / st.w, (H - 48) / st.h));
    st.x = (W - st.w * st.s) / 2;
    st.y = Math.max(16, (H - st.h * st.s) / 2);
    apply(smooth);
  };
  wrap._me = () => {
    const g = [...stage.querySelectorAll('.karta')].find((k) => k.getAttribute('data-name') === st.center);
    if (!g) return wrap._fit(true);
    const b = g.getBBox();
    st.s = Math.max(st.s, 0.9);
    st.x = wrap.clientWidth / 2 - (b.x + b.width / 2) * st.s;
    st.y = wrap.clientHeight / 2 - (b.y + b.height / 2) * st.s;
    apply(true);
  };
  const tools = [
    ['plus', 'Zmadho', () => zoomAt(1.25, ...mid(), true)],
    ['minus', 'Zvogëlo', () => zoomAt(0.8, ...mid(), true)],
    ['fit', 'Shiko gjithë pemën', () => wrap._fit(true)],
    ['me', 'Te qendra', () => wrap._me()],
    ['full', 'Ekran i plotë', () => (document.fullscreenElement ? document.exitFullscreen()
                                                                : wrap.requestFullscreen && wrap.requestFullscreen())],
  ];
  const tb = wrap.querySelector('.tools');
  tools.forEach(([ic, label, fn]) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.title = label;
    b.setAttribute('aria-label', label);
    b.innerHTML = icon(ic);
    b.addEventListener('pointerdown', (e) => e.stopPropagation());
    b.onclick = fn;
    tb.append(b);
  });
  const lg = wrap.querySelector('.legend');
  LEGEND.forEach(([c, t]) => {
    const s = document.createElement('span');
    const i = document.createElement('i');
    if (c === 'dash') i.className = 'dash'; else i.style.background = c;
    s.append(i, document.createTextNode(t));
    lg.append(s);
  });
  wrap.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    st.drag = { x: e.clientX, y: e.clientY, ox: st.x, oy: st.y, id: e.pointerId };
    st.moved = false;
  });
  wrap.addEventListener('pointermove', (e) => {
    const d = st.drag;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!st.moved && Math.hypot(dx, dy) < 5) return;  // klikim, jo tërheqje
    if (!st.moved) {
      st.moved = true;
      wrap.classList.add('drag');
      wrap.setPointerCapture(d.id);
    }
    st.x = d.ox + dx;
    st.y = d.oy + dy;
    apply(false);
  });
  const end = () => { st.drag = null; wrap.classList.remove('drag'); };
  wrap.addEventListener('pointerup', end);
  wrap.addEventListener('pointercancel', end);
  wrap.addEventListener('wheel', (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;  // rrota e thjeshtë lëviz faqen
    e.preventDefault();
    const r = wrap.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top, false);
  }, { passive: false });
  document.addEventListener('fullscreenchange', () => setTimeout(() => wrap._fit(true), 60));
}

export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  let wrap = parentElement.querySelector('.pw');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.className = 'pw';
    parentElement.appendChild(wrap);
    build(wrap, setTriggerValue);
  }
  const st = wrap._st;
  if (wrap.dataset.sig === data.sig) return;
  const stage = wrap.querySelector('.stage');
  stage.innerHTML = data.svg;
  wrap.dataset.sig = data.sig;
  const first = !st.w, newCenter = st.center !== data.center;
  st.w = data.w;
  st.h = data.h;
  st.center = data.center;
  wrap.style.height = Math.round(Math.max(380, Math.min(window.innerHeight * 0.74, data.h + 110))) + 'px';
  stage.querySelectorAll('.karta').forEach((g) => {
    const name = g.getAttribute('data-name');
    const t = g.querySelector('title');
    g.setAttribute('tabindex', '0');
    g.setAttribute('role', 'button');
    g.setAttribute('aria-label', t ? t.textContent : name);
    g.onclick = () => { if (!st.moved) setTriggerValue('person', name); };
    g.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTriggerValue('person', name); }
    };
  });
  if (first || newCenter) {  // pemë e re: hyrje e animuar dhe e gjithë pema në pamje
    wrap.classList.remove('anim');
    void wrap.offsetWidth;
    wrap.classList.add('anim');
    requestAnimationFrame(() => wrap._fit(!first));
  }
}
"""

GALLERY_CSS = """
.gal { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
figure { margin: 0; }
img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 10px; cursor: zoom-in; display: block;
      background: rgba(128,128,128,.15); }
img:hover { outline: 3px solid var(--st-primary-color); outline-offset: -3px; }
figcaption { display: flex; gap: 4px; justify-content: space-between; align-items: center; font-size: 12px;
             color: var(--st-text-color); opacity: .8; padding: 3px 2px; }
figcaption span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
figcaption a { text-decoration: none; cursor: pointer; flex: none; }
"""

GALLERY_JS = """
export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  let box = parentElement.querySelector('.gal');
  if (!box) {
    box = document.createElement('div');
    box.className = 'gal';
    parentElement.appendChild(box);
  }
  box.replaceChildren();
  (data.items || []).forEach((it) => {
    const fig = document.createElement('figure');
    const img = document.createElement('img');
    img.src = it.src;
    img.alt = it.cap;
    img.title = 'Kliko: hap foton · ' + it.cap;
    img.onclick = () => setTriggerValue('open', it.i);
    const cap = document.createElement('figcaption');
    const t = document.createElement('span');
    t.textContent = it.cap;
    const a = document.createElement('a');
    a.textContent = '📁';
    a.title = 'Trego në dosje';
    a.onclick = (e) => { e.preventDefault(); setTriggerValue('folder', it.i); };
    cap.append(t, a);
    fig.append(img, cap);
    box.append(fig);
  });
}
"""

tree = st.components.v2.component("pema_pema", css=TREE_CSS, js=TREE_JS)
gallery = st.components.v2.component("pema_galeria", css=GALLERY_CSS, js=GALLERY_JS)
