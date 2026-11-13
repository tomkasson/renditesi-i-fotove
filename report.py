"""Raporti i plotë: çdo skedar i skanuar, çfarë u gjet dhe çfarë ndodhi me të.

Krijon `raporti.html` (hapet në shfletues, me kërkim dhe filtra) dhe `raporti.csv` (për Excel).
"""
import csv
import datetime as dt
import html
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time as _time

_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

REPORT_HTML = "raporti.html"
REPORT_CSV = "raporti.csv"

S_COPIED = "✅ U kopjua"
S_MOVED = "✅ U zhvendos"
S_PLANNED = "➡ Do të kopjohet"
S_DUP = "♻️ E dyfishtë"
S_FILTER = "🧠 Filtruar (kategoria)"
S_ERROR = "⚠️ Gabim"
S_SKIP = "⏭ Kapërcyer gjatë skanimit"


def _status(row, dest, errors, executed, move, skip_dups):
    p = row["shtegu"]
    if p in errors:
        return S_ERROR, errors[p]
    if dest:
        return (S_MOVED if move else S_COPIED) if executed else S_PLANNED, dest
    if skip_dups and row.get("dyfishe"):
        return S_DUP, f"E njëjtë me: {row.get('dyfishe_e') or '?'}"
    return S_FILTER, f"Kategoria '{row.get('kategoria_emri') or row.get('kategoria')}' nuk ishte e zgjedhur"


def build(out_dir, rows, planned, errors=(), skipped=(), executed=False, move=False, skip_dups=True,
          layout="", sources=(), thumbs=True, progress=None):
    """rows: rreshtat e katalogut; planned: [(burimi, [dest_rel])]; errors: [(burimi, mesazhi)];
    skipped: [(shtegu, madhësia, arsyeja)] nga skanimi. Kthen shtegun e raportit HTML."""
    os.makedirs(out_dir, exist_ok=True)
    dest_of = {src: os.path.join(out_dir, d[0]) for src, d in planned}
    err = {p: m for p, m in errors}
    items = []
    for r in rows:
        st, detail = _status(r, dest_of.get(r["shtegu"]), err, executed, move, skip_dups)
        items.append({
            "shtegu": r["shtegu"], "emri": os.path.basename(r["shtegu"]), "lloji": r.get("lloji", ""),
            "statusi": st, "detaje": detail, "data": (r.get("data") or "")[:16].replace("T", " "),
            "burimi_datës": r.get("burimi_datës", ""), "vendi": " / ".join(x for x in (r.get("vendi"), r.get("qyteti")) if x),
            "kategoria": r.get("kategoria_emri") or "", "siguria": r.get("siguria") or "",
            "personat": r.get("personat") or "", "fytyra": r.get("fytyra") or "",
            "kamera": r.get("kamera") or "", "kb": r.get("madhesia_kb") or "",
        })
    for p, size, reason in skipped:
        items.append({
            "shtegu": p, "emri": os.path.basename(str(p).rstrip("\\/")) or str(p), "lloji": "dosje" if size is None and os.path.isdir(p) else "",
            "statusi": S_SKIP, "detaje": reason, "data": "", "burimi_datës": "", "vendi": "", "kategoria": "",
            "siguria": "", "personat": "", "fytyra": "", "kamera": "", "kb": round(size / 1024) if size else "",
        })

    # CSV për Excel
    fields = ["statusi", "detaje", "emri", "shtegu", "lloji", "data", "burimi_datës", "vendi", "kategoria",
              "siguria", "personat", "fytyra", "kamera", "kb"]
    with open(os.path.join(out_dir, REPORT_CSV), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(items)

    # Pamje të vogla (lazy në HTML; skedarët ruhen në cache të aplikacionit)
    if thumbs:
        import ai

        fotos = [it for it in items if it["lloji"] == "foto"]

        def mk(it):
            t = ai.photo_thumb(it["shtegu"], 200)
            it["thumb"] = Path(t).as_uri() if t else ""

        # Thread-et vetëm përgatisin pamjet; progresi raportohet nga thread-i kryesor
        # (Streamlit nuk lejon përditësimin e faqes nga thread-e të tjera).
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(mk, it) for it in fotos]
            for i, _ in enumerate(as_completed(futs), 1):
                if progress and (i % 25 == 0 or i == len(fotos)):
                    progress(i, len(fotos))

    path = os.path.join(out_dir, REPORT_HTML)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_html(items, executed, layout, sources, out_dir))
    return path


def _bars(counter, total, limit=12):
    if not counter:
        return '<p class="muted">—</p>'
    mx = max(counter.values())
    out = []
    for k, v in counter.most_common(limit):
        pct = 100 * v / mx
        out.append(f'<div class="bar"><span class="lbl" title="{html.escape(str(k))}">{html.escape(str(k))}</span>'
                   f'<span class="track"><span class="fill" style="width:{pct:.1f}%"></span></span>'
                   f'<span class="num">{v}</span></div>')
    if len(counter) > limit:
        out.append(f'<p class="muted">… dhe {len(counter) - limit} të tjera</p>')
    return "\n".join(out)


def _html(items, executed, layout, sources, out_dir):
    st = Counter(i["statusi"] for i in items)
    analysed = [i for i in items if i["statusi"] != S_SKIP]
    ok = st.get(S_COPIED, 0) + st.get(S_MOVED, 0) + st.get(S_PLANNED, 0)
    years = Counter((i["data"][:4] or "Pa datë") for i in analysed)
    cats = Counter(i["kategoria"] or "Pa analizë AI" for i in analysed
                   if i["lloji"] == "foto" and i["statusi"] != S_DUP)
    people = Counter(n.strip() for i in analysed for n in i["personat"].split(";") if n.strip())
    places = Counter(i["vendi"] for i in analysed if i["vendi"])
    reasons = Counter(i["detaje"] for i in items if i["statusi"] == S_SKIP)
    datesrc = Counter({"exif": "📷 Nga fotoja (EXIF)", "emri": "🏷️ Nga emri i skedarit",
                       "skedari": "🗂️ Nga data e skedarit (e pasigurt)"}.get(i["burimi_datës"], "Pa datë")
                      for i in analysed)
    now = dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    statuses = sorted(st)
    data_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    src_html = "".join(f"<li><code>{html.escape(s)}</code></li>" for s in sources) or "<li>—</li>"

    def card(label, val, cls=""):
        return f'<div class="card {cls}"><div class="v">{val}</div><div class="l">{label}</div></div>'

    cards = "".join([
        card("Skedarë të analizuar", len(analysed)),
        card("U kopjuan" if executed else "Do të kopjohen", ok, "good"),
        card("Të dyfishta", st.get(S_DUP, 0)),
        card("Filtruar nga AI", st.get(S_FILTER, 0)),
        card("Kapërcyer në skanim", st.get(S_SKIP, 0)),
        card("Gabime", st.get(S_ERROR, 0), "bad" if st.get(S_ERROR) else ""),
    ])
    opts = "".join(f'<option value="{html.escape(s)}">{html.escape(s)} ({st[s]})</option>' for s in statuses)

    return f"""<!doctype html>
<html lang="sq"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raporti i Fotove</title>
<style>
:root{{--bg:#f6f7f9;--panel:#fff;--text:#1b1f24;--muted:#667085;--line:#e4e7ec;--accent:#2563eb;--good:#16a34a;--bad:#dc2626;--track:#eef2f7}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0f1115;--panel:#171a21;--text:#e7e9ee;--muted:#98a2b3;--line:#2a2f3a;--accent:#60a5fa;--good:#4ade80;--bad:#f87171;--track:#232835}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:1300px;margin:0 auto;padding:24px 16px 60px}}h1{{margin:0 0 4px;font-size:26px}}h2{{font-size:16px;margin:0 0 12px}}
.muted{{color:var(--muted)}}code{{font-size:12px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}}.card .v{{font-size:26px;font-weight:700}}.card .l{{color:var(--muted)}}
.card.good .v{{color:var(--good)}}.card.bad .v{{color:var(--bad)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}}
.bar{{display:grid;grid-template-columns:minmax(80px,40%) 1fr 48px;gap:8px;align-items:center;margin:5px 0}}
.lbl{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.track{{background:var(--track);border-radius:6px;height:10px;overflow:hidden}}
.fill{{display:block;height:100%;background:var(--accent);border-radius:6px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0 12px}}input,select{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit}}
input{{flex:1;min-width:200px}}
.tbl{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px}}
table{{border-collapse:collapse;width:100%;min-width:1000px}}th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:var(--panel);cursor:pointer;user-select:none;font-weight:600}}
td.t img{{width:72px;height:72px;object-fit:cover;border-radius:6px;display:block}}
td .p{{color:var(--muted);font-size:12px;word-break:break-all}}.more{{margin:12px 0;text-align:center}}
button{{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 14px;font:inherit;cursor:pointer}}
</style></head><body><div class="wrap">
<h1>📸 Raporti i Fotove</h1>
<div class="muted">Krijuar më {now} · {"pas kopjimit" if executed else "para kopjimit (paraparje)"}{" · Struktura: " + html.escape(layout) if layout else ""} · Dalja: <code>{html.escape(out_dir)}</code></div>
<div class="cards">{cards}</div>
<div class="grid">
<div class="panel"><h2>Çfarë ndodhi</h2>{_bars(st, len(items))}</div>
<div class="panel"><h2>📅 Sipas vitit</h2>{_bars(years, len(analysed))}</div>
<div class="panel"><h2>🧠 Përmbajtja (AI)</h2>{_bars(cats, len(analysed))}</div>
<div class="panel"><h2>👤 Personat</h2>{_bars(people, len(analysed))}</div>
<div class="panel"><h2>📍 Vendet</h2>{_bars(places, len(analysed))}</div>
<div class="panel"><h2>🗓️ Nga erdhi data</h2>{_bars(datesrc, len(analysed))}</div>
<div class="panel"><h2>⏭ Pse u kapërcyen</h2>{_bars(reasons, len(items))}</div>
<div class="panel"><h2>📂 Dosjet e skanuara</h2><ul>{src_html}</ul></div>
</div>
<div class="filters">
<input id="q" placeholder="🔍 Kërko: emër skedari, dosje, person, vend, kamerë...">
<select id="fs"><option value="">Të gjitha statuset ({len(items)})</option>{opts}</select>
</div>
<div class="muted" id="cnt"></div>
<div class="tbl"><table><thead><tr>
<th data-k=""></th><th data-k="statusi">Statusi</th><th data-k="emri">Skedari</th><th data-k="data">Data</th>
<th data-k="kategoria">Përmbajtja</th><th data-k="personat">Personat</th><th data-k="vendi">Vendi</th>
<th data-k="kamera">Kamera</th><th data-k="kb">KB</th></tr></thead><tbody id="tb"></tbody></table></div>
<div class="more"><button id="more">Shfaq më shumë</button></div>
</div>
<script>
const D={data_json};
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}})[c]);
let rows=D,shown=0,sortK="",sortD=1;const PAGE=200;
function filt(){{const q=document.getElementById('q').value.toLowerCase(),s=document.getElementById('fs').value;
rows=D.filter(r=>(!s||r.statusi===s)&&(!q||[r.emri,r.shtegu,r.personat,r.vendi,r.kamera,r.kategoria,r.detaje,r.data].join(' ').toLowerCase().includes(q)));
if(sortK)rows.sort((a,b)=>String(a[sortK]).localeCompare(String(b[sortK]),'sq',{{numeric:true}})*sortD);
shown=0;document.getElementById('tb').innerHTML='';more();}}
function more(){{const tb=document.getElementById('tb');let h='';
for(const r of rows.slice(shown,shown+PAGE)){{const sig=r.siguria?` <span class="p">(${{Math.round(r.siguria*100)}}%)</span>`:'';
h+=`<tr><td class="t">${{r.thumb?`<a href="${{esc('file:///'+r.shtegu.replaceAll('\\\\','/'))}}" target="_blank"><img loading="lazy" src="${{esc(r.thumb)}}"></a>`:''}}</td>
<td>${{esc(r.statusi)}}<div class="p">${{esc(r.detaje)}}</div></td><td>${{esc(r.emri)}}<div class="p">${{esc(r.shtegu)}}</div></td>
<td>${{esc(r.data)}}<div class="p">${{esc(({{exif:'📷 nga fotoja',emri:'🏷️ nga emri i skedarit',skedari:'🗂️ nga data e skedarit'}})[r.burimi_datës]||'')}}</div></td><td>${{esc(r.kategoria)}}${{sig}}</td>
<td>${{esc(r.personat)}}</td><td>${{esc(r.vendi)}}</td><td>${{esc(r.kamera)}}</td><td>${{esc(r.kb)}}</td></tr>`;}}
tb.insertAdjacentHTML('beforeend',h);shown+=PAGE;
document.getElementById('cnt').textContent=`Po shfaqen ${{Math.min(shown,rows.length)}} nga ${{rows.length}} skedarë`;
document.getElementById('more').style.display=shown<rows.length?'':'none';}}
document.getElementById('q').addEventListener('input',filt);document.getElementById('fs').addEventListener('change',filt);
document.getElementById('more').addEventListener('click',more);
document.querySelectorAll('th[data-k]').forEach(th=>th.addEventListener('click',()=>{{const k=th.dataset.k;if(!k)return;
sortD=sortK===k?-sortD:1;sortK=k;filt();}}));
filt();
</script></body></html>"""
