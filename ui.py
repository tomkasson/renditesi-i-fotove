"""Pjesët e përbashkëta të Renditësit (faqet Skano · Personat · Rendit): konstantet, gjendja e personave,
dialogët dhe ndihmësit. Faqet janë te faqet/, hyrja dhe shiriti lart te app.py."""
import datetime as dt
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import streamlit as st

import time as _time

import core
import historiku


def fresh(m):
    """Streamlit nuk i rilexon gjithmonë modulet tona kur ndryshojnë pa u rinisur serveri
    ('module core has no attribute ...'): rilexoje vetë modulin kur skedari është më i ri se ngarkimi."""
    import importlib

    try:
        if os.path.getmtime(m.__file__) > getattr(m, "_LOADED", 0):
            return importlib.reload(m)
    except Exception:
        pass
    return m


core, historiku = fresh(core), fresh(historiku)
for _name in ("pema", "report"):  # importohen më vonë brenda funksioneve: rifreskoji te sys.modules
    if _name in sys.modules:
        fresh(sys.modules[_name])

ss = st.session_state
_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

CAT_LABELS = {}
CAT_REAL = {}
CAT_DEFAULT = []
try:  # etiketat e kategorive (pa ngarkuar modelet)
    import ai

    ai = fresh(ai)
    CAT_LABELS = dict(ai.CAT_LABEL, video="Video")
    CAT_REAL, CAT_DEFAULT = ai.CAT_REAL, ai.CAT_DEFAULT
except Exception:
    ai = None

PER_PERSON = "Çdo person → Viti"
PRESETS = {  # emri → nivelet e dosjeve (None = zgjidh vetë)
    PER_PERSON: ["Personi", "Viti"],
    "Viti → Muaji": ["Viti", "Muaji"],
    "Viti": ["Viti"],
    "Personi kryesor → Viti": ["Personi", "Viti"],
    "Përmbajtja → Viti": ["Përmbajtja", "Viti"],
    "Viti → Përmbajtja": ["Viti", "Përmbajtja"],
    "Vendi → Qyteti": ["Vendi", "Qyteti"],
    "Viti → Vendi": ["Viti", "Vendi"],
    "Strukturë tjetër…": None,
}
PRESET_ICON = {PER_PERSON: ":material/groups:", "Viti → Muaji": ":material/calendar_month:",
               "Viti": ":material/event:", "Personi kryesor → Viti": ":material/person:",
               "Përmbajtja → Viti": ":material/category:", "Viti → Përmbajtja": ":material/category:",
               "Vendi → Qyteti": ":material/location_on:", "Viti → Vendi": ":material/location_on:",
               "Strukturë tjetër…": ":material/tune:"}
PRESET_HELP = {PER_PERSON: "Fotoja shkon te dosja e secilit person që është në të (kopjet shtesë nuk zënë vend)."}


def pick_folder():
    code = (
        "import tkinter as tk;from tkinter import filedialog;r=tk.Tk();r.withdraw();"
        "r.attributes('-topmost',True);print(filedialog.askdirectory())"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    p = res.stdout.strip()
    return os.path.normpath(p) if p else None


def reset():
    ss.records = None
    ss.groups = None


def add_source():
    p = pick_folder()
    if p:
        lines = [l for l in ss.sources.splitlines() if l.strip()]
        if p not in lines:
            lines.append(p)
        ss.sources = "\n".join(lines)
        reset()


def whole_pc():
    ss.sources = "\n".join(core.default_sources())
    reset()


def pick_out():
    p = pick_folder()
    if p:
        ss.out = p


def open_file(p):
    if not os.environ.get("RENDITESI_NO_OPEN"):  # testet automatike nuk hapin dritare
        os.startfile(p)


def face_strip(faces, limit):
    """Pamje të vogla të fytyrave (një për foto), të përgatitura paralelisht."""
    todo, seen = [], set()
    for r, f in faces:
        if r["path"] in seen:
            continue
        seen.add(r["path"])
        todo.append((r["path"], tuple(f["box"])))
        if len(todo) >= limit:
            break
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda a: ai.face_thumb(*a), todo))
    return [t for t in res if t]


def face_items(faces, limit):
    """[(shtegu, pamja e fytyrës)], një për foto."""
    todo, seen = [], set()
    for r, f in faces:
        if r["path"] not in seen:
            seen.add(r["path"])
            todo.append((r["path"], tuple(f["box"])))
        if len(todo) >= limit:
            break
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda a: ai.face_thumb(*a), todo))
    return [(p, t) for (p, _), t in zip(todo, res) if t]


def photo_items(paths):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ai.photo_thumb, paths))
    return [(p, t) for p, t in zip(paths, res) if t]


def photo_strip(paths):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(ai.photo_thumb, paths))
    return [(t, os.path.basename(p)) for t, p in zip(res, paths) if t]


def _more():
    ss.dlg_n = ss.get("dlg_n", 60) + 60


# ---------- Personat: një person = një ose disa grupe fytyrash ----------
# AI-ja shpesh e ndan të njëjtin person në disa grupe (mosha, syze, dritë). Përdoruesi i bashkon:
# ss.owner {grupi: grupi_kryesor}, ss.names {grupi_kryesor: emri}, ss.nope {frozenset(a, b)} = "nuk janë i njëjti",
# ss.removed {grupi: {fotot}} = "❌ Jo ky", ss.excl {grupi_kryesor} = hequr nga 'Përfshi'.
AUTO_PICK = 0.80  # te "➕ Gjej të tjera", grupet mbi këtë ngjashmëri dalin të shënuara
SUGGEST_MIN = 0.45  # nën këtë nuk sugjerohen fare
FACE_SUGGEST_MIN = 0.55  # fytyrë e hequr → person tjetër (fytyrat e vërteta i ngjajnë qendrës së tyre ≥0.64 në 95%)


def gk(name):
    """Çelës widget-i që ndryshon me çdo skanim (që emrat e vjetër të mos dalin te grupet e reja)."""
    return f"{name}__{ss.get('gen', 0)}"


def init_people(groups):
    ss.gen = ss.get("gen", 0) + 1
    ss.owner, ss.names, ss.nope, ss.excl, ss.removed, ss.covers = {}, {}, set(), set(), {}, {}
    # fytyrat e hequra: ss.moved {(grupi, foto): grupi i personit të ri}, ss.dismissed {(grupi, foto)} = "askush",
    # ss.face_no {(grupi, foto): {grupet}} = personat ku u tha "jo" (mos i sugjero më)
    ss.moved, ss.dismissed, ss.face_no, ss.gidx = {}, set(), {}, {}
    ss.gpaths = [frozenset(r["path"] for r, _ in g["faces"]) for g in groups]
    ss.C = np.stack([g["centroid"] for g in groups]).astype(np.float32) if groups else np.zeros((0, 128), np.float32)
    first = {}
    for g in groups:  # grupet që njohën të njëjtin emër nga herët e kaluara = një person
        n = (g.get("name") or "").strip()
        if n:
            ss.names[g["id"]] = n
            if n.casefold() in first:
                merge(first[n.casefold()], g["id"])
            else:
                first[n.casefold()] = g["id"]
    apply_fixes(groups)
    ss.people_for = id(groups)


def apply_fixes(groups):
    """Zbaton vendimet e ruajtura për fytyra të veçanta ('nuk është X', 'është Y', 'askush')."""
    if ai is None:
        return
    try:
        fixes = ai.load_fixes()
    except Exception as e:
        ss.save_err = f"Korrigjimet e fotove nuk u lexuan: {e}"
        return
    if not fixes:
        return
    want = {os.path.normcase(e["path"]) for e in fixes}
    where = {}  # foto → [(grupi, fytyra)]
    for g in groups:
        for x in g["faces"]:
            p = os.path.normcase(x[0]["path"])
            if p in want:
                where.setdefault(p, []).append((g["id"], x))
    by_name = {}
    for r, n in ss.names.items():
        if n.strip():
            by_name.setdefault(n.strip().casefold(), root(r))
    for e in fixes:
        cand = where.get(os.path.normcase(e["path"]))
        if not cand:
            continue
        emb = np.asarray(e["emb"], dtype=np.float32)
        sims = [float(x[1]["emb"] @ emb) for _, x in cand]
        i = int(np.argmax(sims))
        if sims[i] < ai.FIX_SAME:
            continue
        g, x = cand[i]
        p, key = x[0]["path"], (g, x[0]["path"])
        own = ss.names.get(root(g), "").strip().casefold()
        no = {n.casefold() for n in e.get("jo", [])}
        for n in no:
            if n in by_name:
                ss.face_no.setdefault(key, set()).add(by_name[n])
        po = (e.get("po") or "").strip().casefold()
        if po and po != own and po not in by_name:  # p.sh. një emër i shtuar te Databaza: s'ka grup në këtë skanim → person i ri
            by_name[po] = new_person(e["po"].strip(), x[1]["emb"])
        if po and po != own and po in by_name:
            removed(g).add(p)
            ss.moved[key] = by_name[po]
        elif own and own in no:
            removed(g).add(p)
            if e.get("askush"):
                ss.dismissed.add(key)


def ensure_people_state():
    """Gjendja e fytyrave të hequra (moved/dismissed/face_no/gidx). Mund të mungojë kur rifreskohet vetëm
    një dialog (fragment, pa rrjedhën kryesore) në një sesion të nisur me version tjetër të app.py."""
    if "moved" not in ss:
        ss.moved, ss.dismissed, ss.face_no, ss.gidx = {}, set(), {}, {}
        if ss.get("groups"):
            apply_fixes(ss.groups)


def root(gid):
    return ss.owner.get(gid, gid)


def members(r):
    return [r] + [g for g, o in ss.owner.items() if o == r]


def removed(gid):
    """Fotot e këtij grupi që përdoruesi i shënoi 'nuk është ky person'."""
    return ss.setdefault("removed", {}).setdefault(gid, set())


def person_paths(r):
    gp, out = ss.gpaths, set()
    for g in members(r):
        out |= gp[g] - removed(g)
    return out | {p for _, p in moved_in(r)}


def moved_in(r):
    """Fytyrat e hequra nga persona të tjerë që përdoruesi ia dha këtij personi: [(grupi, foto)]."""
    own = ss.owner
    return [k for k, t in ss.get("moved", {}).items() if own.get(t, t) == r]


def face_of(g, p):
    """(rekordi, fytyra) e grupit g te fotoja p."""
    idx = ss.setdefault("gidx", {})
    if g not in idx:
        idx[g] = {}
        for x in ss.groups[g]["faces"]:
            idx[g].setdefault(x[0]["path"], x)
    return idx[g].get(p)


def homeless():
    """Fytyrat e hequra ('❌ Jo ky' ose pa ✔ te ➕) që ende s'kanë person tjetër: [(grupi, foto)]."""
    mv, dis = ss.get("moved", {}), ss.get("dismissed", set())
    return [(g, p) for g, ps in sorted(ss.get("removed", {}).items()) for p in sorted(ps)
            if (g, p) not in mv and (g, p) not in dis and face_of(g, p)]


def suggest(g, p, k=2):
    """Personat (nga ata që shfaqen) më të ngjashëm me fytyrën (g, p): [(personi, ngjashmëria)]."""
    x = face_of(g, p)
    if x is None:
        return []
    C, owner = ss.C, ss.owner
    roots = np.array([owner.get(i, i) for i in range(len(C))])
    best = np.full(len(C), -1.0, dtype=np.float32)
    np.maximum.at(best, roots, C @ x[1]["emb"])
    skip = {root(g)} | {root(q) for q in ss.get("face_no", {}).get((g, p), ())}
    shown = ss.get("shown_set") or set(roots.tolist())
    out = [(int(q), float(best[q])) for q in np.argsort(-best)
           if best[q] >= FACE_SUGGEST_MIN and int(q) in shown and int(q) not in skip]
    return out[:k]


def person_faces(r, mix=True):
    """Fytyrat e personit pa ato '❌ Jo ky'. mix=True: me radhë nga çdo pjesë (që të duken të gjitha)."""
    gp, groups = ss.gpaths, ss.groups
    parts = sorted(members(r), key=lambda g: -len(gp[g]))
    lists = []
    for g in parts:
        rm = removed(g)
        lists.append([x for x in groups[g]["faces"] if x[0]["path"] not in rm] if rm else groups[g]["faces"])
    extra = [x for x in (face_of(g, p) for g, p in moved_in(r)) if x]
    if extra:
        lists.append(extra)
    if not mix:
        return [x for lst in lists for x in lst]
    out, i = [], 0
    while any(i < len(lst) for lst in lists):
        out += [lst[i] for lst in lists if i < len(lst)]
        i += 1
    return out


def plabel(r):
    """Emri i personit; një grup i bashkuar më vonë merr emrin e personit kryesor (jo 'Personi 4')."""
    if r is None:
        return "?"
    rr = root(r) if "owner" in ss else r
    n = (ss.names.get(rr, "") or ss.names.get(r, "")).strip()
    return n or f"Personi {rr + 1} · pa emër"


def merge(a, b):
    """Bashkon dy persona; mbetet kryesor ai me më shumë foto."""
    ra, rb = root(a), root(b)
    if ra == rb:
        return
    size = lambda r: sum(len(ss.gpaths[g]) for g in members(r))
    keep, other = (ra, rb) if size(ra) >= size(rb) else (rb, ra)
    if not ss.names.get(keep, "").strip() and ss.names.get(other, "").strip():
        ss.names[keep] = ss.names[other]
        _drop_name_widgets(keep)  # që fusha e emrit të marrë emrin e ri
    for g in members(other):
        ss.owner[g] = keep
    if other in ss.excl and keep not in ss.excl:
        ss.excl.discard(other)


def candidates(r, min_sim=SUGGEST_MIN):
    """Personat e tjerë që i ngjajnë r-së: [(grupi_kryesor, ngjashmëria)], më i ngjashmi i pari.
    Ngjashmëria = më e larta midis çdo pjese të njërit dhe çdo pjese të tjetrit."""
    mem = members(r)
    C, owner = ss.C, ss.owner
    best_g = (C[mem] @ C.T).max(0)
    roots = np.array([owner.get(g, g) for g in range(len(C))])
    best = np.full(len(C), -1.0, dtype=np.float32)
    np.maximum.at(best, roots, best_g)
    best[r] = -1
    no = {x for pair in ss.nope if pair & set(mem) for x in pair}
    for q in {root(x) for x in no}:
        best[q] = -1
    idx = np.where(best >= min_sim)[0]
    return [(int(q), float(best[q])) for q in idx[np.argsort(-best[idx])]]


def part_centroid(g):
    """Qendra e një grupi pa fotot '❌ Jo ky' (që kujtesa të mos mësojë fytyra të gabuara)."""
    rm = removed(g)
    if rm:
        embs = [f["emb"] for x, f in ss.groups[g]["faces"] if x["path"] not in rm]
        if embs:
            c = np.mean(embs, 0)
            return c / (np.linalg.norm(c) + 1e-9)
    return ss.C[g]


def persist(r, steal_from=()):
    """Ruan përgjithmonë (cache/personat.json): emri ↔ të gjitha pjesët e personit.
    steal_from: emri i vjetër i kartës kur riemërtohet (vetëm atij i hiqen pjesët)."""
    r = root(r)
    n = ss.names.get(r, "").strip()
    if n and ai is not None:
        try:
            ai.remember(n, [part_centroid(g) for g in members(r)], steal_from=steal_from)
        except Exception as e:
            ss.save_err = f"Emri '{n}' nuk u ruajt: {e}"
        # edhe vendimet për fytyra të veçanta (p.sh. u hoqën kur personi s'kishte ende emër)
        ops = [(g, p, "jo", n) for g in members(r) for p in removed(g)]
        ops += [(g, p, "po", n) for g, p in moved_in(r)]
        _fix(ops)


def _fix(ops):
    """Ruan përgjithmonë vendimet për fytyra: [(grupi, foto, veprimi, emri)]; veprimi: jo/unjo/po/unpo/askush/unaskush."""
    items = []
    for g, p, op, n in ops:
        x = face_of(g, p)
        if x is not None and (n or op.endswith("askush")):
            items.append((p, x[1]["emb"], op, n))
    if items and ai is not None:
        try:
            ai.fix_faces(items)
        except Exception as e:
            ss.save_err = f"Korrigjimi i fotos nuk u ruajt: {e}"


def pname(r):
    """Emri i personit (bosh nëse s'ka)."""
    return ss.names.get(root(r), "").strip()


def _forget_parts(gs, names):
    """Këto pjesë i hiqen vetëm emrit/emrave të dhënë (p.sh. emrit të kartës), jo të gjithë kujtesës."""
    if ai is not None and any(names):
        try:
            ai.forget([part_centroid(g) for g in gs] + [ss.C[g] for g in gs], names)
        except Exception as e:
            ss.save_err = f"Kujtesa nuk u përditësua: {e}"


def _merge_cb(a, b):
    merge(a, b)
    persist(a)


def _nope_cb(a, b):
    ss.nope.add(frozenset((a, b)))


def desel(r, q):
    """Fotot e grupit q që përdoruesi i hoqi te '🔍 Hap' (nuk janë personi r)."""
    return ss.setdefault("desel", {}).setdefault((r, q), set())


def _pick_key(r, q):
    return gk(f"pick_{r}_{q}")


def _sel_key(r, q, p):
    import hashlib

    return gk(f"sel_{r}_{q}_{hashlib.md5(p.encode()).hexdigest()[:12]}")


def _on_pick(r, q):
    ss.setdefault("picks", {})[(r, q)] = bool(ss.get(_pick_key(r, q)))


def _toggle_sel(r, q, p):
    (desel(r, q).discard if ss.get(_sel_key(r, q, p)) else desel(r, q).add)(p)


def _sel_all(r, q, paths, on):
    d = desel(r, q)
    d.clear() if on else d.update(paths)
    for p in paths:
        ss[_sel_key(r, q, p)] = on


def _open_detail(q):
    ss.find_open, ss.fd_n = q, 60


def _close_detail(r, q, k):
    ss.find_open = None
    ss.setdefault("picks", {})[(r, q)] = k > 0
    ss[_pick_key(r, q)] = k > 0


def _merge_picked(r, cands):
    picks, k = ss.setdefault("picks", {}), 0
    for q, s in cands:
        if picks.get((r, q), s >= AUTO_PICK):
            d = ss.get("desel", {}).get((r, q), set())
            if d >= person_paths(q):  # asnjë foto e zgjedhur
                continue
            for g in members(q):  # fotot pa shenjë nuk bashkohen: shkojnë te 'Të tjerë'
                for p in d & ss.gpaths[g]:
                    removed(g).add(p)
            merge(r, q)
            k += 1
        elif s >= AUTO_PICK:  # ishte i shënuar dhe përdoruesi e hoqi = "nuk është ky"
            ss.nope.add(frozenset((r, q)))
    if k:
        persist(r)
        ss.merged_msg = (f"🔗 U bashkuan {k} grupe: tani {plabel(root(r))} ka {len(person_paths(root(r)))} foto. "
                         "Lista më poshtë u rifreskua me personin e bashkuar; mund të ketë edhe të tjerë.")


def _merge_one(r, q, s):
    ss.setdefault("picks", {})[(r, q)] = True
    ss.find_open = None
    _merge_picked(r, [(q, s)])


def _split(r, g):
    n = ss.names.get(root(r), "").strip()
    _forget_parts([g], [n])
    if n and ai is not None:
        try:
            ai.reject(n, [part_centroid(g), ss.C[g]])
        except Exception as e:
            ss.save_err = f"Kujtesa nuk u përditësua: {e}"
    ss.owner.pop(g, None)
    ss.names.pop(g, None)
    _drop_name_widgets(g)
    ss.nope.add(frozenset((r, g)))
    persist(r)


def _drop_name_widgets(g):
    """Fushat e emrit (karta dhe dritarja e vogël) rimarrin emrin nga ss.names."""
    for k in ("name", "tname", "dbname"):
        ss.pop(gk(f"{k}_{g}"), None)


def _on_name(r, key=None):
    n = (ss.get(key or gk(f"name_{r}")) or "").strip()
    old = ss.names.get(r, "").strip()
    ss.names[r] = n
    if n:  # i njëjti emër te dy karta = i njëjti person
        for q in {root(g) for g in ss.names if root(g) != r and ss.names[g].strip().casefold() == n.casefold()}:
            merge(r, q)
        renamed = old and old.casefold() != n.casefold()
        persist(r, steal_from=(old,) if renamed else ())  # riemërtim: pjesët i hiqen vetëm emrit të vjetër
    elif old:  # emri u fshi: këto pjesë nuk i përkasin më atij emri (vetëm atij)
        _forget_parts(members(r), [old])


def _on_inc(r):
    (ss.excl.discard if ss.get(gk(f"inc_{r}")) else ss.excl.add)(r)


def _mark_not(r, p):
    """'❌ Jo ky' te 👀: fotoja del nga personi r (nga të gjitha pjesët ku ndodhet, ose nga ato të dhëna me ➡)."""
    r, n, ops = root(r), pname(r), []
    for g in members(r):
        if p in ss.gpaths[g] and p not in removed(g):
            removed(g).add(p)
            ops.append((g, p, "jo", n))
    for g, q in moved_in(r):
        if q == p:
            ss.moved.pop((g, p), None)
            ss.face_no.setdefault((g, p), set()).add(r)
            ops += [(g, p, "unpo", n), (g, p, "jo", n)]
    _fix(ops)


def _restore(g, p):
    """↩ Ktheje: fytyra kthehet te personi i saj i parë."""
    r = root(g)
    ops = [(g, p, "unjo", pname(r)), (g, p, "unaskush", "")]
    t = ss.moved.pop((g, p), None)
    if t is not None:
        ops.append((g, p, "unpo", pname(t)))
    ss.dismissed.discard((g, p))
    removed(g).discard(p)
    ss.pop(_rm_key(r, p), None)
    _fix(ops)


def _assign(g, p, q):
    """➡ fytyra (g, p) i përket personit q."""
    q, ops = root(q), []
    old = ss.moved.get((g, p))
    if old is not None:
        ops.append((g, p, "unpo", pname(old)))
    ss.moved[(g, p)] = q
    ss.dismissed.discard((g, p))
    ss.pop(_rm_key(q, p), None)
    ss.face_no.get((g, p), set()).discard(q)
    _fix(ops + [(g, p, "unaskush", ""), (g, p, "po", pname(q))])


def new_person(name, emb):
    """Person i ri pa grup fytyrash (p.sh. i shtuar te Databaza): një 'grup' bosh me qendër = fytyra e parë.
    Fotot i jepen me ➡ (ss.moved); emri ruhet te kujtesa me persist()."""
    gid = len(ss.groups)
    emb = np.asarray(emb, dtype=np.float32)
    ss.groups.append({"id": gid, "faces": [], "centroid": emb, "name": name, "manual": True})
    ss.gpaths.append(frozenset())
    ss.C = np.vstack([ss.C, emb[None]])
    ss.names[gid] = name
    return gid


def target_options(exclude=()):
    """{etiketa: personi} për listat 'Dërgo te': personat e shfaqur + emrat që janë vetëm te pema/Databaza
    (personi = None: krijohet kur zgjidhet)."""
    ex = {root(q) for q in exclude if q is not None}
    opts = {}
    for q in ss.get("shown_list", []):
        if root(q) not in ex:
            opts.setdefault(plabel(q), root(q))
    try:
        import pema

        extra = [n for n in pema.in_tree(pema.load()) if not n.startswith(pema.VIRTUAL)]
    except Exception:
        extra = []
    have = {k.casefold() for k in opts} | {ss.names.get(root(q), "").strip().casefold() for q in ex}
    for n in sorted(extra, key=str.casefold):
        if n.casefold() not in have:
            opts[n] = None
    return opts


SIMILAR_FACE = 0.60  # "edhe këto i ngjajnë": fytyrë pa vend ↔ fytyrat e personit


def assign_label(g, p, label):
    """➡ sipas etiketës: person ekzistues, emër nga pema/Databaza, ose emër i ri i shkruar (krijohet personi).
    Kthen personin (ose None)."""
    label = " ".join((label or "").split())
    if not label or face_of(g, p) is None:
        return None
    q = target_options().get(label)
    if q is None:
        q = next((root(r) for r, n in ss.names.items() if n.strip().casefold() == label.casefold()), None)
    if q is None:
        q = new_person(label, face_of(g, p)[1]["emb"])
        _assign(g, p, q)
        persist(q)  # kujtesa mëson fytyrën: herës tjetër njihet vetë
        return q
    _assign(g, p, q)
    return q


def _offer(q):
    """Pas një caktimi: kërko vetë fotot pa vend dhe grupet pa emër që i ngjajnë këtij personi (paneli sipër)."""
    if q is not None:
        ss.offer = root(q)


def _assign_offer(g, p, q):
    _assign(g, p, q)
    _offer(q)


def _assign_label_cb(g, p, key):
    v = ss.get(key)
    if v:
        _offer(assign_label(g, p, v))
    ss.pop(key, None)


def _chk(g, p):
    return _fkey("chk", g, p)


def _sel_items(items):
    return [(g, p) for g, p in items if ss.get(_chk(g, p))]


def _clear_sel(items):
    for g, p in items:
        ss.pop(_chk(g, p), None)


def _select_all(items, key):
    on = bool(ss.get(key))
    for g, p in items:
        ss[_chk(g, p)] = on


def _bulk(items, action, key=None, tag=""):
    """Veprim për të gjitha fotot e zgjedhura: 'to' (cakto te personi/emri), 'no' (askush), 'back' (ktheji)."""
    sel = _sel_items(items)
    if action == "to":
        label, q = ss.get(key), None
        for g, p in sel:
            q = assign_label(g, p, label) or q
        ss.pop(key, None)
        _offer(q)
    elif action == "no":
        for g, p in sel:
            _dismiss(g, p)
    elif action == "back":
        for g, p in sel:
            _restore(g, p)
    _clear_sel(items)
    ss.pop(gk(f"chkall_{tag}"), None)


def similar_to(q):
    """(fotot pa vend që i ngjajnë personit q, grupet pa emër që i ngjajnë shumë): [(g, p)], [(grupi, ngjashmëria)]."""
    q = root(q)
    embs = [f["emb"] for _, f in person_faces(q, mix=False)[:400]] + [ss.C[q]]
    E = np.stack(embs).astype(np.float32)
    faces = []
    for g, p in homeless():
        x = face_of(g, p)
        if x is not None and float((E @ x[1]["emb"]).max()) >= SIMILAR_FACE and q not in ss.face_no.get((g, p), ()):
            faces.append((g, p))
    groups = [(o, s) for o, s in candidates(q, AUTO_PICK) if not pname(o)]
    return faces, groups


def _offer_take(q, faces):
    for g, p in faces:
        _assign(g, p, q)
    ss.offer = root(q)  # rillogarit: mbase dalin edhe të tjera


def _offer_mark(faces):
    for g, p in faces:
        ss[_chk(g, p)] = True


def _offer_merge(q, groups):
    for o, _ in groups:
        merge(q, o)
    persist(root(q))
    ss.offer = root(q)


def offer_panel():
    """Pas çdo caktimi: AI-ja kërkon vetë të tjera që i ngjajnë personit, pa skanuar nga fillimi."""
    q = ss.get("offer")
    if q is None:
        return
    q = root(q)
    faces, groups = similar_to(q)
    if not faces and not groups:
        st.success(f"U caktua te **{plabel(q)}**. Nuk ka foto të tjera pa vend që i ngjajnë.",
                   icon=":material/check_circle:")
        ss.pop("offer", None)
        return
    with st.container(border=True):
        st.markdown(f":material/auto_awesome: **{plabel(q)}**: AI-ja gjeti të tjera që i ngjajnë")
        if faces:
            c1, c2, c3 = st.columns([3, 1.4, 1.8], vertical_alignment="center")
            c1.caption(f"**{len(faces)} foto pa vend** i ngjajnë mbi {int(SIMILAR_FACE * 100)}%")
            c2.button("Shëno ato", icon=":material/check_box:", key=gk("offer_mark"), on_click=_offer_mark,
                      args=(faces,), width="stretch", help="I shënon te lista: kontrolloji, pastaj Cakto")
            c3.button(f"Cakto të gjitha te {plabel(q)}", icon=":material/done_all:", type="primary",
                      key=gk("offer_take"), on_click=_offer_take, args=(q, faces), width="stretch")
            strip = face_strip([face_of(g, p) for g, p in faces[:12]], 12)
            if strip:
                st.image(strip, width=48)
        if groups:
            n_ph = sum(len(person_paths(o)) for o, _ in groups)
            c1, c2 = st.columns([3, 3.2], vertical_alignment="center")
            c1.caption(f"**{len(groups)} grupe pa emër** ({n_ph} foto) i ngjajnë mbi {int(AUTO_PICK * 100)}%")
            c2.button(f"Bashkoji me {plabel(q)}", icon=":material/merge:", key=gk("offer_merge"),
                      on_click=_offer_merge, args=(q, groups), width="stretch",
                      help="Fotot e këtyre grupeve i kalojnë këtij personi (kontrolloji më pas te Fotot e tij)")
        st.button("Jo, mjafton", icon=":material/close:", key=gk("offer_no"), type="tertiary",
                  on_click=lambda: ss.pop("offer", None))


def bulk_bar(items, tag, bottom=False):
    """Paneli i zgjedhjes: 'N foto të zgjedhura → cakto te [personi]' (sipër dhe poshtë listës)."""
    sel = _sel_items(items)
    k = f"{tag}_b" if bottom else tag
    if bottom and not sel:
        return
    with st.container(border=True):
        if sel:
            st.markdown(f":material/check_box: **{len(sel)} foto të zgjedhura** → cakto te:")
        b1, b2, b3, b4, b5 = st.columns([1.6, 3.2, 1.2, 1.2, 1.2], vertical_alignment="center", gap="small")
        if not bottom:
            ak = gk(f"chkall_{tag}")
            b1.checkbox(f"Zgjidh të gjitha ({len(items)})", key=ak, on_change=_select_all, args=(items, ak))
        tk = gk(f"bulkto_{k}")
        b2.selectbox("Cakto te", list(target_options()), index=None, key=tk, accept_new_options=True,
                     placeholder="Personi... (ose shkruaj emër të ri)", label_visibility="collapsed")
        b3.button(f"Cakto ({len(sel)})", icon=":material/arrow_forward:", type="primary", width="stretch",
                  key=gk(f"bulkgo_{k}"), disabled=not (sel and ss.get(tk)), on_click=_bulk,
                  args=(items, "to", tk, tag))
        b4.button("Askush", icon=":material/block:", width="stretch", key=gk(f"bulkno_{k}"), disabled=not sel,
                  on_click=_bulk, args=(items, "no", None, tag), help="Nuk janë asnjë nga këta: mbeten te 'Të tjerë'")
        b5.button("Ktheji", icon=":material/undo:", width="stretch", key=gk(f"bulkback_{k}"), disabled=not sel,
                  on_click=_bulk, args=(items, "back", None, tag), help="Gabova: kthehen te personi i tyre i parë")
        if not sel:
            st.caption(":material/check_box: Shëno fotot me kutinë majtas: këtu del 'N foto të zgjedhura → cakto te'. "
                       "Te lista ka edhe emrat e Databazës (edhe pa foto), ose shkruaj një emër të ri.")


def _assign_sel(g, p, key):
    q = ss.get(key)
    if q is not None:
        _assign(g, p, q)
    ss.pop(key, None)


def _dismiss(g, p):
    """🚫 Askush: mbetet te 'Të tjerë' dhe del nga kutia."""
    old = ss.moved.pop((g, p), None)
    ss.dismissed.add((g, p))
    _fix(([(g, p, "unpo", pname(old))] if old is not None else []) + [(g, p, "askush", "")])


def _fkey(kind, g, p):
    import hashlib

    return gk(f"{kind}_{g}_{hashlib.md5(p.encode()).hexdigest()[:12]}")


FIX_K = 6  # sa foto në rresht te "Fotot pa vend" / "Të hequrat"


def fix_tile(g, p, thumb, sug):
    """Një fytyrë e hequr si kartë e vogël: kutia e zgjedhjes, fytyra, nga kush u hoq, sugjerimi kryesor dhe
    menuja ⋯ (sugjerimet e tjera, Tjetër / emër i ri, Askush, Ktheje, Hap foton)."""
    r = root(g)
    t = ss.moved.get((g, p))
    with st.container(border=True, gap="small"):
        st.checkbox("Zgjidh", key=_chk(g, p))
        if thumb:
            st.image(thumb, width="stretch")
        state = (f" · :green[→ {plabel(t)}]" if t is not None else " · :gray[askush]" if (g, p) in ss.dismissed
                 else "")
        st.caption(f"nga **{plabel(r)}**{state}")
        if sug:
            q, s = sug[0]
            st.button(f"{plabel(q)} {int(s * 100)}%", icon=":material/arrow_forward:", key=_fkey(f"to{q}", g, p),
                      on_click=_assign_offer, args=(g, p, q), width="stretch", type="primary",
                      help=f"Kjo fytyrë i ngjan {plabel(q)} {int(s * 100)}%: shtyp nëse është ai/ajo")
        with st.popover("Më shumë", icon=":material/more_horiz:", width="stretch"):
            st.caption(os.path.basename(p))
            for q, s in sug[1:]:
                st.button(f"{plabel(q)} {int(s * 100)}%", icon=":material/arrow_forward:", key=_fkey(f"to{q}", g, p),
                          on_click=_assign_offer, args=(g, p, q), width="stretch")
            k = _fkey("sel", g, p)
            st.selectbox("Tjetër", list(target_options(exclude=(r, t))), index=None, key=k, accept_new_options=True,
                         placeholder="Tjetër / emër i ri...", on_change=_assign_label_cb, args=(g, p, k))
            if (g, p) not in ss.dismissed:
                st.button("Askush", icon=":material/block:", key=_fkey("no", g, p), on_click=_dismiss, args=(g, p),
                          width="stretch", help="Nuk është asnjë nga këta: mbetet te 'Të tjerë'")
            st.button(f"Ktheje te {plabel(r)}", icon=":material/undo:", key=_fkey("back", g, p), on_click=_restore,
                      args=(g, p), width="stretch", help="Gabova: fotoja kthehet te personi i saj i parë")
            if st.button("Hap foton", icon=":material/open_in_new:", key=_fkey("open", g, p), width="stretch"):
                open_file(p)


def fix_rows(items, tag="lista"):
    """Fytyrat e hequra si rrjetë (FIX_K në rresht), të renditura sipas sugjerimit: fytyrat që i ngjajnë të njëjtit
    person dalin bashkë, që të shënohen e caktohen njëherësh."""
    from concurrent.futures import ThreadPoolExecutor

    offer_panel()
    if len(items) > 1:
        bulk_bar(items, tag)
    sugs = {(g, p): ([] if ss.moved.get((g, p)) is not None or (g, p) in ss.dismissed else suggest(g, p, k=3))
            for g, p in items}
    items = sorted(items, key=lambda it: (plabel(sugs[it][0][0]).casefold() if sugs[it] else "~",
                                          -(sugs[it][0][1] if sugs[it] else 0)))
    todo = [(p, tuple(face_of(g, p)[1]["box"])) for g, p in items]  # session_state vetëm në fillin kryesor
    with ThreadPoolExecutor(max_workers=8) as ex:
        thumbs = list(ex.map(lambda a: ai.face_thumb(*a, size=160, square=True), todo))
    th_of = dict(zip(items, thumbs))
    groups_ = {}  # sipas sugjerimit kryesor: një titull për çdo person, me "Shëno këto" / "Cakto të gjitha"
    for it in items:
        groups_.setdefault(root(sugs[it][0][0]) if sugs[it] else None, []).append(it)
    for gi, (q, its) in enumerate(groups_.items()):
        h1, h2, h3 = st.columns([3.2, 1.3, 2], vertical_alignment="center")
        if q is None:
            h1.markdown(f"**Pa sugjerim** :gray[· {len(its)} foto]")
        else:
            h1.markdown(f":material/arrow_forward: I ngjajnë **{plabel(q)}** :gray[· {len(its)} foto]")
            h3.button(f"Cakto të gjitha te {plabel(q)}", icon=":material/done_all:", key=gk(f"grp_take_{tag}_{q}"),
                      on_click=_offer_take, args=(q, its), width="stretch", type="primary",
                      help="Kontrolloji më parë: nëse ndonjë s'është ai/ajo, mos e shëno dhe përdor 'Cakto' sipër")
        h2.button("Shëno këto", icon=":material/check_box:", key=gk(f"grp_mark_{tag}_{gi}"), on_click=_offer_mark,
                  args=(its,), width="stretch")
        for i in range(0, len(its), FIX_K):
            cols = st.columns(FIX_K, gap="small")
            for col, it in zip(cols, its[i:i + FIX_K]):
                with col:
                    fix_tile(it[0], it[1], th_of[it], sugs[it])
    if len(items) > 1:
        bulk_bar(items, tag, bottom=True)


def _more_inbox():
    ss.inbox_n = ss.get("inbox_n", 48) + 48


@st.dialog("🧺 Fotot pa vend", width="large", on_dismiss="rerun")
def inbox_dialog():
    ensure_people_state()
    items = homeless()
    if not items:
        st.success("Nuk ka më foto pa vend. 🎉")
    else:
        st.caption(f"**{len(items)} fytyra** që i hoqe nga një person (❌ Jo ky, ose pa ✔ te ➕). AI-ja i krahason me "
                   "personat e tjerë dhe propozon kujt mund t'i përkasin; vendos ti. Deri atëherë shkojnë te "
                   "'Të tjerë'.")
        n = min(ss.get("inbox_n", 48), len(items))
        fix_rows(items[:n], "inbox")
        if n < len(items):
            st.button(f"Shfaq edhe {min(48, len(items) - n)} ({n} nga {len(items)})", icon=":material/expand_more:", on_click=_more_inbox, width="stretch")
    if st.button("✔ Mbaro", type="primary", width="stretch", key="inbox_done"):
        st.rerun()


def _rm_key(r, p):
    import hashlib

    return gk(f"rm_{r}_{hashlib.md5(p.encode()).hexdigest()[:12]}")


@st.dialog("👀 Të gjitha fotot", width="large", on_dismiss="rerun")
def show_all_dialog(r):
    ensure_people_state()
    r = root(r)
    mem = members(r)
    faces = person_faces(r, mix=False)  # pa ato të hequra; bashkë me ato të dhëna me ➡
    paths = list(dict.fromkeys(x[0]["path"] for x in faces))
    gone = [(g, p) for g in sorted(mem) for p in sorted(removed(g)) if face_of(g, p)]
    st.markdown(f"**{plabel(r)}** · {len(paths)} foto" + (f" · ❌ {len(gone)} të hequra" if gone else "")
                + (f" · 🧩 nga {len(mem)} grupe" if len(mem) > 1 else ""))
    st.caption("Shëno **❌ Jo ky** te fotot ku NUK është ky person: fotoja del menjëherë nga lista dhe shkon te "
               "**🧺 Fotot pa vend**, ku AI-ja propozon kujt mund t'i përkasë.")
    view = st.radio("Pamja", ["🙂 Vetëm fytyra (e prerë)", "🖼️ Foto e plotë (pa prerje)"],
                    horizontal=True, key="dlg_view", label_visibility="collapsed")
    n = min(ss.get("dlg_n", 60), len(paths))
    faces_view = view.startswith("🙂")
    with st.spinner("Po përgatis fotot..."):
        items = face_items(faces, n) if faces_view else photo_items(paths[:n])
    k = 6 if faces_view else 4
    cols = st.columns(k)
    for i, (p, t) in enumerate(items):
        with cols[i % k]:
            st.image(t, width="stretch", caption=None if faces_view else os.path.basename(p))
            key = _rm_key(r, p)
            if key not in ss:
                ss[key] = False
            st.checkbox("❌ Jo ky", key=key, on_change=_mark_not, args=(r, p))
    b1, b2 = st.columns(2)
    if n < len(paths):
        b1.button(f"⬇ Shfaq edhe 60 ({n} nga {len(paths)})", on_click=_more, width="stretch")
    if b2.button("✔ Mbaro", type="primary", width="stretch"):
        st.rerun()
    if gone:
        with st.expander(f"❌ Të hequrat nga {plabel(r)} ({len(gone)})"):
            st.caption("**↩ Ktheje** nëse gabove. Ose trego kujt i përket: AI-ja propozon personat më të ngjashëm.")
            fix_rows(gone[:60], f"gone_{r}")
            if len(gone) > 60:
                st.caption(f"... dhe {len(gone) - 60} të tjera te 🧺 Fotot pa vend.")


def _reset_find():
    ss.find_open = None


@st.dialog("➕ Gjej fotot e tjera të këtij personi", width="large", on_dismiss=_reset_find)
def find_dialog(r):
    ensure_people_state()
    r = root(r)  # pas një bashkimi kryesor mund të jetë bërë grupi tjetër
    msg = ss.pop("merged_msg", None)
    if msg:
        st.success(msg)
    cands = candidates(r)
    q_open = ss.get("find_open")
    if q_open is not None:
        sim = dict(cands).get(q_open)
        if sim is not None:
            return _find_detail(r, q_open, sim)
        ss.find_open = None
    st.markdown(f"**{plabel(r)}** · {len(person_paths(r))} foto")
    st.image(face_strip(person_faces(r), 10), width=64)
    if not cands:
        st.info("Nuk ka grupe të tjera që i ngjajnë këtij personi.")
        if st.button("✔ Mbaro", type="primary", width="stretch"):
            st.rerun()
        return
    strong = sum(s >= AUTO_PICK for _, s in cands)
    st.caption(f"Këto {len(cands)} grupe i ngjajnë këtij personi, më të ngjashmit sipër. "
               + (f"{strong} mbi {int(AUTO_PICK * 100)}% janë shënuar vetë; hiq shenjën nga ato që NUK janë ky person. "
                  if strong else "Shëno ato që janë ky person. ")
               + "Me **🔍 Hap** e shikon grupin foto për foto dhe zgjedh vetëm ato ku është ky person. "
               + "Pastaj shtyp **🔗 Bashko**: fotot e tyre shkojnë te ky person.")
    n = min(ss.get("find_n", 25), len(cands))
    shown = cands[:n]
    picks, picked = ss.setdefault("picks", {}), 0
    for q, s in shown:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4], vertical_alignment="center")
            pk = _pick_key(r, q)
            if pk not in ss:
                ss[pk] = picks.get((r, q), s >= AUTO_PICK)
            on = c1.checkbox(f"**{int(s * 100)}%**", key=pk, on_change=_on_pick, args=(r, q))
            picked += on
            qp = person_paths(q)
            d = desel(r, q) & qp
            c1.caption(f"{plabel(q)} · " + (f"✔ {len(qp) - len(d)} nga {len(qp)} foto" if d else f"{len(qp)} foto"))
            c1.button("🔍 Hap", key=gk(f"open_{r}_{q}"), on_click=_open_detail, args=(q,),
                      help="Shiko të gjitha fotot e këtij grupi dhe zgjidh vetëm ato ku është ky person")
            c2.image(face_strip([x for x in person_faces(q) if x[0]["path"] not in d], 8), width=56)
    b1, b2, b3 = st.columns(3)
    if n < len(cands):
        b1.button(f"⬇ Shfaq edhe 25 ({n} nga {len(cands)})", width="stretch",
                  on_click=lambda: ss.update(find_n=ss.get("find_n", 25) + 25))
    b2.button(f"🔗 Bashko {picked} të zgjedhurit", type="primary", width="stretch", disabled=not picked,
              on_click=_merge_picked, args=(r, shown))
    if b3.button("✔ Mbaro", width="stretch"):
        st.rerun()


def _find_detail(r, q, s):
    """Brenda dritares ➕: një grup kandidat foto për foto; përdoruesi lë vetëm ato ku është personi r."""
    d = desel(r, q)
    faces = person_faces(q, mix=False)
    paths = list(dict.fromkeys(x[0]["path"] for x in faces))
    k = sum(p not in d for p in paths)
    st.markdown(f"🔍 **{plabel(q)}** · {len(paths)} foto · {int(s * 100)}% i ngjashëm me **{plabel(r)}**")
    st.caption(f"Kështu duket {plabel(r)}:")
    st.image(face_strip(person_faces(r), 10), width=48)
    st.caption(f"Lër me ✔ vetëm fotot ku është **{plabel(r)}**. Fotot pa ✔ nuk bashkohen me të: shkojnë te "
               "**🧺 Fotot pa vend**, ku AI-ja propozon kujt mund t'i përkasin.")
    a1, a2, a3 = st.columns([1, 1, 2], vertical_alignment="center")
    a1.button("✔ Të gjitha", on_click=_sel_all, args=(r, q, paths, True), width="stretch")
    a2.button("✖ Asnjë", on_click=_sel_all, args=(r, q, paths, False), width="stretch")
    view = a3.radio("Pamja", ["🙂 Fytyra", "🖼️ Foto e plotë"], horizontal=True, key="find_view",
                    label_visibility="collapsed")
    n = min(ss.get("fd_n", 60), len(paths))
    faces_view = view.startswith("🙂")
    with st.spinner("Po përgatis fotot..."):
        items = face_items(faces, n) if faces_view else photo_items(paths[:n])
    kc = 6 if faces_view else 4
    cols = st.columns(kc)
    for i, (p, t) in enumerate(items):
        with cols[i % kc]:
            st.image(t, width="stretch", caption=None if faces_view else os.path.basename(p))
            key = _sel_key(r, q, p)
            if key not in ss:
                ss[key] = p not in d
            st.checkbox("✔ Ky", key=key, on_change=_toggle_sel, args=(r, q, p))
    if n < len(paths):
        st.button(f"⬇ Shfaq edhe 60 ({n} nga {len(paths)})", width="stretch",
                  on_click=lambda: ss.update(fd_n=ss.get("fd_n", 60) + 60))
    b1, b2 = st.columns(2)
    b1.button(f"⬅ Kthehu te lista ({k} nga {len(paths)} të zgjedhura)", on_click=_close_detail, args=(r, q, k),
              width="stretch")
    b2.button(f"🔗 Bashko {k} foto tani", type="primary", disabled=not k, on_click=_merge_one, args=(r, q, s),
              width="stretch")


@st.dialog("🧩 Nga cilat grupe përbëhet", width="large", on_dismiss="rerun")
def parts_dialog(r):
    ensure_people_state()
    r = root(r)
    mem = sorted(members(r), key=lambda g: -len(ss.gpaths[g]))
    st.markdown(f"**{plabel(r)}** · {len(person_paths(r))} foto nga {len(mem)} grupe")
    st.caption("Nëse një grup NUK është ky person, shtyp **✂️ Ndaj**: ai bëhet përsëri person më vete.")
    for g in mem:
        with st.container(border=True):
            c1, c2 = st.columns([1, 4], vertical_alignment="center")
            c1.caption(f"Grupi {g + 1} · {len(ss.gpaths[g] - removed(g))} foto" + (" · kryesori" if g == r else ""))
            if g != r:
                c1.button("✂️ Ndaj", key=gk(f"split_{r}_{g}"), on_click=_split, args=(r, g))
            c2.image(face_strip([x for x in ss.groups[g]["faces"] if x[0]["path"] not in removed(g)], 8), width=56)
    if st.button("✔ Mbaro", type="primary", width="stretch"):
        st.rerun()


def cover(r):
    """(shtegu, kutia) e fytyrës që e përfaqëson personin: nga më të mëdhatë, më tipikja (më afër qendrës)."""
    mem = members(r)
    key = (r, len(mem), sum(len(removed(g)) for g in mem))
    cache = ss.setdefault("covers", {})
    if key not in cache:
        rm = removed(r)
        faces = [x for x in ss.groups[r]["faces"] if x[0]["path"] not in rm][:3000] or person_faces(r)[:3000]
        if not faces:
            return None
        w = np.array([f["box"][2] for _, f in faces])
        sim = np.stack([f["emb"] for _, f in faces]) @ ss.C[r]
        i = int(np.argmax(np.where(w >= np.median(w), sim, -2)))
        cache[key] = (faces[i][0]["path"], tuple(faces[i][1]["box"]))
    return cache[key]


def save_person_index(persons):
    """Për 🌳 Pemën (cache/fotot_e_personave.json): emri → fytyra përfaqësuese + fotot me vitin.
    Bashkë me korrigjimet (❌/➡); shkruhet vetëm kur ndryshon numri i fotove të dikujt."""
    named = {}
    for r in persons:
        n = ss.names.get(r, "").strip()
        if n:
            named.setdefault(n, r)
    sig = tuple(sorted((n, len(person_paths(r))) for n, r in named.items()))
    if not named or sig == ss.get("_index_sig"):
        return
    years = {rec["path"]: str(rec["date"].year) for rec in ss.records or []
             if rec.get("date") and rec.get("date_src") != "skedari"}
    entries = {}
    for n, r in named.items():
        c = cover(r)
        entries[n] = {"fytyra": [c[0], [float(b) for b in c[1]]] if c else None,
                      "fotot": [[p, years.get(p, "")] for p in sorted(person_paths(r))]}
    try:
        import pema

        pema.save_index(entries)
        ss._index_sig = sig
    except Exception as e:
        ss.save_err = f"Fotot e personave për Pemën nuk u ruajtën: {e}"


def _more_grid():
    ss.grid_n = ss.get("grid_n", 60) + 60


GRID_K = 7  # dritare në rresht (faqja është "wide")


def person_grid(tiles):
    """Të gjithë personat si dritare të vogla: fytyra, emri, numri i fotove, Fotot dhe Gjej."""
    if not tiles:
        st.success("Asnjë person këtu: të gjithë kanë emër, ose kërkimi nuk gjeti asgjë.", icon=":material/check_circle:")
        return
    n = min(ss.get("grid_n", 63), len(tiles))
    from concurrent.futures import ThreadPoolExecutor

    covers = [cover(r) for r in tiles[:n]]
    with st.spinner("Po përgatis fytyrat..."), ThreadPoolExecutor(max_workers=8) as ex:
        thumbs = list(ex.map(lambda c: ai.face_thumb(*c, size=160, square=True) if c else None, covers))
    for i in range(0, n, GRID_K):
        cols = st.columns(GRID_K, gap="small")
        for col, r, t in zip(cols, tiles[i:i + GRID_K], thumbs[i:i + GRID_K]):
            with col.container(border=True, gap="small"):
                if t:
                    st.image(t, width="stretch")
                key = gk(f"tname_{r}")
                if key not in ss:
                    ss[key] = ss.names.get(r, "")
                named = ss.names.get(r, "").strip()
                st.text_input(f"Emri i personit {r + 1}", key=key, placeholder="Kush është?",
                              label_visibility="collapsed", on_change=_on_name, args=(r, key),
                              icon=":material/check_circle:" if named else ":material/person:")
                mem = members(r)
                n_paths = len(person_paths(r))
                cands = candidates(r)
                strong = sum(s >= AUTO_PICK for _, s in cands)
                st.caption(f"{n_paths} foto" + (f" · {len(mem)} pjesë" if len(mem) > 1 else "")
                           + (" · :orange[jashtë]" if r in ss.excl else ""))
                b1, b2 = st.columns(2, gap="small")
                if b1.button(":material/photo_library:", key=gk(f"tall_{r}"), width="stretch",
                             help=f"Shiko të gjitha {n_paths} fotot (dhe hiq ato që s'janë ky person)"):
                    ss.dlg_n = 60
                    show_all_dialog(r)
                if b2.button(":material/person_search:" + (f" {strong}" if strong else ""), key=gk(f"tfind_{r}"),
                             width="stretch", disabled=not cands, type="primary" if strong else "secondary",
                             help=(f"Gjej të tjera: {strong} grupe ngjajnë mbi {int(AUTO_PICK * 100)}% (me shumë "
                                   "gjasë po ky person)" if strong
                                   else f"Gjej të tjera: {len(cands)} grupe ngjajnë pak" if cands
                                   else "Asnjë grup tjetër nuk i ngjan")):
                    ss.find_n = 25
                    find_dialog(r)
    if n < len(tiles):
        st.button(f"Shfaq edhe {min(63, len(tiles) - n)} ({n} nga {len(tiles)})", icon=":material/expand_more:",
                  on_click=lambda: ss.update(grid_n=n + 63), width="stretch")


# ---------- Databaza: të gjithë personat në një tabelë + karta e plotë e të zgjedhurit ----------
def _uri(fp):
    import base64

    try:
        with open(fp, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
    except OSError:
        return None


def _pema():
    try:
        import pema

        return pema, pema.load()
    except Exception:
        return None, None


def db_rows(people):
    """Rreshtat e tabelës (një për person): fytyra, emri, fotot, pjesët, gjinia, lidhja te pema, kujtesa."""
    from concurrent.futures import ThreadPoolExecutor

    pm, d = _pema()
    une = (d or {}).get("une", "")
    g = pm.graph(d) if d else None
    known = set(ai.load_people())
    covers = [cover(r) for r in people]
    with ThreadPoolExecutor(max_workers=8) as ex:
        thumbs = list(ex.map(lambda c: ai.face_thumb(*c, size=96, square=True) if c else None, covers))
    rows = []
    for r, t in zip(people, thumbs):
        n = ss.names.get(r, "").strip()
        rec = (d or {}).get("persons", {}).get(n) if n else None
        links = sum(n in (lk["a"], lk["b"]) for lk in d["links"]) if (d and n) else 0
        kin = ""
        if d and n and (rec is not None or links):
            kin = "ti" if n == une else pm.kinship(d, une, n, g)
            if not kin:  # shok/koleg i 'unë'
                kin = next((pm.role(d, lk, n) for lk in d["links"] if lk["lloji"] in pm.OTHER
                            and {lk["a"], lk["b"]} == {n, une}), "")
        rows.append({"Fytyra": _uri(t) if t else None, "Emri": n or f"· Personi {r + 1}",
                     "Foto": len(person_paths(r)), "Pjesë": len(members(r)),
                     "Gjinia": {"m": "M", "f": "F"}.get((rec or {}).get("gjinia", ""), ""),
                     "Te pema": kin or (f"{links} lidhje" if links else ""),
                     "Kujtesa": "po" if n in known else "", "Përfshi": "po" if r not in ss.excl else "jo"})
    return rows


def person_db(people):
    """Databaza: tabelë me të gjithë personat (kërko, rendit, kliko një rresht) + karta e personit djathtas."""
    import pandas as pd

    if not people:
        st.info("Asnjë person për këtë filtër.", icon=":material/search_off:")
        return
    n = min(ss.get("db_n", 150), len(people))
    view = people[:n]
    with st.spinner("Po përgatis tabelën..."):
        rows = db_rows(view)
    left, right = st.columns([3, 2], gap="medium")
    with left:
        ev = st.dataframe(
            pd.DataFrame(rows), key=gk("db_tab"), hide_index=True, on_select="rerun", selection_mode="single-row",
            height=min(640, 38 * len(rows) + 40), row_height=38, width="stretch",
            column_config={
                "Fytyra": st.column_config.ImageColumn("", width=46),
                "Emri": st.column_config.TextColumn("Emri", width="medium"),
                "Foto": st.column_config.ProgressColumn("Foto", min_value=0,
                                                        max_value=max(x["Foto"] for x in rows) or 1,
                                                        format="%d", width="small"),
                "Pjesë": st.column_config.NumberColumn("Pjesë", width=60, help="Sa grupe fytyrash janë bashkuar"),
                "Gjinia": st.column_config.TextColumn("Gjinia", width=60),
                "Te pema": st.column_config.TextColumn("Te pema", help="Si e ke (nga pema e lidhjeve)"),
                "Kujtesa": st.column_config.TextColumn("Kujtesa", width=70,
                                                       help="Emri njihet vetë në çdo skanim tjetër"),
                "Përfshi": st.column_config.TextColumn("Përfshi", width=70,
                                                       help="Fotot e tij kopjohen te dosja e tij (ndryshohet te karta)"),
            })
        if n < len(people):
            st.button(f"Shfaq edhe ({n} nga {len(people)})", icon=":material/expand_more:", type="tertiary",
                      on_click=lambda: ss.update(db_n=n + 150))
    sel = ev.selection.rows if ev is not None and ev.selection else []
    if sel:
        ss.db_sel = view[sel[0]]
    r = ss.get("db_sel")
    with right:
        if r is None or root(r) not in people:
            with st.container(border=True):
                st.markdown("#### :material/touch_app: Zgjidh një person")
                st.caption("Kliko një rresht te tabela: këtu del karta e tij, ku ndryshon emrin, kontrollon fotot, "
                           "bashkon pjesët dhe e lidh me pemën.")
        else:
            person_panel(root(r))


def _save_sex(name, key):
    pm, d = _pema()
    if pm:
        pm.set_person(d, name, gjinia={"Mashkull": "m", "Femër": "f"}.get(ss.get(key), ""))
        pm.save(d)


def person_panel(r):
    """Karta e plotë e një personi: emri, përfshirja, fotot, gjej/pjesët, pema, harrimi."""
    paths = sorted(person_paths(r))
    mem = members(r)
    name = ss.names.get(r, "").strip()
    with st.container(border=True):
        c1, c2 = st.columns([1, 2.4], vertical_alignment="center")
        c = cover(r)
        t = ai.face_thumb(*c, size=200, square=True) if c else None
        if t:
            c1.image(t, width="stretch")
        key = gk(f"dbname_{r}")
        if key not in ss:
            ss[key] = name
        c2.text_input("Emri", key=key, placeholder="Kush është?", on_change=_on_name, args=(r, key),
                      help="I njëjti emër te dy persona i bashkon. Ruhet vetë dhe njihet në çdo skanim.")
        c2.caption(f"Personi {r + 1} · **{len(paths)} foto** · {len(mem)} pjesë"
                   + (" · :green[në kujtesë]" if name and name in ai.load_people() else ""))
        ikey = gk(f"inc_{r}")
        if ikey not in ss:
            ss[ikey] = r not in ss.excl
        c2.toggle("Përfshi në renditje", key=ikey, on_change=_on_inc, args=(r,),
                  help="Fotot e tij kopjohen te dosja e tij. Të hequrit shkojnë te 'Të tjerë'.")
        faces = face_strip(person_faces(r), 12)
        if faces:  # fytyrat (katrore, nga pjesë të ndryshme): shihet menjëherë nëse ka dikë tjetër brenda
            st.caption("Fytyrat e tij/saj · nëse sheh dikë tjetër: **Pjesët** → ✂️ ose **Fotot** → ❌")
            st.image(faces, width=52)
        cands = candidates(r)
        strong = sum(s >= AUTO_PICK for _, s in cands)
        b1, b2, b3 = st.columns(3)
        if b1.button(f"Fotot ({len(paths)})", icon=":material/photo_library:", key=gk(f"dball_{r}"),
                     width="stretch", help="Të gjitha fotot; ❌ heq ato që nuk janë ky person"):
            ss.dlg_n = 60
            show_all_dialog(r)
        if b2.button("Gjej" + (f" ({strong})" if strong else ""), icon=":material/person_search:",
                     key=gk(f"dbfind_{r}"), width="stretch", disabled=not cands,
                     type="primary" if strong else "secondary", help="Grupe të tjera që i ngjajnë: bashkoji"):
            ss.find_n = 25
            find_dialog(r)
        if b3.button(f"Pjesët ({len(mem)})", icon=":material/extension:", key=gk(f"dbparts_{r}"), width="stretch",
                     disabled=len(mem) < 2, help="Grupet që përbëjnë këtë person; ✂️ ndaj një pjesë të gabuar"):
            parts_dialog(r)
        for q, s in cands[:2]:  # sugjerimet më të forta, direkt këtu
            q1, q2, q3, q4 = st.columns([0.7, 5, 1, 1], vertical_alignment="center")
            fs = face_strip(person_faces(q), 1)
            if fs:
                q1.image(fs[0], width=40)
            q2.caption(f"Edhe ky? **{plabel(q)}** · {len(person_paths(q))} foto · {int(s * 100)}%")
            q3.button(":material/link:", key=gk(f"dby_{r}_{q}"), on_click=_merge_cb, args=(r, q), width="stretch",
                      help="Po, është i njëjti person: bashkoji")
            q4.button(":material/close:", key=gk(f"dbn_{r}_{q}"), on_click=_nope_cb, args=(r, q), width="stretch",
                      help="Jo, është tjetër person")
        if not name:
            st.caption(":material/info: Jepi një emër që ta lidhësh me pemën dhe ta njohë vetë herën tjetër.")
            return
        pm, d = _pema()
        if pm:
            st.divider()
            st.markdown("**:material/account_tree: Te pema**")
            une = d.get("une", "")
            kin = "ti" if name == une else (pm.kinship(d, une, name) if une else "")
            links = [pm.link_text(d, lk) for lk in d["links"] if name in (lk["a"], lk["b"])]
            gkey = gk(f"dbsex_{r}")
            p1, p2 = st.columns([3, 2], vertical_alignment="center")
            p1.radio("Gjinia", ["Mashkull", "Femër"], index={"m": 0, "f": 1}.get(pm.sex(d, name)), key=gkey,
                     horizontal=True, on_change=_save_sex, args=(name, gkey),
                     help="Nga gjinia varen emërtimet: babai/nëna, kushëriri/kushërira")
            if p2.button("Hape te Pema", icon=":material/open_in_new:", key=gk(f"dbtree_{r}"), width="stretch"):
                if name in d["persons"] or links:
                    ss.pema_qendra = name
                ss.pema_menu, ss.pema_menu_open = name, True
                st.switch_page(PAGES["pema"])
            if kin:
                st.caption(f"Për {une}: **{kin}**")
            art = pm._w("i", "e", "i/e", pm.sex(d, name))
            for w, others in pm.derived(d, name)[:8]:
                st.caption(f":material/link: **{w.split(' · ')[0]}** {art} " + ", ".join(others[:6])
                           + (f" +{len(others) - 6}" if len(others) > 6 else ""))
            if not links:
                st.caption("Ende pa lidhje te pema. **Hape te Pema** → *Lidh me dikë*.")
        if name in ai.load_people():
            with st.expander(":material/delete: Harroje emrin"):
                st.caption(f"Fshin **{name}** nga kujtesa e fytyrave: në skanimin tjetër nuk njihet më vetë. "
                           "Fotot nuk preken.")
                sure = st.checkbox(f"Po, harroje {name}", key=gk(f"dbsure_{r}"))
                st.button("Harroje", icon=":material/delete:", key=gk(f"dbforget_{r}"), disabled=not sure,
                          on_click=ai.forget_name, args=(name,))


VIEW_GRID, VIEW_DB, VIEW_CARDS = (":material/grid_view: Rrjeta", ":material/table_rows: Databaza",
                                  ":material/view_agenda: Me detaje")

# ---------- Videot ----------
V_OWN, V_WITH, V_NONE = "Dosje më vete: Videot → Viti → Muaji", "Bashkë me fotot", "Mos i kopjo"
V_MODE = {V_OWN: "own", V_WITH: "with", V_NONE: "none"}


def _vkey(p):
    import hashlib

    return f"vid_{hashlib.md5(p.encode()).hexdigest()[:12]}"


def _vid_toggle(p):
    off = ss.setdefault("video_off", set())
    (off.discard if ss.get(_vkey(p)) else off.add)(p)


def _vid_all(paths, on):
    off = ss.setdefault("video_off", set())
    off.difference_update(paths) if on else off.update(paths)
    for p in paths:
        ss[_vkey(p)] = on


def _vid_more():
    ss.vid_n = ss.get("vid_n", 30) + 30


def _vyear(r):
    return (r.get("data") or "")[:4] or "Pa Datë"


def _dur(s):
    if not s:
        return ""
    s = int(round(s))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


@st.dialog("🎬 Zgjidh videot", width="large", on_dismiss="rerun")
def videos_dialog(vids):
    off = ss.setdefault("video_off", set())
    years = sorted({_vyear(r) for r in vids}, reverse=True)
    f1, f2, f3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    y = f1.selectbox("Viti", ["Të gjitha vitet"] + years, key="vid_year")
    sel = sorted((r for r in vids if y.startswith("Të gjitha") or _vyear(r) == y),
                 key=lambda r: r.get("data") or "", reverse=True)
    paths = [r["shtegu"] for r in sel]
    f2.button("✔ Të gjitha", on_click=_vid_all, args=(paths, True), width="stretch")
    f3.button("✖ Asnjë", on_click=_vid_all, args=(paths, False), width="stretch")
    n_on = sum(r["shtegu"] not in off for r in vids)
    st.caption(f"**{n_on} nga {len(vids)} video** do të kopjohen. Hiq ✔ nga ato që nuk i do; "
               "**▶** e hap videon me programin tënd.")
    n = min(ss.get("vid_n", 30), len(sel))
    from concurrent.futures import ThreadPoolExecutor

    with st.spinner("Po përgatis pamjet e videove..."), ThreadPoolExecutor(max_workers=6) as ex:
        infos = list(ex.map(ai.video_thumb, paths[:n])) if ai else [(None, None)] * n
    cols = st.columns(3)
    for i, (r, (t, d)) in enumerate(zip(sel[:n], infos)):
        p = r["shtegu"]
        with cols[i % 3].container(border=True):
            if t:
                st.image(t, width="stretch")
            else:
                st.caption("🎬 (pa pamje)")
            kb = int(r.get("madhesia_kb") or 0)
            st.caption(f"**{os.path.basename(p)}**  \n{(r.get('data') or '')[:10] or 'Pa datë'}"
                       + (f" · ⏱ {_dur(d)}" if d else "") + f" · {core.human_size(kb * 1024)}")
            k = _vkey(p)
            if k not in ss:
                ss[k] = p not in off
            c1, c2 = st.columns([3, 1], vertical_alignment="center")
            c1.checkbox("✔ Kopjoje", key=k, on_change=_vid_toggle, args=(p,))
            c2.button("▶", key=f"play_{k}", on_click=open_file, args=(p,), help="Hape videon")
    b1, b2 = st.columns(2)
    if n < len(sel):
        b1.button(f"⬇ Shfaq edhe 30 ({n} nga {len(sel)})", on_click=_vid_more, width="stretch")
    if b2.button("✔ Mbaro", type="primary", width="stretch", key="vid_done"):
        st.rerun()


# ---------------- gjendja e përbashkët e faqeve (Skano · Personat · Rendit) ----------------
PAGES = {"skano": "faqet/skano.py", "personat": "faqet/personat.py", "databaza": "faqet/databaza.py",
         "rendit": "faqet/rendit.py",
         "pema": "faqet/pema_lidhjet.py"}


def init_state():
    ss.setdefault("sources", str(Path.home() / "Pictures"))
    ss.setdefault("out", str(Path.home() / "Fotot e Renditura"))
    ss.setdefault("records", None)
    ss.setdefault("groups", None)


def scan_context():
    """(dosjet për skanim, dosja e daljes, dosjet që nuk ekzistojnë)."""
    sources = [s.strip() for s in (ss.get("sources") or "").splitlines() if s.strip()]
    out_dir = (ss.get("out") or "").strip()
    return sources, out_dir, [s for s in sources if not os.path.isdir(s)]


def header(title, subtitle=None, icon=None):
    """Titull kompakt i faqes (h3) me një rresht shpjegues të vogël."""
    st.markdown(f"### {icon + ' ' if icon else ''}{title}")
    if subtitle:
        st.caption(subtitle)


def next_step(label, page, icon=":material/arrow_forward:", primary=True):
    """Butoni 'Vazhdo' poshtë djathtas, që çon te faqja tjetër."""
    _, c = st.columns([3, 1])
    if c.button(label, icon=icon, type="primary" if primary else "secondary", width="stretch",
                key=f"next_{page}"):
        st.switch_page(PAGES[page])


def open_scan(sid):
    """Rihap një skanim nga historiku: pa kaluar diskun, pa lexuar fotot, pa rigrupuar fytyrat."""
    try:
        info, recs_, groups_, rep = historiku.load(sid)
    except Exception as e:
        ss.hist_err = f"Skanimi nuk u hap: {e}"
        return
    if groups_ and ai is not None:
        try:
            ai.rename_groups(groups_)  # emrat e dhënë pas atij skanimi
        except Exception:
            pass
    ss.records, ss.groups, ss.scan_report = recs_, groups_, rep
    ss.removed, ss.people_for, ss.scan_id, ss.scan_from_hist = {}, None, sid, info
    ss.sources = "\n".join(info.get("dosjet", []))


def delete_scan(sid):
    historiku.delete(sid)
    if ss.get("scan_id") == sid:
        ss.scan_id = None


def prepare_people():
    """Gjendja e personave për grupet e tanishme (emrat, bashkimet, korrigjimet). Kthen personat,
    më të shpeshtët së pari, dhe përditëson indeksin e fotove për 🌳 Pemën."""
    groups = ss.get("groups")
    if not groups:
        return []
    if ss.get("people_for") != id(groups):
        init_people(groups)
    else:  # sesion i nisur me version tjetër: shto gjendjen e re pa humbur emrat
        ensure_people_state()
    persons = sorted({root(g["id"]) for g in groups}, key=lambda r: -len(person_paths(r)))
    save_person_index(persons)
    return persons


def shown_persons(persons):
    """Personat që shfaqen dhe përfshihen: aq sa zgjodhe (ss.show_n, si parazgjedhje 30) + gjithmonë ata me emër."""
    n = min(len(persons), ss.get("show_n") or 30)
    shown = persons[:n] + [r for r in persons[n:] if ss.names.get(r, "").strip()]
    ss.shown_set = set(shown)  # sugjerimet për fytyrat e hequra: vetëm te këta
    pos = {r: i for i, r in enumerate(shown)}
    ss.shown_list = sorted(shown, key=lambda r: (not pname(r), pname(r).casefold(), pos[r]))
    return shown


def people_map(shown):
    """{foto: [(emri, sipërfaqja e fytyrës)]} për renditjen sipas personave."""
    people = {}
    for r in shown:
        if r in ss.excl:
            continue
        n = plabel(r)
        for g in members(r):
            rem = removed(g)
            for rr, f in ss.groups[g]["faces"]:
                if rr["path"] not in rem:
                    people.setdefault(rr["path"], []).append((n, f["box"][2] * f["box"][3]))
        for g, p in moved_in(r):  # fytyra të dhëna me ➡ nga 🧺
            f = face_of(g, p)[1]
            people.setdefault(p, []).append((n, f["box"][2] * f["box"][3]))
    return people


def current_rows():
    """(rreshtat, burimi): nga skanimi (me personat) ose nga katalogu i dosjes së daljes (pa skanuar)."""
    recs = ss.get("records")
    if recs:
        persons = prepare_people() if ss.get("groups") else []
        people = people_map(shown_persons(persons)) if persons else {}
        return core.build_rows(recs, people, CAT_LABELS), "skanim"
    _, out_dir, _ = scan_context()
    catalog = core.load_catalog(out_dir) if out_dir else None
    return (catalog, "katalog") if catalog else (None, None)


def no_scan_yet(what):
    """Gjendja bosh e faqeve Personat/Rendit: çfarë mungon dhe një veprim për ta zgjidhur."""
    hist = historiku.items()
    with st.container(border=True):
        st.markdown(f"**Ende pa skanim.** {what}")
        c1, c2, _ = st.columns([2, 2, 3])
        if hist:
            c1.button(f"Hap skanimin e fundit ({hist[0]['koha']})", icon=":material/bolt:", type="primary",
                      on_click=open_scan, args=(hist[0]["id"],), width="stretch", key="empty_open_last")
        if c2.button("Shko te Skano", icon=":material/search:", width="stretch", key="empty_to_scan"):
            st.switch_page(PAGES["skano"])


def person_cards(shown):
    """Pamja 'Me detaje': një kartë për person, me fytyrat, butonat dhe sugjerimet për bashkim."""
    for r in shown:
        paths = person_paths(r)
        mem = members(r)
        with st.container(border=True):
            h1, h2, h3 = st.columns([3, 2, 1], vertical_alignment="bottom")
            key = gk(f"name_{r}")
            if key not in ss:
                ss[key] = ss.names.get(r, "")
            h1.text_input(f"Personi {r + 1}", key=key, placeholder="Shkruaj emrin...", on_change=_on_name, args=(r,))
            h2.caption(f":material/photo_library: {len(paths)} foto"
                       + (f" · :material/extension: nga {len(mem)} grupe" if len(mem) > 1 else ""))
            ikey = gk(f"inc_{r}")
            if ikey not in ss:
                ss[ikey] = r not in ss.excl
            h3.checkbox("Përfshi", key=ikey, on_change=_on_inc, args=(r,))
            strip = face_strip(person_faces(r), 10)
            if strip:
                st.image(strip, width=64)
            cands = candidates(r)
            strong = sum(s >= AUTO_PICK for _, s in cands)
            b1, b2, b3, _ = st.columns([2, 2, 2, 3])
            if b1.button(f"Të gjitha ({len(paths)})", icon=":material/visibility:", key=gk(f"all_{r}"),
                         width="stretch"):
                ss.dlg_n = 60
                show_all_dialog(r)
            if b2.button("Gjej të tjera" + (f" ({strong})" if strong else ""), icon=":material/person_search:",
                         key=gk(f"find_{r}"), width="stretch", disabled=not cands,
                         type="primary" if strong else "secondary",
                         help=(f"{strong} grupe ngjajnë mbi {int(AUTO_PICK * 100)}%: me shumë gjasë po ky person"
                               if strong else f"{len(cands)} grupe ngjajnë pak" if cands
                               else "Asnjë grup tjetër nuk i ngjan")):
                ss.find_n = 25
                find_dialog(r)
            if len(mem) > 1 and b3.button(f"Pjesët ({len(mem)})", icon=":material/extension:",
                                          key=gk(f"parts_{r}"), width="stretch"):
                parts_dialog(r)
            for q, s in cands[:2]:
                c1, c2, c3, c4 = st.columns([3, 4, 1, 1], vertical_alignment="center")
                c1.image(face_strip(person_faces(q), 4), width=44)
                c2.caption(f"Edhe ky? **{plabel(q)}** · {len(person_paths(q))} foto · {int(s * 100)}%")
                c3.button(":material/link:", key=gk(f"y_{r}_{q}"), on_click=_merge_cb, args=(r, q), width="stretch",
                          help="Po, është i njëjti person: bashkoji")
                c4.button(":material/close:", key=gk(f"n_{r}_{q}"), on_click=_nope_cb, args=(r, q),
                          width="stretch", help="Jo, është tjetër person: mos e sugjero më")
