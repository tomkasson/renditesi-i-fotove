"""Pema e lidhjeve: familja (pa kufi brezash) dhe lidhjet e tjera (shoqëria, shkolla, puna...).

Pa ndërfaqe, që të testohet lehtë. Të dhënat ruhen te cache/pema.json.
Familja ruhet vetëm me 3 lidhje bazë: 'prind' (a është prind i b), 'partner' dhe 'vella' (vëlla/motër).
Gjyshërit, xhaxhallarët, kushërinjtë, vjehrri, kunata... dalin vetë nga zinxhiri.
"""
import html
import json
import os
import re
from collections import defaultdict, deque
import time as _time

_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

HERE = os.path.dirname(os.path.abspath(__file__))
import paths  # noqa: E402

FILE = os.environ.get("PEMA_FILE") or paths.data("pema.json")  # PEMA_FILE: për prova
# {emri: {"fytyra": [shtegu, [x, y, w, h]] ose null, "fotot": [[shtegu, "viti"], ...]}}; e shkruan Renditësi
INDEX = os.environ.get("PEMA_INDEX") or paths.data("fotot_e_personave.json")
SUGJERO_MIN = 5  # sa foto bashkë duhen që AI-ja të sugjerojë një lidhje

FAMILY = ("prind", "partner", "vella")
OTHER = {"shoqeri": ":material/handshake: Shoqëria", "shkolla": ":material/school: Shkolla", "puna": ":material/work: Puna",
         "tjeter": ":material/more_horiz: Të tjera"}
VIRTUAL = "§"  # prind i padukshëm për vëllezërit/motrat pa prindër të regjistruar

# "[X] është [zgjedhja] i/e [Y]": (lloji, gjinia e X-it, ndërro (Y prind i X), roli)
CHOICES = {
    "Babai": ("prind", "m", False, ""),
    "Nëna": ("prind", "f", False, ""),
    "Djali": ("prind", "m", True, ""),
    "Vajza": ("prind", "f", True, ""),
    "Vëllai": ("vella", "m", False, ""),
    "Motra": ("vella", "f", False, ""),
    "Gjyshi (nga babai)": ("gjysh", "m", False, ""),
    "Gjyshja (nga babai)": ("gjysh", "f", False, ""),
    "Gjyshi (nga nëna)": ("gjysh", "m", False, ""),
    "Gjyshja (nga nëna)": ("gjysh", "f", False, ""),
    "Xhaxhai (vëllai i babait)": ("xhaxha", "m", False, ""),
    "Halla (motra e babait)": ("xhaxha", "f", False, ""),
    "Daja (vëllai i nënës)": ("xhaxha", "m", False, ""),
    "Tezja (motra e nënës)": ("xhaxha", "f", False, ""),
    "Kushëriri": ("kusheri", "m", False, ""),
    "Kushërira": ("kusheri", "f", False, ""),
    "Xhaxheshja (gruaja e xhaxhait)": ("xhaxha_partner", "f", False, ""),
    "Dajesha (gruaja e dajës)": ("xhaxha_partner", "f", False, ""),
    "Burri i hallës": ("xhaxha_partner", "m", False, ""),
    "Burri i tezes": ("xhaxha_partner", "m", False, ""),
    "Bashkëshorti / Partneri": ("partner", "m", False, ""),
    "Bashkëshortja / Partnerja": ("partner", "f", False, ""),
    "Shok": ("shoqeri", "m", False, ""),
    "Shoqe": ("shoqeri", "f", False, ""),
    "Fqinj/e": ("shoqeri", "", False, "fqinj"),
    "Shok/shoqe shkolle": ("shkolla", "", False, ""),
    "Mësues/e": ("shkolla", "", False, "mësues"),
    "Koleg/e pune": ("puna", "", False, ""),  # roli sipas gjinisë: koleg / kolege
    "Shef/e": ("puna", "", False, "shef"),
    "Tjetër…": ("tjeter", "", False, ""),
}
# shpjegim i shkurtër te lista e lidhjeve (hover/etiketë)
HINT = {"Babai": "prindi", "Nëna": "prindi", "Djali": "fëmija", "Vajza": "fëmija",
        "Vëllai": "të njëjtët prindër", "Motra": "të njëjtët prindër",
        "Gjyshi (nga babai)": "babai i babait", "Gjyshja (nga babai)": "nëna e babait",
        "Gjyshi (nga nëna)": "babai i nënës", "Gjyshja (nga nëna)": "nëna e nënës",
        "Kushëriri": "djali i xhaxhait/hallës/dajës/tezes", "Kushërira": "vajza e xhaxhait/hallës/dajës/tezes",
        "Xhaxheshja (gruaja e xhaxhait)": "edhe kur xhaxhai s'ka foto", "Dajesha (gruaja e dajës)": "edhe pa foto të dajës",
        "Fqinj/e": "shoqëria", "Mësues/e": "shkolla", "Shef/e": "puna", "Tjetër…": "kumbarë, trajner, mjek..."}
# lidhjet e përbëra: nga cila anë (gjinia e prindit të Y-it nëpër të cilin kalon lidhja)
SIDE = {"Gjyshi (nga babai)": "m", "Gjyshja (nga babai)": "m", "Gjyshi (nga nëna)": "f", "Gjyshja (nga nëna)": "f",
        "Xhaxhai (vëllai i babait)": "m", "Halla (motra e babait)": "m", "Daja (vëllai i nënës)": "f",
        "Tezja (motra e nënës)": "f"}
# prindi i kushëririt, kur nuk është ende në pemë: (gjinia e tij, ana: m = vëlla/motër e babait, f = e nënës)
UNCLE = {"Xhaxhai": ("m", "m"), "Halla": ("f", "m"), "Daja": ("m", "f"), "Tezja": ("f", "f")}
# bashkëshorti/ja i/e xhaxhait...: kush është 'via' (nëse duhet shtuar, edhe pa foto)
SPOUSE_OF = {"Xhaxheshja (gruaja e xhaxhait)": "Xhaxhai", "Dajesha (gruaja e dajës)": "Daja",
             "Burri i hallës": "Halla", "Burri i tezes": "Tezja"}
DEFAULT_ROLE = {"shoqeri": ("shok", "shoqe", "shok/shoqe"), "shkolla": ("shok shkolle", "shoqe shkolle", "shok/e shkolle"),
                "puna": ("koleg", "kolege", "koleg/e"), "tjeter": ("i njohur", "e njohur", "i/e njohur")}

# madhësitë e vizatimit (piksel)
W, H = 120, 150  # karta
PG = 26  # hapësira mes partnerëve
GAP = 34  # hapësira mes blloqeve në një rresht
FAM_GAP = 56  # hapësirë shtesë midis kartave me prindër të ndryshëm (familjet nuk duken si një grup)
VG = 84  # hapësira mes brezave
M = 24  # buza
FACE_R = 34  # rrezja e rrethit të fytyrës
FACE_CY = 46  # qendra e rrethit, nga maja e kartës


# ---------------- të dhënat ----------------
def empty():
    return {"une": "", "persons": {}, "links": [], "jo_sugjero": []}


def load(path=None):
    try:
        with open(path or FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    out = empty()
    out.update({k: v for k, v in data.items() if k in out})
    return out


def save(data, path=None):
    """Shkrim i sigurt: së pari skedar i përkohshëm, pastaj zëvendësim; versioni i mëparshëm mbetet si kopje."""
    path = path or FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    if os.path.exists(path):
        try:
            os.replace(path, path.replace(".json", "_kopje.json"))
        except OSError:
            pass
    os.replace(tmp, path)


def save_index(entries, path=None):
    """Shton/zëvendëson emrat te indeksi i fotove. Emrat që nuk janë në 'entries' mbeten (p.sh. nga një
    skanim i dosjeve të tjera). Shkrim i sigurt si save()."""
    path = path or INDEX
    old = load_index(path, raw=True)
    # një emër i vjetër që s'është në skanim, por ka fytyrën e njërit prej të rinjve ose shumicën e fotove të tij,
    # është i njëjti person me emër tjetër (u riemërtua): mos e mbaj, përndryshe del dy herë te pema
    faces = {json.dumps(e.get("fytyra")) for e in entries.values() if e.get("fytyra")}
    photos = [{q for q, _ in e.get("fotot", [])} for e in entries.values()]
    for n in [n for n in old if n not in entries]:
        mine = {q for q, _ in old[n].get("fotot", [])}
        if json.dumps(old[n].get("fytyra")) in faces or (
                len(mine) >= 5 and any(len(mine & ph) > 0.8 * len(mine) for ph in photos)):
            del old[n]
    old.update(entries)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_index(path=None, raw=False):
    """{emri: {"fytyra": (shtegu, kutia) ose None, "fotot": {shtegu: viti}}}."""
    try:
        with open(path or INDEX, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if raw:
        return data
    out = {}
    for n, v in data.items():
        fy = v.get("fytyra")
        out[n] = {"fytyra": (fy[0], tuple(fy[1])) if fy else None,
                  "fotot": {p: (y or "") for p, y in v.get("fotot", [])}}
    return out


def photos(index, name):
    return (index.get(name) or {}).get("fotot") or {}


def together(index, names):
    """Fotot ku janë të gjithë 'names' bashkë: [shtegu], më të rejat së pari."""
    sets = [photos(index, n) for n in names]
    if not sets or not all(sets):
        return []
    common = set(sets[0]).intersection(*sets[1:])
    return sorted(common, key=lambda p: (sets[0][p] or "0000", p), reverse=True)


def span(index, name, paths):
    ys = sorted({photos(index, name).get(p) for p in paths} - {"", None})
    return "" if not ys else ys[0] if ys[0] == ys[-1] else f"{ys[0]}–{ys[-1]}"


def companions(index, name, limit=12):
    """Me kë del 'name' më shpesh në foto: [(tjetri, numri)]."""
    mine = set(photos(index, name))
    out = [(o, len(mine & set(v["fotot"]))) for o, v in index.items() if o != name]
    return sorted([x for x in out if x[1]], key=lambda x: (-x[1], x[0].casefold()))[:limit]


def linked(data, a, b):
    """Lidhjet e ruajtura mes a dhe b (familja nga zinxhiri nuk llogaritet këtu)."""
    return [lk for lk in data["links"] if {lk["a"], lk["b"]} == {a, b}]


def suggestions(data, index, min_n=SUGJERO_MIN):
    """Çiftet që dalin shpesh bashkë në foto, pa lidhje dhe pa 'jo': [(a, b, numri, vitet)], 'unë' në krye."""
    une = data.get("une", "")
    known = {frozenset((lk["a"], lk["b"])) for lk in data["links"]}
    no = {frozenset(p) for p in data.get("jo_sugjero", [])}
    g = graph(data)
    fam = family_component(data, une, g) if une else set()
    names = sorted(index, key=str.casefold)
    sets = {n: set(index[n]["fotot"]) for n in names}
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pair = frozenset((a, b))
            if pair in known or pair in no or (a in fam and b in fam):
                continue
            common = sets[a] & sets[b]
            if len(common) >= min_n:
                if b == une:
                    a, b = b, a
                out.append((a, b, len(common), span(index, a, common)))
    return sorted(out, key=lambda s: (une not in s[:2], -s[2], s[0].casefold(), s[1].casefold()))


def face_names():
    """Emrat që Renditësi i njeh nga fytyrat (cache/personat.json)."""
    try:
        import ai

        with open(ai.PEOPLE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def all_names(data, faces=()):
    names = set(faces) | set(data["persons"])
    for lk in data["links"]:
        names |= {lk["a"], lk["b"]}
    return sorted(names, key=str.casefold)


def canon(name, names):
    """Emri ashtu si ekziston tashmë (pa dallim shkronjash të mëdha/vogla), ose i pastruar."""
    name = " ".join((name or "").split())
    name = re.sub(r"\s·\s\d+ foto me .*$", "", name)  # etiketa e listës së vjetër (p.sh. "Ben · 5 foto me Ana")
    for n in names:
        if n.casefold() == name.casefold():
            return n
    return name


def person(data, name):
    return data["persons"].get(name) or {}


def sex(data, name):
    return person(data, name).get("gjinia", "")


def is_contact(data, name, faces=()):
    k = person(data, name).get("kontakt")
    return bool(k) if k is not None else name in faces


def set_person(data, name, **fields):
    rec = data["persons"].setdefault(name, {})
    rec.update({k: v for k, v in fields.items() if v is not None})
    return rec


def rename(data, old, new):
    """Riemërton (ose bashkon me një person ekzistues, p.sh. 'Gjyshi' → 'Arben' që ka foto)."""
    new = " ".join((new or "").split())
    if not new:
        raise ValueError("Emri i ri është bosh.")
    if new == old:
        return
    rec = data["persons"].pop(old, None)
    if rec:
        tgt = data["persons"].setdefault(new, {})
        for k, v in rec.items():
            if tgt.get(k) in (None, ""):
                tgt[k] = v
    links, seen = [], set()
    for lk in data["links"]:
        lk = dict(lk, a=new if lk["a"] == old else lk["a"], b=new if lk["b"] == old else lk["b"])
        if lk["a"] == lk["b"] or _key(lk) in seen:
            continue
        seen.add(_key(lk))
        links.append(lk)
    data["links"] = links
    if data["une"] == old:
        data["une"] = new
    data["jo_sugjero"] = [[new if x == old else x for x in p] for p in data["jo_sugjero"]]


def delete_person(data, name):
    data["persons"].pop(name, None)
    data["links"] = [lk for lk in data["links"] if name not in (lk["a"], lk["b"])]
    if data["une"] == name:
        data["une"] = ""


def _key(lk):
    """Çelësi për dyfishet: 'prind' ka drejtim, të tjerat jo."""
    if lk["lloji"] == "prind":
        return ("prind", lk["a"], lk["b"])
    return (lk["lloji"],) + tuple(sorted((lk["a"], lk["b"])))


def add_link(data, a, b, lloji, roli="", ku=""):
    a, b = " ".join((a or "").split()), " ".join((b or "").split())
    if not a or not b:
        raise ValueError("Zgjidh të dy personat.")
    if a == b:
        raise ValueError("Një person nuk lidhet dot me veten.")
    if lloji not in FAMILY and lloji not in OTHER:
        raise ValueError(f"Lloj i panjohur lidhjeje: {lloji}")
    lk = {"a": a, "b": b, "lloji": lloji}
    if lloji in OTHER:
        if roli.strip():
            lk["roli"] = roli.strip()
        if ku.strip():
            lk["ku"] = ku.strip()
    if any(_key(x) == _key(lk) for x in data["links"]):
        raise ValueError("Kjo lidhje ekziston tashmë.")
    if lloji == "prind":
        par = defaultdict(set)
        for x in data["links"]:
            if x["lloji"] == "prind":
                par[x["b"]].add(x["a"])
        if len(par[b]) >= 2:
            raise ValueError(f"{b} ka tashmë 2 prindër ({', '.join(sorted(par[b]))}).")
        if a in _ancestors_of(par, b) or b in _ancestors_of(par, a) or a == b:
            raise ValueError(f"{b} është tashmë paraardhës i {a}: kjo do të bënte një rreth.")
    if lloji in ("prind", "vella", "partner"):  # mospërputhje me lidhjet që ekzistojnë (edhe të nënkuptuarat)
        gp, gk_, gpart = graph(data)
        if lloji != "prind" and (a in _ancestors_of(gp, b) or b in _ancestors_of(gp, a)):
            what = "vëllezër/motra" if lloji == "vella" else "çift"
            raise ValueError(f"{a} dhe {b} janë tashmë prind e fëmijë (ose gjysh e nip) te pema: nuk mund të jenë "
                             f"edhe {what}. Ndoshta zgjodhe personin e gabuar?")
        sibs = {s for p in gp.get(a, ()) for s in gk_.get(p, ())} - {a}
        if lloji == "prind" and b in sibs:
            raise ValueError(f"{a} dhe {b} janë vëllezër/motra te pema: nuk mund të jenë edhe prind e fëmijë.")
    data["links"].append(lk)
    return lk


def _ancestors_of(par, x):
    out, q = set(), [x]
    while q:
        for p in par.get(q.pop(), ()):
            if p not in out:
                out.add(p)
                q.append(p)
    return out


def parent_of(data, y, side):
    """Babai (side='m') ose nëna (side='f') e Y-it, nga lidhjet (edhe të nënkuptuarat), ose None."""
    par, _, _ = graph(data)
    for p in sorted(par.get(y, ())):
        if not p.startswith(VIRTUAL) and sex(data, p) == side:
            return p
    return None


def uncles_aunts(data, y):
    """Vëllezërit/motrat e prindërve të Y-it: [(emri, 'xhaxhai'/'halla'/'daja'/'tezja' ose më i përgjithshëm)]."""
    par, kids, _ = graph(data)
    out = []
    for p in sorted(par.get(y, ())):
        if p.startswith(VIRTUAL):
            continue
        for gp in par.get(p, ()):
            for s in sorted(kids.get(gp, ())):
                if s != p and s not in [o for o, _ in out]:
                    out.append((s, kinship(data, y, s) or "i afërm"))
    return out


def in_tree(data):
    """Personat që janë tashmë te pema (me të dhëna ose me të paktën një lidhje)."""
    return set(data["persons"]) | {n for lk in data["links"] for n in (lk["a"], lk["b"])}


def add_relation(data, x, choice, y, roli="", ku="", names=(), via=None, via_kind=None):
    """Nga fjalia "[X] është [zgjedhja] i/e [Y]" te lidhja e ruajtur. Kthen lidhjen kryesore.

    Lidhjet e përbëra ruhen me 3 lidhjet bazë: gjyshi = prind i babait/nënës së Y-it; xhaxhai/halla/daja/tezja =
    vëlla/motër e babait/nënës; kushëriri = fëmijë i 'via' (xhaxhait...). Kur 'via' është i ri, via_kind
    ('Xhaxhai'/'Halla'/'Daja'/'Tezja') tregon gjininë e tij dhe anën, dhe ai shtohet në të njëjtin hap."""
    lloji, g, swap, role0 = CHOICES[choice]
    names = list(names) + all_names(data)
    x, y = canon(x, names), canon(y, names)
    if x == y:
        raise ValueError("Një person nuk lidhet dot me veten.")
    if lloji in ("gjysh", "xhaxha"):
        side = SIDE[choice]
        p = parent_of(data, y, side)
        if not p:
            raise ValueError(f"Shto më parë {'babain' if side == 'm' else 'nënën'} e {y} (zgjidh 'Babai'/'Nëna'), "
                             "pastaj këtë lidhje.")
        lk = add_link(data, x, p, "prind" if lloji == "gjysh" else "vella")
    elif lloji in ("kusheri", "xhaxha_partner"):
        via = canon(via, names) if via else ""
        if lloji == "xhaxha_partner":
            via_kind = SPOUSE_OF[choice]
        if not via:
            raise ValueError("Zgjidh xhaxhain, hallën, dajën ose tezen (ose shkruaj emrin, edhe pa foto).")
        known = [u for u, _ in uncles_aunts(data, y)]
        if via not in known and via not in in_tree(data):  # i ri: shtohet si vëlla/motër e prindit të Y-it
            if via_kind not in UNCLE:
                raise ValueError(f"{via} nuk është ende në pemë: zgjidh nëse është xhaxhai, halla, daja apo tezja.")
            vg, side = UNCLE[via_kind]
            p = parent_of(data, y, side)
            if not p:
                raise ValueError(f"Shto më parë {'babain' if side == 'm' else 'nënën'} e {y}, pastaj këtë lidhje.")
            add_link(data, via, p, "vella")
            data["persons"].setdefault(via, {})
            if not sex(data, via):
                set_person(data, via, gjinia=vg)
        lk = add_link(data, via, x, "prind" if lloji == "kusheri" else "partner")
    else:
        lk = add_link(data, y if swap else x, x if swap else y, lloji, roli or role0, ku)
    for n in (x, y):  # personat e rinj (pa foto) hyjnë te lista
        data["persons"].setdefault(n, {})
    if g and not sex(data, x):
        set_person(data, x, gjinia=g)
    return lk


def delete_link(data, lk):
    data["links"] = [x for x in data["links"] if _key(x) != _key(lk)]


# ---------------- familja si graf ----------------
def graph(data):
    """(prindërit, fëmijët, partnerët). Vëllezërit/motrat pa prindër të njohur marrin prindërit e njëri-tjetrit,
    ose një prind të padukshëm (VIRTUAL...), që të vizatohen bashkë."""
    par, kids, partners = defaultdict(set), defaultdict(set), defaultdict(set)
    sib = {}

    def find(v):
        while sib[v] != v:
            sib[v] = sib[sib[v]]
            v = sib[v]
        return v

    for lk in data["links"]:
        a, b, t = lk["a"], lk["b"], lk["lloji"]
        if t == "prind":
            par[b].add(a)
            kids[a].add(b)
        elif t == "partner":
            partners[a].add(b)
            partners[b].add(a)
        elif t == "vella":
            sib.setdefault(a, a)
            sib.setdefault(b, b)
            sib[find(a)] = find(b)
    # të nënkuptuarat (nuk ruhen): dy prindërit e të njëjtit fëmijë = çift; fëmija me një prind të njohur
    # merr edhe partnerin e vetëm të atij prindi (zakonisht futet vetëm njëri, p.sh. "Gjyshi babai i Xhaxhit")
    for c in list(par):
        ps = sorted(par[c])
        if len(ps) == 2:
            partners[ps[0]].add(ps[1])
            partners[ps[1]].add(ps[0])
    for c in list(par):
        if len(par[c]) == 1:
            (p,) = par[c]
            if len(partners[p]) == 1:
                (q,) = partners[p]
                if q != c and c not in _ancestors_of(par, q):
                    par[c].add(q)
                    kids[q].add(c)
    groups = defaultdict(set)
    for v in list(sib):
        groups[find(v)].add(v)
    for i, mem in enumerate(sorted(groups.values(), key=lambda s: sorted(s))):
        known = set().union(*(par[m] for m in mem))
        shared = known if 0 < len(known) <= 2 else {f"{VIRTUAL}{i}"}
        for m in sorted(mem):
            if not par[m]:
                for p in shared:
                    par[m].add(p)
                    kids[p].add(m)
    return par, kids, partners


def _neighbors(par, kids, partners, x):
    return ([(p, -1) for p in sorted(par.get(x, ()))] + [(s, 0) for s in sorted(partners.get(x, ()))]
            + [(c, 1) for c in sorted(kids.get(x, ()))])


def _up(par, x):
    """{paraardhësi: (sa breza lart, prindi i parë në rrugë)}, përfshirë vetveten (0, None)."""
    out, q = {x: (0, None)}, deque([x])
    while q:
        y = q.popleft()
        d, first = out[y]
        for p in sorted(par.get(y, ())):
            if p not in out:
                out[p] = (d + 1, first if first is not None else p)
                q.append(p)
    return out


def blood(par, a, b):
    """(breza lart nga a, breza poshtë te b, prindi i a-së në atë rrugë) nëpërmjet paraardhësit të përbashkët."""
    ua, ub = _up(par, a), _up(par, b)
    best = None
    for anc in ua.keys() & ub.keys():
        u, first = ua[anc]
        d = ub[anc][0]
        if best is None or u + d < best[0] + best[1]:
            best = (u, d, first)
    return best


def _w(m, f, n, g):
    return m if g == "m" else f if g == "f" else n


def _ster(k, base):
    """k=3 → stërgjyshi, k=4 → stër-stërgjyshi..."""
    return "stër-" * (k - 3) + "stër" + base


def _blood_word(u, d, g, side):
    if d == 0:
        if u == 1:
            return _w("babai", "nëna", "prindi", g)
        base = _w("gjyshi", "gjyshja", "gjyshi/gjyshja", g)
        return base if u == 2 else _ster(u, base)
    if u == 0:
        if d == 1:
            return _w("djali", "vajza", "fëmija", g)
        base = _w("nipi", "mbesa", "nipi/mbesa", g)
        return base if d == 2 else _ster(d, base)
    if u == 1:
        if d == 1:
            return _w("vëllai", "motra", "vëlla/motër", g)
        base = _w("nipi", "mbesa", "nipi/mbesa", g)  # fëmija i vëllait/motrës
        return base if d == 2 else _ster(d, base)
    if u == 2 and d == 1:
        if side == "m":
            return _w("xhaxhai", "halla", "xhaxhai/halla", g)
        if side == "f":
            return _w("daja", "tezja", "daja/tezja", g)
        return _w("xhaxhai/daja", "halla/tezja", "xhaxha/dajë/hallë/teze", g)
    if d == 1:
        return _w("vëllai", "motra", "vëlla/motër", g) + " " + _w("i", "e", "i/e", g) + " " + (
            "gjyshërve" if u == 3 else "stërgjyshërve" if u == 4 else "të parëve")
    kus = _w("kushëriri", "kushërira", "kushëri/e", g)
    return kus if u == d == 2 else kus + " " + _w("i", "e", "i/e", g) + " largët"


def kinship(data, frm, to, g=None):
    """Si e ka 'to' personi 'frm': 'gjyshi', 'kushërira', 'vjehrra', 'kunati'... ('' nëse nuk dihet)."""
    if frm == to:
        return ""
    par, kids, partners = g or graph(data)
    sx = sex(data, to)
    b = blood(par, frm, to)
    if b:
        u, d, first = b
        side = sex(data, first) if first and not first.startswith(VIRTUAL) else ""
        return _blood_word(u, d, sx, side)
    if to in partners.get(frm, ()):
        return _w("bashkëshorti", "bashkëshortja", "partneri/partnerja", sx)
    for p in sorted(partners.get(frm, ())):  # familja e partnerit
        bp = blood(par, p, to)
        if bp:
            if bp[:2] == (1, 0):
                return _w("vjehrri", "vjehrra", "vjehrri/vjehrra", sx)
            if bp[:2] == (1, 1):
                return _w("kunati", "kunata", "kunati/kunata", sx)
            side = sex(data, bp[2]) if bp[2] and not bp[2].startswith(VIRTUAL) else ''  # ana e partneres (babai/nëna)
            return f"{_blood_word(bp[0], bp[1], sx, side)} · nga {p}"
    w = _spouse_word(data, frm, to, par, partners)
    if w:
        return w
    for p in sorted(partners.get(frm, ())):  # bashkëshorti/ja i/e një të afërmi të partneres (xhaxheshja · nga Ana)
        w = _spouse_word(data, p, to, par, partners)
        if w and to != frm:
            return f"{w} · nga {p}"
    sibs = {s for p in par.get(frm, ()) for s in kids.get(p, ())} - {frm}
    if any(to in partners.get(s, ()) for s in sibs):
        return _w("kunati", "kunata", "kunati/kunata", sx)
    for c in sorted(kids.get(frm, ())):
        if to in partners.get(c, ()):
            return _w("dhëndri", "nusja", "dhëndri/nusja", sx)
        if any(to in par.get(pc, ()) for pc in partners.get(c, ())):
            return _w("krushku", "krushka", "krushk/ë", sx)
    if any(to in partners.get(p, ()) for p in par.get(frm, ())):
        return _w("njerku", "njerka", "njerk/ë", sx)
    if any(to in kids.get(p, ()) for p in partners.get(frm, ())):
        return _w("thjeshtri", "thjeshtra", "thjeshtër", sx)
    return "familje nga martesa" if to in family_component(data, frm, (par, kids, partners)) else ""


SPOUSE_WORD = {"xhaxhai": "xhaxheshja", "daja": "dajesha", "halla": "burri i hallës", "tezja": "burri i tezes",
               "vëllai": "kunata", "motra": "kunati", "djali": "nusja", "vajza": "dhëndri"}


def _spouse_word(data, frm, to, par, partners):
    """Nëse 'to' është bashkëshort/e i/e një të afërmi me gjak të 'frm' (jo të një paraardhësi): emërtimi
    (xhaxheshja, dajesha, burri i hallës...), përndryshe None."""
    for s_ in sorted(partners.get(to, ())):
        b2 = blood(par, frm, s_)
        if b2 and s_ != frm and b2[1] > 0:  # jo partneri i një paraardhësi (njerku/njerka trajtohet veç)
            word = _blood_word(b2[0], b2[1], sex(data, s_),
                               sex(data, b2[2]) if b2[2] and not b2[2].startswith(VIRTUAL) else "")
            return SPOUSE_WORD.get(word) or f"{_w('burri', 'gruaja', 'partneri/ja', sex(data, to))} · {word}"
    return None


def family_component(data, x, g=None):
    par, kids, partners = g or graph(data)
    seen, q = {x}, deque([x])
    while q:
        for y, _ in _neighbors(par, kids, partners, q.popleft()):
            if y not in seen:
                seen.add(y)
                q.append(y)
    return seen


ORDER = ("bashkëshort", "partner", "babai", "nëna", "prindi", "djali", "vajza", "fëmija", "vëlla", "motra",
         "gjysh", "nip", "mbes", "xhaxh", "hall", "daj", "tez", "kushër", "vjehr", "dhënd", "nus", "kunat", "stër")


def derived(data, name, g=None):
    """Të gjitha lidhjet familjare të 'name' që dalin vetë nga zinxhiri (edhe ato që s'janë ruajtur):
    [(fjala, [personat])], p.sh. [("nëna", ["Besa", "Drita", "Gent"]), ("gjyshja", ["Ana", ...])].
    Pa "familje nga martesa" (shumë e paqartë) dhe pa prindërit e padukshëm."""
    g = g or graph(data)
    by = defaultdict(list)
    for o in family_component(data, name, g):
        if o == name or o.startswith(VIRTUAL):
            continue
        w = kinship(data, o, name, g)  # çfarë është 'name' për 'o'
        if w and not w.startswith("familje"):
            by[w].append(o)

    def rank(w):
        base = w.split(" · ")[0]
        return next((i for i, k in enumerate(ORDER) if base.startswith(k)), len(ORDER)), base

    return [(w, sorted(v, key=str.casefold)) for w, v in sorted(by.items(), key=lambda kv: rank(kv[0]))]


def other_families(data, center):
    """Pemët e familjes që nuk lidhen me 'center': [[emrat]], më të mëdhatë së pari."""
    g = graph(data)
    fam = sorted({n for lk in data["links"] if lk["lloji"] in FAMILY for n in (lk["a"], lk["b"])}, key=str.casefold)
    done = family_component(data, center, g)
    out = []
    for n in fam:
        if n not in done:
            comp = family_component(data, n, g)
            done |= comp
            out.append(sorted((c for c in comp if not c.startswith(VIRTUAL)), key=str.casefold))
    return sorted(out, key=len, reverse=True)


# ---------------- tekstet ----------------
def years(data, name):
    p = person(data, name)
    lin, vdk = (p.get("lindja") or "").strip(), (p.get("vdekja") or "").strip()
    if lin and vdk:
        return f"{lin} – {vdk} †"
    if vdk:
        return f"† {vdk}"
    return f"l. {lin}" if lin else ""


def role(data, lk, who):
    """Roli i personit 'who' te një lidhje jofamiljare (p.sh. 'shef', 'shoqe klase')."""
    if lk.get("roli"):
        return lk["roli"]
    return _w(*DEFAULT_ROLE.get(lk["lloji"], ("", "", "")), sex(data, who))


def link_text(data, lk):
    a, b, t = lk["a"], lk["b"], lk["lloji"]
    if t == "prind":
        return f"{a} — {_w('babai', 'nëna', 'prindi', sex(data, a))} → {b}"
    if t == "partner":
        return f"{a} ⚭ {b}"
    if t == "vella":
        return f"{a} ↔ {b} · vëllezër/motra"
    extra = " · ".join(x for x in (role(data, lk, a), lk.get("ku", "")) if x)
    return f"{a} — {extra} → {b}" if lk.get("roli") else f"{a} ↔ {b} · {extra}"


def circles(data, name):
    """Lidhjet jofamiljare të 'name': {lloji: {ku: [(tjetri, roli)]}}."""
    out = {k: defaultdict(list) for k in OTHER}
    for lk in data["links"]:
        if lk["lloji"] in OTHER and name in (lk["a"], lk["b"]):
            other = lk["b"] if lk["a"] == name else lk["a"]
            r = role(data, lk, other) if (other == lk["a"] or not lk.get("roli")) else f"{name} është {lk['roli']}"
            out[lk["lloji"]][lk.get("ku", "")].append((other, r))
    return {k: dict(v) for k, v in out.items() if v}


# ---------------- rregullimi i pemës ----------------
def _place(widths, desired, extra=None):
    """Qendrat x të blloqeve sipas radhës, sa më afër 'desired', pa mbivendosje (regresion izotonik / PAVA).
    extra[i] = hapësirë shtesë para bllokut i (p.sh. midis dy familjeve të ndryshme)."""
    n = len(widths)
    if not n:
        return []
    off = [0.0] * n
    for i in range(1, n):
        off[i] = off[i - 1] + (widths[i - 1] + widths[i]) / 2 + GAP + (extra[i] if extra else 0)
    ys = [d - o for d, o in zip(desired, off)]
    stack = []  # [shuma, numri]
    for y in ys:
        stack.append([y, 1])
        while len(stack) > 1 and stack[-2][0] / stack[-2][1] > stack[-1][0] / stack[-1][1]:
            s, c = stack.pop()
            stack[-1][0] += s
            stack[-1][1] += c
    out = []
    for s, c in stack:
        out += [s / c] * c
    return [y + o for y, o in zip(out, off)]


def layout(data, center, up=3, down=2, only_contact=False, faces=()):
    """Pozicionet e pemës rreth 'center'. Kthen dict: nodes, partners, families, width, height."""
    g = graph(data)
    par, kids, partners = g
    # brezi i secilit, vetëm brenda kufijve; 'prev' = rruga drejt qendrës
    gen, prev, q = {center: 0}, {center: None}, deque([center])
    while q:
        x = q.popleft()
        for y, d in _neighbors(par, kids, partners, x):
            gy = gen[x] + d
            if y not in gen and -up <= gy <= down:
                gen[y], prev[y] = gy, x
                q.append(y)
    keep = set(gen)
    if only_contact:
        anc = set(_up(par, center))
        want = {n for n in gen if n in anc or n == center or is_contact(data, n, faces)}
        keep = set()
        for n in want:
            while n is not None and n not in keep:
                keep.add(n)
                n = prev[n]
    # partneri i qendrës (në të njëjtin brez): familja e tij vendoset nga ana tjetër, pa kryqëzime
    inlaw_of = next((pp for pp in sorted(partners.get(center, ())) if gen.get(pp) == 0 and pp in keep), None)
    real = [n for n in gen if n in keep and not n.startswith(VIRTUAL)]  # radha e zbulimit (BFS)

    # blloqet: partnerët në të njëjtin brez rrinë ngjitur
    bl = {n: n for n in real}

    def bfind(v):
        while bl[v] != v:
            v = bl[v]
        return v

    for n in real:
        for s in partners.get(n, ()):
            if s in bl and gen[s] == gen[n]:
                bl[bfind(s)] = bfind(n)
    blocks, rows = {}, defaultdict(list)
    for n in real:
        r = bfind(n)
        if r not in blocks:
            blocks[r] = []
            rows[gen[n]].append(r)
        blocks[r].append(n)
    bw = {r: len(m) * W + (len(m) - 1) * PG for r, m in blocks.items()}
    x = {}
    cx = {}
    for gg, rs in rows.items():  # fillimi: njëri pas tjetrit
        pos = _place([bw[r] for r in rs], [0.0] * len(rs))
        cx.update(zip(rs, pos))

    def member_x():
        for r, mem in blocks.items():
            left = cx[r] - bw[r] / 2 + W / 2
            for j, n in enumerate(mem):
                x[n] = left + j * (W + PG)

    def px(n):
        """x i një personi; prindi i padukshëm = mesi i fëmijëve të tij të dukshëm."""
        if n in x:
            return x[n]
        ks = [x[k] for k in kids.get(n, ()) if k in x]
        return sum(ks) / len(ks) if ks else None

    def mean(v):
        v = [a for a in v if a is not None]
        return sum(v) / len(v) if v else None

    def parents_x(r):
        return mean([px(p) for n in blocks[r] for p in par.get(n, ()) if p in keep])

    def kids_x(r):
        return mean([x[k] for n in blocks[r] for k in kids.get(n, ()) if k in x])

    def order_members():
        for r, mem in blocks.items():
            if len(mem) > 1:
                own = {n: mean([px(p) for p in par.get(n, ()) if p in keep]) for n in mem}
                base = cx[r]
                mem.sort(key=lambda n: (own[n] if own[n] is not None else base, n))

    def sib_key(r, rs):
        """Prindërit e anëtarit të bllokut që ka vëllezër/motra në blloqe të tjera të rreshtit (ose None)."""
        others = {n for q in rs if q != r for n in blocks[q]}
        for n in blocks[r]:
            ps = frozenset(p for p in par.get(n, ()) if p in gen)
            if ps and any(frozenset(p for p in par.get(o, ()) if p in gen) == ps for o in others):
                return ps
        return None

    def contiguous(rs):
        """Vëllezërit/motrat (me blloqet e tyre) rrinë ngjitur, në vendin e të parit prej tyre."""
        keys = {r: sib_key(r, rs) for r in rs}
        out, seen = [], set()
        for r in rs:
            k = keys[r]
            if k is None:
                out.append(r)
            elif k not in seen:
                seen.add(k)
                out += [q for q in rs if keys[q] == k]
        return out

    def sweep(gs, first):
        for gg in gs:
            rs = rows[gg]
            keys = {}
            for r in rs:
                a, b = (parents_x(r), kids_x(r)) if first == "par" else (kids_x(r), parents_x(r))
                keys[r] = a if a is not None else b if b is not None else cx[r]
            rs.sort(key=lambda r: (keys[r], cx[r]))
            rs[:] = contiguous(rs)
            cx.update(zip(rs, _place([bw[r] for r in rs], [keys[r] for r in rs])))
            member_x()

    member_x()
    gs = sorted(rows)
    for _ in range(6):
        sweep(gs, "par")
        order_members()
        sweep(gs[::-1], "kids")
        order_members()
    def fam(r):
        """Prindërit (të dukshëm ose të padukshëm) e anëtarëve të bllokut: dy blloqe me të njëjtët = vëllezër."""
        return {frozenset(par[n]) for n in blocks[r] if par.get(n)}

    def fam_gaps(rs):
        return [0] + [0 if (fam(a) & fam(b)) or not (fam(a) and fam(b)) else FAM_GAP for a, b in zip(rs, rs[1:])]

    def final_place():
        for _ in range(4):  # çdo bllok në mes të prindërve dhe fëmijëve të vet, pa ndryshuar radhën
            for gg in gs + gs[::-1]:
                rs = rows[gg]
                des = [mean([parents_x(r), kids_x(r)]) for r in rs]
                des = [d if d is not None else cx[r] for d, r in zip(des, rs)]
                cx.update(zip(rs, _place([bw[r] for r in rs], des, fam_gaps(rs))))
                member_x()

    fam_edges = []  # (prindërit e dukshëm, fëmija): për të numëruar vijat që kryqëzohen
    for n in real:
        ps = [p for p in par.get(n, ()) if p in x or (p in keep and p.startswith(VIRTUAL))]
        if ps:
            fam_edges.append((ps, n))

    def score():
        """Sa vija prind→fëmijë kryqëzohen (kryesorja), plus gjatësia e tyre (për barazimet)."""
        by_row, length = defaultdict(list), 0.0
        for ps, n in fam_edges:
            ax = mean([px(p) for p in ps])
            if ax is None:
                continue
            by_row[gen[n]].append((ax, x[n]))
            length += abs(ax - x[n])
        cross = 0
        for es in by_row.values():
            for i in range(len(es)):
                for j in range(i + 1, len(es)):
                    if (es[i][0] - es[j][0]) * (es[i][1] - es[j][1]) < -1e-6:
                        cross += 1
        return cross * 100000 + length

    def units(rs):
        """Blloqet e rreshtit të ndara në njësi: çdo grup vëllezërish/motrash lëviz i tëri."""
        out = []
        for r in rs:
            k = sib_key(r, rs)
            if out and k is not None and out[-1][0] == k:
                out[-1][1].append(r)
            else:
                out.append((k, [r]))
        return [u for _, u in out]

    def local_search(ok=lambda: True):
        """Kërkim lokal: ndërro njësitë ngjitur ose radhën e çiftit, nëse kryqëzimet pakësohen (dhe ok())."""
        final_place()
        best = score()
        for _ in range(3):  # kërkim lokal: ndërro njësitë ngjitur ose radhën e çiftit, nëse kryqëzimet pakësohen
            improved = False
            for gg in gs:
                cands = []
                us = units(rows[gg])
                for i in range(len(us) - 1):
                    cands.append(("rows", [r for u in us[:i] + [us[i + 1], us[i]] + us[i + 2:] for r in u]))
                for u in us:
                    for i in range(len(u) - 1):
                        v = u[:i] + [u[i + 1], u[i]] + u[i + 2:]
                        cands.append(("rows", [r for w in us for r in (v if w is u else w)]))
                for r in rows[gg]:
                    if len(blocks[r]) == 2:
                        cands.append(("flip", r))
                for kind, c in cands:
                    saved = ({k: list(v) for k, v in rows.items()}, dict(cx), {k: list(v) for k, v in blocks.items()})
                    if kind == "rows":
                        rows[gg][:] = c
                    else:
                        blocks[c].reverse()
                    member_x()
                    final_place()
                    for g2 in gs:  # rreshtat e tjerë ndjekin ndryshimin (prindërit, pastaj fëmijët)
                        if g2 != gg:
                            rs2 = rows[g2]
                            k2 = {r: (parents_x(r) if parents_x(r) is not None else kids_x(r)) for r in rs2}
                            rs2.sort(key=lambda r: (k2[r] if k2[r] is not None else cx[r], cx[r]))
                            rs2[:] = contiguous(rs2)
                    member_x()
                    final_place()
                    sc = score()
                    if sc < best - 1e-6:
                        best, improved = sc, True
                    else:
                        for k, v in saved[0].items():
                            rows[k][:] = v
                        cx.clear()
                        cx.update(saved[1])
                        for k, v in saved[2].items():
                            blocks[k][:] = v
                        member_x()
            if not improved:
                break
        final_place()

    local_search()
    def sibs_of(n):
        return {m for p in par.get(n, ()) for m in kids.get(p, ()) if m != n}

    def snapshot():
        return ({k: list(v) for k, v in rows.items()}, dict(cx), {k: list(v) for k, v in blocks.items()})

    def restore(saved):
        for k, v in saved[0].items():
            rows[k][:] = v
        cx.clear()
        cx.update(saved[1])
        for k, v in saved[2].items():
            blocks[k][:] = v
        member_x()

    def chains(gg):
        """Zinxhirët e rreshtit: blloqe (çifte ose të vetëm) të lidhura me vëllezër/motra, të renditura që çdo
        partner të rrijë nga ana e vëllezërve/motrave të veta: Leka–Vesa | Mira–Ben | Toni–Era.
        Kthen [(blloqet në radhë, drejtimet e çifteve)] ose [] kur s'ka çifte me vëllezër nga të dyja anët."""
        rs = rows[gg]
        link = {r: {q for q in rs if q != r and any(set(blocks[q]) & sibs_of(m) for m in blocks[r])} for r in rs}
        seen, out = set(), []
        for r0 in sorted(rs, key=cx.get):
            if r0 in seen or not link[r0]:
                continue
            comp, st_ = set(), [r0]
            while st_:
                v = st_.pop()
                if v not in comp:
                    comp.add(v)
                    st_ += list(link[v])
            seen |= comp
            if not any(len(blocks[r]) == 2 for r in comp):
                continue  # vetëm vëllezër pa çifte: 'contiguous' i mban tashmë bashkë

            def sides(r):
                return [m for m in blocks[r] if any(set(blocks[q]) & sibs_of(m) for q in comp if q != r)]

            ends = [r for r in comp if len(sides(r)) <= 1]
            if not ends:
                continue  # rreth (rast i rrallë): lëre siç është
            start = min(ends, key=cx.get)
            order, orient, placed = [], {}, set()

            def place(r, left_member):
                mem = list(blocks[r])
                if len(mem) == 2:
                    if left_member is not None:
                        if mem[0] != left_member:
                            mem.reverse()
                    elif sides(r) and mem[-1] not in sides(r):
                        mem.reverse()  # fillimi: anëtari me vëllezër/motra nga e djathta
                orient[r] = mem
                order.append(r)
                placed.add(r)
                for q in sorted(comp - placed, key=cx.get):
                    if q in placed:
                        continue
                    hit = [m for m in blocks[q] if sibs_of(mem[-1]) & {m}]
                    if hit:
                        place(q, hit[0])

            place(start, None)
            for q in sorted(comp - placed, key=cx.get):  # pjesë që s'u arritën nga e djathta
                place(q, None)
            out.append((order, orient))
        return out

    def violations():
        """Sa vëllezër/motra ndodhen nga ana e partnerit tjetër të çiftit (0 = të gjithë nga ana e vet)."""
        bad = 0
        for gg in gs:
            for r in rows[gg]:
                if len(blocks[r]) != 2:
                    continue
                a, b = blocks[r]
                others = [set(blocks[q]) for q in rows[gg] if q != r]
                if not (any(o & sibs_of(a) for o in others) and any(o & sibs_of(b) for o in others)):
                    continue  # vetëm njëri ka vëllezër këtu (p.sh. Ilir–Lule): s'ka anë për të ruajtur
                for q in rows[gg]:
                    if q == r:
                        continue
                    if set(blocks[q]) & sibs_of(a) and cx[q] > cx[r] and not set(blocks[q]) & sibs_of(b):
                        bad += 1
                    if set(blocks[q]) & sibs_of(b) and cx[q] < cx[r] and not set(blocks[q]) & sibs_of(a):
                        bad += 1
        return bad

    def move_units(g2):
        """Çdo grup vëllezërish i rreshtit provohet në çdo pozicion (jo vetëm një hap): mbahet nëse pakësohen
        kryqëzimet pa prishur anët e çifteve. P.sh. fëmijët e tezes kalojnë në anën tjetër të çiftit."""
        best, v0 = score(), violations()
        for _ in range(6):
            us = units(rows[g2])
            found = False
            for i in range(len(us)):
                for j in range(len(us)):
                    if i == j:
                        continue
                    new = us[:i] + us[i + 1:]
                    new.insert(j, us[i])
                    saved = snapshot()
                    rs = rows[g2]
                    rs[:] = [r for u in new for r in u]
                    des = [mean([parents_x(r), kids_x(r)]) for r in rs]  # vetëm ky rresht (i shpejtë)
                    des = [d_ if d_ is not None else cx[r] for d_, r in zip(des, rs)]
                    cx.update(zip(rs, _place([bw[r] for r in rs], des, fam_gaps(rs))))
                    member_x()
                    sc = score()
                    if sc < best - 1e-6 and violations() <= v0:
                        best, found = sc, True
                        break
                    restore(saved)
                if found:
                    break
            if not found:
                break
        final_place()

    def couple_sides():
        for gg in gs:
            for order, orient in chains(gg):
                base = snapshot()
                best_sc, best_state = None, None
                for rev in (False, True):
                    restore(base)
                    seq = order[::-1] if rev else order
                    rs = rows[gg]
                    pos = min(rs.index(r) for r in order)
                    rest = [q for q in rs if q not in order]
                    rs[:] = rest[:pos] + seq + rest[pos:]
                    for r, mem in orient.items():
                        blocks[r][:] = mem[::-1] if rev else mem
                    member_x()
                    final_place()
                    for g2 in gs:
                        if g2 > gg:  # fëmijët ndjekin prindërit
                            rs2 = rows[g2]
                            k2 = {q: (parents_x(q) if parents_x(q) is not None else kids_x(q)) for q in rs2}
                            rs2.sort(key=lambda q: (k2[q] if k2[q] is not None else cx[q], cx[q]))
                            rs2[:] = contiguous(rs2)
                    member_x()
                    final_place()
                    for g2 in gs:  # për secilin drejtim: renditja më e mirë e fëmijëve, pastaj krahaso
                        if g2 > gg:
                            move_units(g2)
                    sc = score() + violations() * 10 ** 7
                    if best_sc is None or sc < best_sc - 1e-6:
                        best_sc, best_state = sc, snapshot()
                restore(best_state)
                final_place()

    couple_sides()

    def follow_rows(g1):
        """Rreshtat e tjerë ndjekin rreshtin g1: poshtë sipas prindërve, sipër sipas fëmijëve."""
        for g2 in gs:
            if g2 == g1:
                continue
            rs2 = rows[g2]
            if g2 > g1:
                k2 = {q: (parents_x(q) if parents_x(q) is not None else kids_x(q)) for q in rs2}
            else:
                k2 = {q: (kids_x(q) if kids_x(q) is not None else parents_x(q)) for q in rs2}
            rs2.sort(key=lambda q: (k2[q] if k2[q] is not None else cx[q], cx[q]))
            rs2[:] = contiguous(rs2)
        member_x()
        final_place()

    def far_side(member, right):
        """Prindërit e 'member' (qendra ose partneri i saj) rrinë nga ana e çiftit qendror; TË GJITHË vëllezërit/motrat
        e tyre (me familjet) shkojnë në anën tjetër (right=True: djathtas). Vijat zgjaten, por nuk kryqëzohen me
        qendrën dhe partnerin. Provohen të dy radhët e çiftit të prindërve; mbahet ajo me më pak kryqëzime."""
        ps = [p for p in par.get(member, ()) if p in x]
        if not ps:
            return
        g1 = gen[ps[0]]
        B = bfind(ps[0])
        base = snapshot()
        best_sc, best_state = None, None
        mem0 = list(blocks[B])
        for near, far in ([(mem0[0], mem0[-1]), (mem0[-1], mem0[0])] if len(mem0) == 2 else [(mem0[0], mem0[0])]):
            restore(base)
            rs = rows[g1]
            sib = sibs_of(far) | sibs_of(near)
            s_far = [q for q in sorted(rs, key=cx.get) if q != B and set(blocks[q]) & sibs_of(far)]
            s_near = [q for q in sorted(rs, key=cx.get) if q != B and q not in s_far and set(blocks[q]) & sibs_of(near)]
            seq = s_far + s_near  # nga B drejt skajit: së pari vëllezërit e anëtarit të largët
            rest = [q for q in rs if q != B and q not in seq]
            i = sum(1 for q in rest if cx[q] < cx[B])
            rs[:] = rest[:i] + [B] + seq + rest[i:] if right else rest[:i] + seq[::-1] + [B] + rest[i:]
            if len(mem0) == 2:
                blocks[B][:] = [near, far] if right else [far, near]
            for q in seq:  # vëllai/motra më afër B-së
                blocks[q].sort(key=lambda m: (m not in sib) if right else (m in sib))
            member_x()
            final_place()
            follow_rows(g1)
            for g2 in gs:
                if g2 > g1:
                    move_units(g2)
            sc = score()
            if best_sc is None or sc < best_sc - 1e-6:
                best_sc, best_state = sc, snapshot()
        restore(best_state)
        final_place()

    def partner_far_side():
        """Qendra dhe partneri i saj: prindërit e të dyve ngjitur, vëllezërit/motrat e prindërve në anët e largëta
        (të qendrës majtas, të partnerit djathtas, ose anasjelltas)."""
        if not inlaw_of or inlaw_of not in x or center not in x:
            return
        partner_right = x[center] < x[inlaw_of]
        far_side(inlaw_of, right=partner_right)
        far_side(center, right=not partner_right)

    partner_far_side()

    gmin = min(gen[n] for n in real)
    shift = M + W / 2 - min(x.values())
    nodes = {n: {"x": x[n] + shift, "y": M + (gen[n] - gmin) * (H + VG), "gen": gen[n]} for n in real}
    if inlaw_of in nodes and center in nodes and nodes[inlaw_of]["x"] < nodes[center]["x"]:
        # partneri (dhe familja e tij) gjithmonë djathtas qendrës: pema si në pasqyrë
        lo_, hi_ = min(v["x"] for v in nodes.values()), max(v["x"] for v in nodes.values())
        for v in nodes.values():
            v["x"] = lo_ + hi_ - v["x"]
    pairs = []
    for mem in blocks.values():
        for a, b in zip(mem, mem[1:]):
            if b in partners.get(a, ()):
                pairs.append((a, b))
    fams = {}
    for n in real:
        ps = tuple(sorted(p for p in par.get(n, ()) if p in keep))
        if ps:
            fams.setdefault(ps, []).append(n)
    families = [{"parents": [p for p in ps if p in nodes], "children": sorted(ch, key=lambda c: nodes[c]["x"])}
                for ps, ch in fams.items()]
    # ----- rrethi i qendrës (shoqëria, shkolla, puna, të tjera): grupe poshtë familjes -----
    # Çdo shok/koleg është një "njësi": ai (+ partneri) sipër, fëmijët e tij poshtë, me vijat e familjes.
    side, labels = [], {}
    circ = circles(data, center)
    sx0 = min(v["x"] for v in nodes.values()) - W / 2  # grupet poshtë pemës, krah për krah
    sy = max(v["y"] for v in nodes.values()) + H + 70
    taken = set(nodes)
    max_cols = 8  # sa karta në rresht brenda një grupi (poshtë pemës ka vend: grupi mbetet i ulët)
    for k, title in OTHER.items():
        items = [(o, r, ku) for ku, lst in sorted(circ.get(k, {}).items(), key=lambda kv: (kv[0] == "", kv[0].casefold()))
                 for o, r in sorted(lst, key=lambda t: t[0].casefold()) if o not in taken]
        if not items:
            continue
        grp = {"kind": k, "title": f"{re.sub(r':material/[a-z_]+:\s*', '', title)} · {len(items)}", "x": sx0, "y": sy}
        side.append(grp)
        y_row, x_col, row_h = sy + 34, 0, 0
        for o, r, ku in items:
            taken.add(o)
            top = [o] + [q for q in sorted(partners.get(o, ())) if q not in taken and not q.startswith(VIRTUAL)]
            taken.update(top)
            kids_ = [c for c in sorted(set().union(*(kids.get(t, set()) for t in top)), key=str.casefold)
                     if c not in taken and not c.startswith(VIRTUAL)]
            taken.update(kids_)
            cols = max(len(top), len(kids_), 1)
            if x_col and x_col + cols > max_cols:  # njësia nuk nxë më në këtë rresht
                y_row += row_h + 16
                x_col, row_h = 0, 0
            ux = sx0 + 14 + x_col * (W + PG)
            uw = cols * W + (cols - 1) * PG
            tw = len(top) * W + (len(top) - 1) * PG
            for i, t in enumerate(top):
                nodes[t] = {"x": ux + (uw - tw) / 2 + W / 2 + i * (W + PG), "y": y_row, "gen": None, "side": k}
            if len(top) > 1:
                pairs += [(top[0], t) for t in top[1:2]]
            labels[o] = r + (f" · {ku}" if ku else "")
            if len(top) > 1:
                labels[top[1]] = kinship(data, o, top[1]) or "partneri/ja"
            if kids_:
                kw = len(kids_) * W + (len(kids_) - 1) * PG
                for i, c in enumerate(kids_):
                    nodes[c] = {"x": ux + (uw - kw) / 2 + W / 2 + i * (W + PG), "y": y_row + H + VG, "gen": None,
                                "side": k}
                    kin = kinship(data, o, c) or "fëmija"
                    labels[c] = f"{kin} {_w('i', 'e', 'i/e', sex(data, c))} {o}"
                families.append({"parents": [t for t in top[:2] if kids.get(t, set()) & set(kids_)],
                                 "children": kids_})
            x_col += cols
            row_h = max(row_h, H + (H + VG if kids_ else 0))
        bottom = y_row + row_h
        right = max(v["x"] for v in nodes.values() if v.get("side") == k) + W / 2
        grp.update(w=right + 14 - sx0, h=bottom + 14 - sy)
        sx0 = right + 14 + 40
    width = max(v["x"] for v in nodes.values()) + W / 2 + M
    height = max(max(v["y"] for v in nodes.values()) + H + M, sy + M)
    return {"center": center, "nodes": nodes, "partners": pairs, "families": families, "side": side,
            "labels": labels, "width": width, "height": height, "graph": g}


# ---------------- vizatimi ----------------
COL = {"line": "#CBD5E1", "partner": "#e0609a", "card": "#ffffff", "border": "#E2E8F0", "center": "#4F46E5",
       "hi": "#10b981", "name": "#0F172A", "kin": "#4338CA", "years": "#64748B",
       "m": "#dbeafe", "f": "#fce7f3", "": "#e5e7eb", "ini": "#374151"}


LANE_COL = ("#818CF8", "#F472B6", "#34D399", "#FBBF24", "#38BDF8", "#A78BFA")  # familjet që kryqëzohen
SIDE_COL = {"shoqeri": "#0EA5E9", "shkolla": "#F59E0B", "puna": "#10B981", "tjeter": "#8B5CF6", "martese": "#E11D48"}
GROUP_COL = {"qendra": "#4F46E5", "gjak": "#6366F1", "martese": "#E11D48", **SIDE_COL}  # shiriti + unaza e kartës
CAMERA = ("M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"
          "M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z")  # Lucide 'camera'


def group(lay, data, n):
    """Ngjyra e kartës: qendra, gjak (paraardhës/pasardhës/kushërinj), martese (familja e partnerit), ose rrethi."""
    v = lay["nodes"][n]
    if n == lay["center"]:
        return "qendra"
    if v.get("side"):
        return v["side"]
    return "gjak" if blood(lay["graph"][0], lay["center"], n) else "martese"


def _initials(name):
    parts = [p for p in name.replace("-", " ").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _short(s, n=17):
    return s if len(s) <= n else s[: n - 1] + "…"


def svg(lay, data, faces=(), images=None, highlight=(), counts=None):
    """SVG e pemës. images: {emri: 'data:image/jpeg;base64,...'} (fytyrat); counts: {emri: numri i fotove}.
    Çdo kartë ka data-name="emri", që klikimi të dijë kush u zgjodh."""
    images, counts = images or {}, counts or {}
    e = html.escape
    nodes, g = lay["nodes"], lay["graph"]
    w, h = int(lay["width"]), int(lay["height"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           f'font-family="Segoe UI, Arial, sans-serif" style="max-width:none">',
           '<defs><clipPath id="pema-rreth" clipPathUnits="objectBoundingBox">'
           '<circle cx=".5" cy=".5" r=".5"/></clipPath>'
           '<clipPath id="pema-kreu"><rect x="0" y="0" width="1" height="1"/></clipPath>'
           '<filter id="pema-hije" x="-20%" y="-20%" width="140%" height="160%">'
           '<feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0F172A" flood-opacity="0.12"/></filter>'
           '</defs>']
    ln = f'class="vija" stroke="{COL["line"]}" stroke-width="2" fill="none" stroke-linejoin="round"'
    # grupet e rrethit: kuti me ngjyrën e grupit + vijë me pika nga qendra te grupi (lidhja jote me ta)
    cn = nodes.get(lay["center"])
    for grp in lay.get("side", []):
        c = SIDE_COL.get(grp["kind"], COL["line"])
        out.append(f'<rect x="{grp["x"]}" y="{grp["y"]}" width="{grp.get("w", W + 28)}" height="{grp.get("h", H + 48)}" '
                   f'rx="16" fill="{c}" fill-opacity="0.06" stroke="{c}" stroke-opacity="0.45" stroke-width="1.5"/>')
    # vijat prind → fëmijë
    by_row = defaultdict(list)
    for f in lay["families"]:
        if f["children"]:
            by_row[nodes[f["children"][0]]["y"]].append(f)
    for top, fams in by_row.items():
        items = []
        for f in fams:
            kx = [nodes[c]["x"] for c in f["children"]]
            ps = f["parents"]
            if not ps:  # vëllezër/motra pa prindër të njohur: vetëm një shirit sipër tyre
                if len(kx) > 1:
                    yb = top - 16
                    out.append(f'<path d="M{min(kx)},{yb} H{max(kx)}" {ln}/>')
                    out += [f'<path d="M{c},{yb} V{top}" {ln}/>' for c in kx]
                continue
            pxs = sorted(nodes[p]["x"] for p in ps)
            couple = len(ps) == 2 and abs(pxs[1] - pxs[0] - (W + PG)) < 1  # çift ngjitur: nga mesi i vijës
            anchors = [(pxs[0] + pxs[1]) / 2] if couple else pxs
            allx = anchors + kx
            items.append({"ps": ps, "kx": kx, "anchors": anchors, "couple": couple,
                          "lo": min(allx), "hi": max(allx)})
        # korsi: familjet që mbivendosen horizontalisht marrin lartësi të ndryshme (jo vija mbi vija)
        ends = []
        for it in sorted(items, key=lambda t: (t["lo"], t["hi"])):
            lane = next((i for i, e in enumerate(ends) if e < it["lo"] - 12), None)
            if lane is None:
                lane = len(ends)
                ends.append(it["hi"])
            else:
                ends[lane] = it["hi"]
            it["lane"] = lane
        nl = max(1, len(ends))
        step = min(16, (VG - 40) / max(1, nl - 1))
        ci = 0
        for it in sorted(items, key=lambda t: t["lane"]):
            yb = top - VG / 2 + (it["lane"] - (nl - 1) / 2) * step
            cross = any(o is not it and o["lo"] < it["hi"] and it["lo"] < o["hi"] for o in items)
            col = LANE_COL[ci % len(LANE_COL)] if cross else COL["line"]
            ci += cross
            y0 = nodes[it["ps"][0]]["y"]
            d = "".join(f"M{ax},{y0 + (FACE_CY if it['couple'] else H)} V{yb}" for ax in it["anchors"])
            d += f"M{it['lo']},{yb} H{it['hi']}" + "".join(f"M{c},{yb} V{top}" for c in it["kx"])
            # "ura": një shirit me ngjyrën e sfondit poshtë vijës, që kryqëzimet të duken qartë
            out.append(f'<g class="vija"><path d="{d}" fill="none" stroke-width="7" stroke-linejoin="round" '
                       f'style="stroke: var(--st-secondary-background-color, #EEF2F7)"/>'
                       f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2" stroke-linejoin="round" '
                       f'stroke-linecap="round"/></g>')
    for a, b in lay["partners"]:
        y = nodes[a]["y"] + FACE_CY
        x1, x2 = sorted((nodes[a]["x"], nodes[b]["x"]))
        xm = (x1 + x2) / 2
        out.append(f'<path class="vija" d="M{x1 + W / 2},{y} H{x2 - W / 2}" stroke="{COL["partner"]}" '
                   f'stroke-width="3" stroke-linecap="round"/><circle class="vija" cx="{xm}" cy="{y}" r="5" '
                   f'fill="#ffffff" stroke="{COL["partner"]}" stroke-width="2.5"/>')
    # titujt e grupeve të rrethit (shoqëria, shkolla, puna...)
    for grp in lay.get("side", []):
        c = SIDE_COL.get(grp["kind"], COL["line"])
        out.append(f'<rect x="{grp["x"] + 14}" y="{grp["y"] + 9}" width="4" height="16" rx="2" fill="{c}"/>'
                   f'<text x="{grp["x"] + 24}" y="{grp["y"] + 22}" font-size="13" font-weight="700" '
                   f'fill="{c}">{e(grp["title"])}</text>')
    # kartat
    center = lay["center"]
    labels = lay.get("labels", {})
    for i, (n, v) in enumerate(sorted(nodes.items(), key=lambda kv: (kv[1]["y"], kv[1]["x"]))):
        x0, y0 = v["x"] - W / 2, v["y"]
        cx, cy = v["x"], v["y"] + FACE_CY
        contact = is_contact(data, n, faces)
        gc = GROUP_COL.get(group(lay, data, n), COL["line"])
        stroke = (f'stroke="{COL["hi"]}" stroke-width="4"' if n in highlight else  # i zgjedhuri, para qendrës
                  f'stroke="{COL["center"]}" stroke-width="3"' if n == center else
                  f'stroke="{COL["border"]}" stroke-width="1.5"' + ("" if contact else ' stroke-dasharray="5 4"'))
        kin = "Ti" if n == data.get("une") else labels.get(n) or kinship(data, center, n, g)
        kin = kin[:1].upper() + kin[1:]
        nf = counts.get(n, 0)
        out.append(f'<g class="karta" data-name="{e(n, quote=True)}" style="--i:{i}" '
                   f'opacity="{1 if contact or n == center else 0.8}">'
                   f'<title>{e(n)}{" · " + e(kin) if kin else ""}{f" · {nf} foto" if nf else ""}</title>')
        fill = "#EEF2FF" if n == center else COL["card"]
        out.append(f'<rect class="bg" x="{x0}" y="{y0}" width="{W}" height="{H}" rx="16" fill="{fill}" '
                   f'filter="url(#pema-hije)" {stroke}/>')
        out.append(f'<path d="M{x0 + 16},{y0 + 1.5} H{x0 + W - 16}" stroke="{gc}" stroke-width="4" '
                   f'stroke-linecap="round"/>')  # shiriti me ngjyrën e grupit
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{FACE_R + 3.5}" fill="none" stroke="{gc}" stroke-width="2.5" '
                   f'stroke-opacity="0.85"/>')
        if n in images:
            out.append(f'<image href="{images[n]}" x="{cx - FACE_R}" y="{cy - FACE_R}" width="{2 * FACE_R}" '
                       f'height="{2 * FACE_R}" clip-path="url(#pema-rreth)" preserveAspectRatio="xMidYMid slice"/>')
        else:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{FACE_R}" fill="{COL[sex(data, n)]}"/>'
                       f'<text x="{cx}" y="{cy + 7}" text-anchor="middle" font-size="20" font-weight="600" '
                       f'fill="{COL["ini"]}">{e(_initials(n))}</text>')
        if nf:  # sa foto ka: kamerë (SVG) + numri, lart djathtas
            bw_ = 26 + 6.2 * len(str(nf))
            bx = x0 + W - bw_ - 6
            out.append(f'<rect x="{bx}" y="{y0 + 8}" width="{bw_}" height="18" rx="9" fill="#EEF2FF"/>'
                       f'<path d="{CAMERA}" transform="translate({bx + 6},{y0 + 11.5}) scale(0.46)" fill="none" '
                       f'stroke="#4338CA" stroke-width="2.6" stroke-linejoin="round"/>'
                       f'<text x="{bx + 20}" y="{y0 + 21}" font-size="10.5" font-weight="600" '
                       f'fill="#3730A3">{nf}</text>')
        out.append(f'<text x="{cx}" y="{y0 + 102}" text-anchor="middle" font-size="13.5" font-weight="600" '
                   f'fill="{COL["name"]}">{e(_short(n))}</text>')
        via = ""
        if " · nga " in kin:  # "Xhaxhai · nga Ana" → "Xhaxhai" + rreshti i vogël "nga Ana"
            kin, via = kin.split(" · nga ", 1)
            via = "nga " + via
        if kin:
            out.append(f'<text x="{cx}" y="{y0 + 120}" text-anchor="middle" font-size="11.5" '
                       f'fill="{COL["kin"]}">{e(_short(kin, 20))}</text>')
        yr = years(data, n)
        third = " · ".join(t for t in (via, yr) if t)
        if third:
            out.append(f'<text x="{cx}" y="{y0 + 137}" text-anchor="middle" font-size="10.5" '
                       f'fill="{COL["years"]}">{e(_short(third, 22))}</text>')
        if v.get("side") in (None, "martese") and n != center:  # edhe shok/koleg i qendrës: shenjë në cep
            tag = next((role(data, lk, n) for lk in data["links"] if lk["lloji"] in OTHER
                        and {lk["a"], lk["b"]} == {n, center}), None)
            if tag:
                kind = next(lk["lloji"] for lk in data["links"] if lk["lloji"] in OTHER and {lk["a"], lk["b"]} == {n, center})
                tw = 14 + 6 * len(tag)
                out.append(f'<rect x="{x0 + 6}" y="{y0 + 9}" width="{tw}" height="16" rx="8" '
                           f'fill="{SIDE_COL.get(kind, COL["line"])}"/><text x="{x0 + 6 + tw / 2}" y="{y0 + 21}" '
                           f'text-anchor="middle" font-size="10" font-weight="600" fill="#ffffff">{e(tag)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)
