"""Logjika e Renditësit të Fotove: skanim, lexim i datës/GPS, kopjim dhe anulim."""
import csv
import datetime as dt
import hashlib
import os
import pickle
import re
import shutil
import string
from pathlib import Path

from PIL import Image

import paths  # të dhënat e përdoruesit: veç kodit
import time as _time

_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:
    pass

IMG_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mkv"}

# Dosje që nuk kanë foto personale (sistem, programe, kode)
SKIP_DIRS = {
    "appdata", "windows", "program files", "program files (x86)", "programdata",
    "system volume information", "node_modules", "site-packages", "venv",
    "steamapps", "steamlibrary", "epic games", "recovery", "perflogs",
}

MUAJT = ["Janar", "Shkurt", "Mars", "Prill", "Maj", "Qershor", "Korrik",
         "Gusht", "Shtator", "Tetor", "Nëntor", "Dhjetor"]

VENDET = {
    "AL": "Shqipëri", "XK": "Kosovë", "MK": "Maqedonia e Veriut", "ME": "Mal i Zi",
    "GR": "Greqi", "IT": "Itali", "DE": "Gjermani", "CH": "Zvicër", "AT": "Austri",
    "FR": "Francë", "ES": "Spanjë", "GB": "Mbretëria e Bashkuar", "US": "SHBA",
    "TR": "Turqi", "HR": "Kroaci", "RS": "Serbi", "BE": "Belgjikë", "NL": "Holandë",
    "SE": "Suedi", "NO": "Norvegji", "DK": "Danimarkë", "FI": "Finlandë", "PL": "Poloni",
    "CZ": "Çeki", "SI": "Slloveni", "BA": "Bosnjë", "BG": "Bullgari", "RO": "Rumani",
    "HU": "Hungari", "PT": "Portugali", "IE": "Irlandë", "CA": "Kanada",
    "AE": "Emiratet e Bashkuara", "EG": "Egjipt", "CY": "Qipro", "MT": "Maltë",
    "LU": "Luksemburg", "SK": "Sllovaki", "AU": "Australi",
}

LOG_NAME = "renditja-log.csv"
NOW_YEAR = dt.date.today().year

_FNAME_DATE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)"
)


def default_sources():
    """Dosja e përdoruesit + çdo disk tjetër (D:, E:, ...)."""
    out = [str(Path.home())]
    for letter in string.ascii_uppercase:
        if letter in ("A", "B", "C"):
            continue
        root = f"{letter}:\\"
        if os.path.exists(root):
            out.append(root)
    return out


def _norm(p):
    return os.path.normcase(os.path.abspath(p))


def iter_files(sources, include_videos=True, min_kb=50, exclude=(), stats=None):
    """Gjen të gjitha fotot/videot, duke anashkaluar dosjet e sistemit.

    stats (dict, opsional) mbush: pa_akses (dosje që s'lexohen), te_vogla, perjashtuar (dosje).
    """
    exts = IMG_EXT | (VID_EXT if include_videos else set())
    excl = [_norm(e) for e in exclude if e]
    seen = set()
    st_ = stats if stats is not None else {}
    for k in ("pa_akses", "te_vogla", "perjashtuar", "dyfish_shteg"):
        st_.setdefault(k, 0)
    skipped = st_.setdefault("lista", [])  # (shtegu, madhësia, arsyeja) për raportin

    def _err(e):
        st_["pa_akses"] += 1
        skipped.append((getattr(e, "filename", str(e)), None, "🚫 Dosje pa akses (Windows nuk e lejon leximin)"))

    for src in sources:
        if not src or not os.path.isdir(src):
            continue
        for root, dirs, files in os.walk(src, onerror=_err):
            if LOG_NAME in files or CATALOG_NAME in files:  # dalje e mëparshme e këtij programi = kopje
                st_["perjashtuar"] += 1
                skipped.append((root, None, "📁 Dosje e anashkaluar: rezultat i mëparshëm i këtij programi (kopje)"))
                dirs[:] = []
                continue
            keep = []
            for d in dirs:
                full = _norm(os.path.join(root, d))
                if d.lower() in SKIP_DIRS or d.startswith((".", "$")):
                    skipped.append((os.path.join(root, d), None, "📁 Dosje e anashkaluar: sistem/program/e fshehur"))
                    continue
                if any(full == e or full.startswith(e + os.sep) for e in excl):
                    st_["perjashtuar"] += 1
                    skipped.append((os.path.join(root, d), None, "📁 Dosje e anashkaluar: dosja e daljes"))
                    continue
                keep.append(d)
            dirs[:] = keep
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in exts:
                    if ext in VID_EXT:
                        skipped.append((os.path.join(root, f), None, "🎬 Video (videot ishin të çaktivizuara)"))
                    continue
                p = os.path.join(root, f)
                key = _norm(p)
                if key in seen:
                    st_["dyfish_shteg"] += 1
                    continue
                seen.add(key)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    st_["pa_akses"] += 1
                    skipped.append((p, None, "🚫 Skedar pa akses"))
                    continue
                if size >= min_kb * 1024:
                    yield p, size, ("video" if ext in VID_EXT else "foto")
                else:
                    st_["te_vogla"] += 1
                    skipped.append((p, size, f"🔎 Shumë i vogël (nën {min_kb} KB, zakonisht ikonë)"))


SCAN_LOG = paths.data("skanimet.csv")
SCAN_FIELDS = ["koha", "gjithsej", "foto", "video", "dosjet", "dalja", "min_kb", "videot",
               "te_vogla", "pa_akses", "perjashtuar"]


def log_scan(row):
    """Ruan një rresht për çdo skanim, që të krahasohen skanimet me njëri-tjetrin."""
    os.makedirs(os.path.dirname(SCAN_LOG), exist_ok=True)
    new = not os.path.exists(SCAN_LOG)
    with open(SCAN_LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SCAN_FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in SCAN_FIELDS})


def load_scans():
    try:
        with open(SCAN_LOG, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _exif_date(value):
    if not value:
        return None
    try:
        d = dt.datetime.strptime(str(value).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return d if 1990 <= d.year <= NOW_YEAR else None


def _gps_deg(vals, ref):
    d, m, s = (float(x) for x in vals)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W") else deg


def read_meta(path, kind):
    """Kthen (data, burimi_i_datës, lat, lon, kamera)."""
    date, src, lat, lon, camera = None, None, None, None, None
    if kind == "foto":
        try:
            with Image.open(path) as im:
                ex = im.getexif()
                if ex:
                    cam = " ".join(str(ex.get(t, "")).strip("\x00 ") for t in (0x010F, 0x0110)).strip()
                    camera = cam or None
                    sub = ex.get_ifd(0x8769)
                    date = _exif_date(sub.get(36867) or sub.get(36868) or ex.get(306))
                    if date:
                        src = "exif"
                    g = ex.get_ifd(0x8825)
                    if g and 2 in g and 4 in g:
                        la = _gps_deg(g[2], g.get(1, "N"))
                        lo = _gps_deg(g[4], g.get(3, "E"))
                        if abs(la) <= 90 and abs(lo) <= 180 and not (la == 0 and lo == 0):
                            lat, lon = la, lo
        except Exception:
            pass
    if not date:
        m = _FNAME_DATE.search(os.path.basename(path))
        if m:
            try:
                d = dt.datetime(int(m[1]), int(m[2]), int(m[3]))
                if 1990 <= d.year <= NOW_YEAR:
                    date, src = d, "emri"
            except ValueError:
                pass
    if not date:
        try:
            date, src = dt.datetime.fromtimestamp(os.path.getmtime(path)), "skedari"
        except OSError:
            pass
    return date, src, lat, lon, camera


META_CACHE = paths.data("metadatat.pkl")


def load_meta_cache():
    """{'meta': {çelësi: (data, burimi, lat, lon, kamera)}, 'sha1': {çelësi: hash}}; çelësi = shteg|madhësi|mtime,
    pra një skedar i ndryshuar lexohet përsëri."""
    try:
        with open(META_CACHE, "rb") as f:
            c = pickle.load(f)
    except Exception:
        c = {}
    c.setdefault("meta", {})
    c.setdefault("sha1", {})
    return c


def save_meta_cache(c):
    os.makedirs(os.path.dirname(META_CACHE), exist_ok=True)
    tmp = META_CACHE + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(c, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, META_CACHE)


def _file_key(path, size):
    try:
        m = int(os.path.getmtime(path))
    except OSError:
        m = 0
    return f"{path}|{size}|{m}"


def read_meta_all(records, cache, progress=None):
    """read_meta për çdo rekord, por nga disku lexohen vetëm skedarët e rinj/të ndryshuar.
    Shton r['_mk'] (çelësi i cache). Kthen sa skedarë u lexuan vërtet."""
    meta, new = cache["meta"], 0
    for i, r in enumerate(records):
        k = r["_mk"] = _file_key(r["path"], r["size"])
        v = meta.get(k)
        if v is None:
            v = meta[k] = read_meta(r["path"], r["kind"])
            new += 1
        r["date"], r["date_src"], r["lat"], r["lon"], r["camera"] = v
        if progress and i % 200 == 0:
            progress(i + 1, len(records), new)
    return new


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mark_duplicates(records, sha_cache=None):
    """Shënon kopjet identike (e njëjta përmbajtje). Hash vetëm kur madhësia përputhet.
    sha_cache: {r['_mk']: hash} (nga load_meta_cache), që skedarët e pandryshuar të mos lexohen përsëri."""
    by_size = {}
    for r in records:
        by_size.setdefault(r["size"], []).append(r)
    for group in by_size.values():
        if len(group) < 2:
            continue
        first = {}
        for r in group:
            k = r.get("_mk")
            h = sha_cache.get(k) if sha_cache is not None and k else None
            if h is None:
                try:
                    h = _sha1(r["path"])
                except OSError:
                    continue
                if sha_cache is not None and k:
                    sha_cache[k] = h
            if h in first:
                r["dup_of"] = first[h]
            else:
                first[h] = r["path"]


def geocode(records):
    pts = [r for r in records if r.get("lat") is not None]
    if not pts:
        return
    import reverse_geocoder as rg

    res = rg.search([(r["lat"], r["lon"]) for r in pts], mode=1, verbose=False)
    for r, g in zip(pts, res):
        r["vendi"] = VENDET.get(g.get("cc"), g.get("cc") or "Tjetër")
        r["qyteti"] = g.get("name") or g.get("admin1") or "I panjohur"


def _safe(name):
    return re.sub(r'[<>:"/\\|?*]', "", str(name)).strip(" .") or "I panjohur"


def plan(records, by_date=True, by_place=True, fallback_mtime=True, skip_dups=True,
         allowed_cats=None, cat_labels=None, by_content=False, people=None):
    """Kthen listë (burimi, [shtigje relative në dosjen e re]).

    allowed_cats: nëse jepet, kopjohen vetëm fotot e këtyre kategorive (filtri AI).
    people: {shtegu: [emrat e personave]} për dosjet 'Njerëz'.
    """
    out = []
    for r in records:
        if skip_dups and r.get("dup_of"):
            continue
        cat = r.get("cat")
        if allowed_cats is not None and cat and cat not in allowed_cats:
            continue
        dests = []
        name = os.path.basename(r["path"])
        if by_content and cat and cat_labels and cat in cat_labels:
            dests.append(os.path.join("Sipas Përmbajtjes", _safe(cat_labels[cat]), name))
        for person in (people or {}).get(r["path"], []):
            dests.append(os.path.join("Njerëz", _safe(person), name))
        if by_date:
            d = r.get("date")
            if d and (r.get("date_src") != "skedari" or fallback_mtime):
                folder = os.path.join("Sipas Datës", str(d.year), f"{d.month:02d}-{MUAJT[d.month - 1]}")
            else:
                folder = os.path.join("Sipas Datës", "Pa Datë")
            dests.append(os.path.join(folder, name))
        if by_place and r.get("vendi"):
            dests.append(os.path.join("Sipas Vendit", _safe(r["vendi"]), _safe(r["qyteti"]), name))
        if dests:
            out.append((r["path"], dests))
    return out


# ---------------- Katalogu: të gjitha të dhënat, një herë ----------------
CATALOG_NAME = "katalogu.csv"
CAT_FIELDS = ["shtegu", "lloji", "data", "burimi_datës", "vendi", "qyteti", "kategoria",
              "kategoria_emri", "personat", "personi_kryesor", "dyfishe", "kamera",
              "madhesia_kb", "siguria", "fytyra", "dyfishe_e"]
LEVELS = ["Viti", "Muaji", "Vendi", "Qyteti", "Përmbajtja", "Personi"]


def build_rows(records, people=None, cat_labels=None):
    """people: {shtegu: [(emri, madhësia_e_fytyrës), ...]}."""
    rows = []
    for r in records:
        ps = sorted((people or {}).get(r["path"], []), key=lambda x: -x[1])
        names = []
        for n, _ in ps:
            if n not in names:
                names.append(n)
        cat = r.get("cat") or ""
        rows.append({
            "shtegu": r["path"], "lloji": r["kind"],
            "data": r["date"].isoformat(timespec="seconds") if r.get("date") else "",
            "burimi_datës": r.get("date_src") or "",
            "vendi": r.get("vendi") or "", "qyteti": r.get("qyteti") or "",
            "kategoria": cat, "kategoria_emri": (cat_labels or {}).get(cat, cat),
            "personat": "; ".join(names), "personi_kryesor": names[0] if names else "",
            "dyfishe": "po" if r.get("dup_of") else "", "kamera": r.get("camera") or "",
            "madhesia_kb": round(r.get("size", 0) / 1024),
            "siguria": f"{r['conf']:.2f}" if r.get("conf") is not None and cat else "",
            "fytyra": len(r.get("faces") or []), "dyfishe_e": r.get("dup_of") or "",
        })
    return rows


def save_catalog(out_dir, rows):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, CATALOG_NAME)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: hapet mirë në Excel
        w = csv.DictWriter(f, fieldnames=CAT_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return path


def load_catalog(out_dir):
    path = os.path.join(out_dir, CATALOG_NAME)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _level_folder(row, level, fallback_mtime):
    d = None
    if row["data"] and (row["burimi_datës"] != "skedari" or fallback_mtime):
        d = dt.datetime.fromisoformat(row["data"])
    if level == "Viti":
        return str(d.year) if d else "Pa Datë"
    if level == "Muaji":
        return f"{d.month:02d}-{MUAJT[d.month - 1]}" if d else "Pa Datë"
    if level == "Vendi":
        return row["vendi"] or "Pa Vend"
    if level == "Qyteti":
        return row["qyteti"] or "Pa Vend"
    if level == "Përmbajtja":
        return row["kategoria_emri"] or "Pa Kategori"
    if level == "Personi":
        return row["personi_kryesor"] or "Pa Persona"
    return ""


OTHERS = "Të tjerë"


def row_people(row):
    return [n.strip() for n in (row.get("personat") or "").split(";") if n.strip()]


def has_faces(row):
    return str(row.get("fytyra") or "0").strip() not in ("", "0")


VIDEOS = "Videot"


def plan_layout(rows, levels, allowed_cats=None, skip_dups=True, fallback_mtime=True,
                per_person=False, others=True, videos="with", skip=None):
    """Një destinacion për çdo foto, sipas niveleve të zgjedhura (p.sh. ['Viti', 'Muaji']).

    per_person=True: vetëm fotot me njerëz, dhe çdo foto shkon te dosja e SECILIT person që është në të.
    Fotot me fytyra pa person të njohur shkojnë te 'Të tjerë' (nëse others=True).
    videos: 'own' → Videot/Viti/Muaji; 'with' → si fotot (te per_person: Videot/..., se AI-ja nuk njeh
    persona në video); 'none' → asnjë video. skip: shtigjet që përdoruesi i hoqi (p.sh. videot pa ✔).
    """
    out = []
    for row in rows:
        if skip_dups and row["dyfishe"]:
            continue
        if skip and row["shtegu"] in skip:
            continue
        if allowed_cats is not None and row["kategoria"] and row["kategoria"] not in allowed_cats:
            continue
        name = os.path.basename(row["shtegu"])
        if row.get("lloji") == "video" and (videos != "with" or per_person):
            if videos == "none":
                continue
            parts = [VIDEOS] + [_safe(_level_folder(row, lv, fallback_mtime)) for lv in ("Viti", "Muaji")]
            out.append((row["shtegu"], [os.path.join(*parts, name)]))
            continue
        if per_person:
            persons = row_people(row)
            if not persons:
                if not (others and has_faces(row)):
                    continue
                persons = [OTHERS]
            dests = []
            for person in persons:
                parts = [_safe(person if lv == "Personi" else _level_folder(row, lv, fallback_mtime))
                         for lv in levels if lv]
                dests.append(os.path.join(*parts, name))
            out.append((row["shtegu"], dests))
            continue
        parts = [_safe(_level_folder(row, lv, fallback_mtime)) for lv in levels if lv]
        out.append((row["shtegu"], [os.path.join(*parts, name)]))
    return out


def _unique(path, taken):
    base, ext = os.path.splitext(path)
    cand, i = path, 1
    while os.path.exists(cand) or _norm(cand) in taken:
        cand = f"{base}_{i}{ext}"
        i += 1
    taken.add(_norm(cand))
    return cand


def execute(planned, out_dir, move=False, progress=None):
    """Kopjon (ose zhvendos) skedarët dhe shkruan regjistrin për anulim."""
    os.makedirs(out_dir, exist_ok=True)
    log_path = os.path.join(out_dir, LOG_NAME)
    new_log = not os.path.exists(log_path)
    taken, done, errors = set(), 0, []
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["veprimi", "burimi", "destinacioni"])
        for i, (src, rels) in enumerate(planned):
            try:
                targets = [_unique(os.path.join(out_dir, rel), taken) for rel in rels]
                for t in targets:
                    os.makedirs(os.path.dirname(t), exist_ok=True)
                first = targets[0]
                if move:
                    shutil.move(src, first)
                    w.writerow(["move", src, first])
                else:
                    shutil.copy2(src, first)
                    w.writerow(["copy", src, first])
                # Kopjet e tjera (p.sh. e njëjta foto te çdo person) = lidhje e fortë te kopja e parë:
                # duken si skedarë të zakonshëm, por nuk zënë vend shtesë. Origjinali nuk preket.
                for t in targets[1:]:
                    try:
                        os.link(first, t)
                    except OSError:
                        shutil.copy2(first, t)
                    w.writerow(["copy", src, t])
                done += 1
            except Exception as e:
                errors.append((src, str(e)))
            if progress and (i % 20 == 0 or i == len(planned) - 1):
                progress(i + 1, len(planned))
    return done, errors


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


_LINKS = {}


def _existing(path):
    probe = os.path.abspath(path)
    while not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    return probe


def links_supported(out_dir):
    """A lejon disku i daljes lidhje të forta (NTFS po; FAT/exFAT jo)?"""
    import tempfile

    probe = _existing(out_dir)
    drive = os.path.splitdrive(probe)[0].lower() or probe
    if drive not in _LINKS:
        ok, a = False, None
        try:
            fd, a = tempfile.mkstemp(dir=probe, prefix=".renditesi_prove_")
            os.close(fd)
            os.link(a, a + "_l")
            os.remove(a + "_l")
            ok = True
        except OSError:
            pass
        finally:
            if a and os.path.exists(a):
                os.remove(a)
        _LINKS[drive] = ok
    return _LINKS[drive]


def space_check(planned, out_dir, move=False, sizes=None):
    """Sa bajt duhen për kopjimin dhe sa ka vend në diskun e daljes.

    Kthen dict: nevojitet, liruar (kopjet e vjetra që fshihen te ri-renditja), te_lira, disku, mjafton,
    lidhje (a përdoren lidhje të forta për kopjet shtesë), shtese (sa vende shtesë në dosje).
    """
    sizes = sizes or {}
    need = 0
    links = any(len(d) > 1 for _, d in planned) and links_supported(out_dir)
    extra = 0
    for src, dests in planned:
        s = sizes.get(src)
        if s is None:
            try:
                s = os.path.getsize(src)
            except OSError:
                s = 0
        same_drive = os.path.splitdrive(os.path.abspath(src))[0].lower() == \
            os.path.splitdrive(os.path.abspath(out_dir))[0].lower()
        # Zhvendosja në të njëjtin disk nuk zë vend të ri; kopjet shtesë janë lidhje (0 bajt)
        need += 0 if (move and same_drive) else s
        extra += len(dests) - 1
        if not links:
            need += s * (len(dests) - 1)
    # Te ri-renditja, kopjet e vjetra fshihen para se të kopjohen të rejat
    freed = 0
    log = os.path.join(out_dir, LOG_NAME)
    if os.path.exists(log):
        with open(log, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("veprimi") == "copy":
                    try:
                        freed += os.path.getsize(r["destinacioni"])
                    except OSError:
                        pass
    probe = os.path.abspath(out_dir)
    while not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    try:
        free = shutil.disk_usage(probe).free
    except OSError:
        free = None
    reserve = 1024 ** 3  # lë të paktën 1 GB të lirë, që Windows të mos ngecë
    ok = free is None or need <= free + freed - reserve
    return {"nevojitet": need, "liruar": freed, "te_lira": free, "disku": os.path.splitdrive(probe)[0] or probe,
            "mjafton": ok, "mbetet": None if free is None else free + freed - need,
            "lidhje": links, "shtese": extra}


def undo(out_dir):
    """Fshin kopjet dhe kthen në vend skedarët e zhvendosur, sipas regjistrit."""
    log_path = os.path.join(out_dir, LOG_NAME)
    if not os.path.exists(log_path):
        return 0, ["Nuk u gjet regjistri, nuk ka çfarë të anulohet."]
    with open(log_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    n, errors = 0, []
    for r in reversed(rows):
        try:
            if r["veprimi"] == "move":
                if os.path.exists(r["destinacioni"]) and not os.path.exists(r["burimi"]):
                    os.makedirs(os.path.dirname(r["burimi"]), exist_ok=True)
                    shutil.move(r["destinacioni"], r["burimi"])
                    n += 1
            elif os.path.exists(r["destinacioni"]):
                os.remove(r["destinacioni"])
                n += 1
        except Exception as e:
            errors.append(f"{r['destinacioni']}: {e}")
    os.remove(log_path)
    for root, dirs, files in os.walk(out_dir, topdown=False):
        if not os.listdir(root):
            try:
                os.rmdir(root)
            except OSError:
                pass
    return n, errors
