"""Pjesa AI: njohja e përmbajtjes (CLIP) dhe e fytyrave (OpenCV YuNet + SFace).

Gjithçka punon lokalisht. Rezultatet ruhen në cache, që skanimi i dytë të jetë i shpejtë.
"""
import json
import os
import pickle

import numpy as np
from PIL import Image, ImageOps
import time as _time

_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")
import paths  # noqa: E402  (të dhënat e përdoruesit: veç kodit, te %LOCALAPPDATA%\RenditesiFotove\data)

CACHE = paths.data("analiza.pkl")
PEOPLE = paths.data("personat.json")
YUNET = os.path.join(MODELS, "face_detection_yunet_2023mar.onnx")
SFACE = os.path.join(MODELS, "face_recognition_sface_2021dec.onnx")

# (çelësi, emri shqip, foto reale?, e përfshirë si parazgjedhje?, përshkrimet për CLIP)
CATEGORIES = [
    ("njerez", "Njerëz & Selfie", True, True,
     ["a photo of a person", "a selfie photo", "a group photo of friends", "a family photo", "a portrait photo of a man", "a portrait photo of a woman"]),
    ("plazh", "Plazh & Det", True, True, ["a photo of a beach", "a photo of the sea", "a photo of a swimming pool"]),
    ("natyre", "Natyrë & Mal", True, True,
     ["a landscape photo of mountains", "a photo of nature with trees", "a photo of a forest", "a photo of a lake", "a photo of a sunset", "a photo of snow"]),
    ("qytet", "Qytet & Ndërtesa", True, True, ["a photo of a city street", "a photo of buildings", "a photo of a monument", "a photo of a city at night"]),
    ("ushqim", "Ushqim & Pije", True, True, ["a photo of food", "a photo of a meal on a table", "a photo of a cake", "a photo of drinks"]),
    ("kafshe", "Kafshë", True, True, ["a photo of a dog", "a photo of a cat", "a photo of a bird", "a photo of an animal"]),
    ("makina", "Makina", True, True, ["a photo of a car", "a photo of a motorcycle"]),
    ("festa", "Festa & Dasma", True, True, ["a photo of a wedding", "a photo of a party celebration", "a photo of a birthday party", "a photo of people dancing"]),
    ("sport", "Sport", True, True, ["a photo of people playing sports", "a photo of a football match", "a photo of a gym"]),
    ("brenda", "Shtëpi & Ambiente", True, True, ["a photo of a room interior", "a photo of a living room", "a photo of a restaurant interior"]),
    ("dokument", "Dokumente & Fatura", True, False,
     ["a photo of a document", "a photo of a receipt", "a photo of a paper with text", "a photo of an id card"]),
    ("screenshot", "Screenshot", False, False,
     ["a screenshot of a phone screen", "a screenshot of a computer screen", "a screenshot of a chat conversation", "a screenshot of a website", "a screenshot of a social media app"]),
    ("loje", "Lojëra", False, False, ["a screenshot of a video game", "video game graphics", "a 3d rendered video game character", "a video game menu"]),
    ("logo", "Logo & Ikona", False, False, ["a logo", "an icon", "a simple flat graphic design", "a brand logo on a plain background"]),
    ("art", "Vizatime & Art", False, False, ["a cartoon illustration", "a drawing", "anime artwork", "digital art", "a clipart image"]),
    ("meme", "Meme & Poster", False, False, ["a meme with text", "a poster with text", "an advertisement banner", "a quote image with text"]),
]
CAT_LABEL = {c[0]: c[1] for c in CATEGORIES}
CAT_REAL = {c[0]: c[2] for c in CATEGORIES}
CAT_DEFAULT = [c[0] for c in CATEGORIES if c[3]]
NAME_SIM = 0.60  # qendra e grupit vs qendrat e ruajtura: mbi këtë, grupi merr vetë emrin
MAX_PARTS = 300  # sa qendra ruhen për një emër (cache/personat.json)
REJECT_SIM = 0.90  # grupi i ndarë me ✂️ nga një emër: në skanimin tjetër njihet (qendër ≥ kaq) dhe nuk e merr atë emër
NOT_PHOTO_SURE = 0.70  # mbi këtë siguri, një "jo-foto" (lojë, logo...) nuk kontrollohet për fytyra


# ---------------- cache ----------------
def _key(r):
    try:
        m = os.path.getmtime(r["path"])
    except OSError:
        m = 0
    return f"{r['path']}|{r['size']}|{int(m)}"


def load_cache():
    try:
        with open(CACHE, "rb") as f:
            return pickle.load(f)
    except Exception:
        return {}


def save_cache(c):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(c, f)
    os.replace(tmp, CACHE)


# ---------------- modelet ----------------
class Analyzer:
    def __init__(self, do_content=True, do_faces=True):
        self.clip = None
        self.det = self.rec = None
        if do_content:
            import open_clip
            import torch

            torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))
            model, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
            model.eval()
            tok = open_clip.get_tokenizer("ViT-B-32")
            prompts, owner = [], []
            for i, c in enumerate(CATEGORIES):
                for p in c[4]:
                    prompts.append(p)
                    owner.append(i)
            with torch.no_grad():
                t = model.encode_text(tok(prompts))
                t = t / t.norm(dim=-1, keepdim=True)
            self.clip = (torch, model, pre, t, np.array(owner))
        if do_faces:
            import cv2

            self.cv2 = cv2
            self.det = cv2.FaceDetectorYN.create(YUNET, "", (320, 320), 0.85, 0.3, 5000)
            self.rec = cv2.FaceRecognizerSF.create(SFACE, "")

    def classify(self, images):
        torch, model, pre, tfeat, owner = self.clip
        with torch.no_grad():
            x = torch.stack([pre(im) for im in images])
            f = model.encode_image(x)
            f = f / f.norm(dim=-1, keepdim=True)
            probs = (100.0 * f @ tfeat.T).softmax(dim=-1).numpy()
        out = []
        for p in probs:
            per = np.zeros(len(CATEGORIES))
            np.add.at(per, owner, p)
            out.append(per)
        return out

    def faces(self, im):
        cv2 = self.cv2
        small = im.copy()
        small.thumbnail((1280, 1280))
        W, H = small.width, small.height
        bgr = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2BGR)
        self.det.setInputSize((bgr.shape[1], bgr.shape[0]))
        _, dets = self.det.detect(bgr)
        res = []
        if dets is None:
            return res
        for d in dets:
            w, h = d[2], d[3]
            if min(w, h) < 24:  # fytyrë shumë e vogël, e pasigurt
                continue
            crop = self.rec.alignCrop(bgr, d)
            e = self.rec.feature(crop).flatten().astype(np.float32)
            e /= np.linalg.norm(e) + 1e-9
            box = (float(d[0]) / W, float(d[1]) / H, float(w) / W, float(h) / H)  # në përqindje
            res.append({"box": box, "emb": e})
        return res


def _decide(per, r):
    """Zgjedh kategorinë, duke marrë parasysh edhe EXIF dhe emrin e skedarit."""
    keys = [c[0] for c in CATEGORIES]
    name = os.path.basename(r["path"]).lower()
    if "screenshot" in name or "screen shot" in name or name.startswith("scr_"):
        return "screenshot", 1.0
    if r.get("camera"):  # e bërë me kamerë/telefon → foto reale
        per = np.where([CAT_REAL[k] for k in keys], per, 0)
    i = int(np.argmax(per))
    cat, conf = keys[i], float(per[i] / (per.sum() + 1e-9))
    # Ka fytyra të vërteta dhe AI nuk është i sigurt që s'është foto → është foto me njerëz
    if r.get("faces") and not CAT_REAL[cat] and conf < NOT_PHOTO_SURE:
        return "njerez", conf
    return cat, conf


def analyze(records, do_content, do_faces, progress=None, batch=16):
    """Shton r['cat'], r['conf'], r['faces'] te çdo foto. Përdor cache."""
    cache = load_cache()
    todo = []
    for r in records:
        if r["kind"] != "foto":
            r["cat"], r["conf"], r["faces"] = "video", 1.0, []
            continue
        c = cache.get(_key(r), {})
        if do_faces and "faces" in c:
            r["faces"] = c["faces"]
        if do_content and "per" in c:
            r["cat"], r["conf"] = _decide(c["per"], r)
        if (do_content and "per" not in c) or (do_faces and "faces" not in c):
            todo.append(r)
    if not todo:
        if progress:
            progress(1, 1)
        return
    an = Analyzer(do_content, do_faces)
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        imgs, ok = [], []
        for r in chunk:
            try:
                with Image.open(r["path"]) as im:
                    im.draft("RGB", (1600, 1600))
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    im.thumbnail((1600, 1600))
                imgs.append(im)
                ok.append(r)
            except Exception:
                r["cat"], r["conf"], r["faces"] = "gabim", 0.0, []
        if ok and do_content and an.clip:
            for r, per in zip(ok, an.classify(imgs)):
                cache.setdefault(_key(r), {})["per"] = per
                r["cat"], r["conf"] = _decide(per, r)
        if ok and do_faces and an.det:
            for r, im in zip(ok, imgs):
                # Fytyrat nuk kërkohen aty ku AI është i sigurt që është lojë/logo/vizatim
                sure_fake = not CAT_REAL.get(r.get("cat"), True) and r.get("conf", 0) >= NOT_PHOTO_SURE
                fs = [] if sure_fake else an.faces(im)
                entry = cache.setdefault(_key(r), {})
                entry["faces"] = fs
                r["faces"] = fs
                if "per" in entry:
                    r["cat"], r["conf"] = _decide(entry["per"], r)
        if progress:
            progress(min(start + batch, len(todo)), len(todo))
        if start % (batch * 20) == 0:
            save_cache(cache)
    save_cache(cache)


# ---------------- grupimi i fytyrave ----------------
CLUSTER_SIM = 0.45  # ngjashmëria mesatare minimale e një fytyre me anëtarët e grupit
SMALL_SIM = 0.55    # për fytyrat e vogla (më pak të besueshme) kërkohet më shumë ngjashmëri
MIN_FACE = 0.04     # fytyrat më të ngushta se 4% e fotos (njerëz në sfond) nuk krijojnë persona
MIN_PHOTOS = 3      # një person duhet të dalë të paktën në 3 foto
SAMPLE = 5000       # sa fytyra grupohen njëherësh (memoria rritet me katrorin e këtij numri)


def _cluster_labels(X, W, seed=0):
    """Grupim pa 'efektin zinxhir' (që bashkonte të gjithë në një person).

    1. Fytyrat e qarta grupohen me average linkage: një fytyrë hyn në grup vetëm nëse ngjan
       mesatarisht me GJITHË anëtarët, jo vetëm me një fqinj.
    2. Kur ka shumë fytyra, grupohet një mostër dhe pjesa tjetër caktohet te grupi me
       ngjashmërinë mesatare më të lartë (x · mesatarja = ngjashmëria mesatare me anëtarët).
    3. Ato që mbeten pa grup grupohen në raundin tjetër.
    4. Fytyrat e vogla caktohen vetëm te grupet ekzistuese, me prag më të lartë.
    """
    from sklearn.cluster import AgglomerativeClustering

    labels = np.full(len(X), -1)
    rng = np.random.default_rng(seed)
    means = []
    left = np.where(W >= MIN_FACE)[0]
    for _ in range(10):
        if len(left) < 2:
            break
        pick = left if len(left) <= SAMPLE else rng.choice(left, SAMPLE, replace=False)
        lab = AgglomerativeClustering(n_clusters=None, metric="cosine", linkage="average",
                                      distance_threshold=1 - CLUSTER_SIM).fit_predict(X[pick])
        added = 0
        for l in np.unique(lab):
            mem = pick[lab == l]
            if len(mem) < 2:
                continue
            labels[mem] = len(means)
            means.append(X[mem].mean(0))
            added += 1
        rest = left[labels[left] < 0]
        if len(rest) and means:
            S = X[rest] @ np.stack(means).T
            best = S.argmax(1)
            ok = S[np.arange(len(rest)), best] >= CLUSTER_SIM
            labels[rest[ok]] = best[ok]
        if len(pick) == len(left) or not added:
            break
        left = left[labels[left] < 0]
    small = np.where((W < MIN_FACE) & (labels < 0))[0]
    if len(small) and means:
        S = X[small] @ np.stack(means).T
        best = S.argmax(1)
        ok = S[np.arange(len(small)), best] >= SMALL_SIM
        labels[small[ok]] = best[ok]
    return labels


GROUPING = paths.data("grupimi.pkl")
GROUPING_KEEP = 5  # sa grupime të ndryshme mbahen (p.sh. për dosje të ndryshme)


def _cached_labels(X, W):
    """_cluster_labels, por i njëjti grup fytyrash (dhe të njëjtat parametra) nuk grupohet dy herë."""
    import hashlib

    h = hashlib.sha1(X.tobytes())
    h.update(np.asarray(W, dtype=np.float64).tobytes())
    h.update(repr((CLUSTER_SIM, SMALL_SIM, MIN_FACE, SAMPLE)).encode())
    key = h.hexdigest()
    try:
        with open(GROUPING, "rb") as f:
            saved = pickle.load(f)
    except Exception:
        saved = {}
    if key in saved and len(saved[key]) == len(X):
        return saved[key]
    labels = _cluster_labels(X, W)
    saved.pop(key, None)
    saved[key] = np.asarray(labels)
    while len(saved) > GROUPING_KEEP:
        saved.pop(next(iter(saved)))
    try:
        os.makedirs(os.path.dirname(GROUPING), exist_ok=True)
        with open(GROUPING + ".tmp", "wb") as f:
            pickle.dump(saved, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(GROUPING + ".tmp", GROUPING)
    except OSError:
        pass
    return labels


def rename_groups(groups):
    """Emrat e grupeve sipas kujtesës së tanishme (p.sh. kur rihapet një skanim i vjetër nga historiku)."""
    known, rejected = load_people(), load_rejected()
    for g in groups or []:
        g["name"] = name_for(g["centroid"], known, rejected)


def cluster_faces(records):
    """Kthen listë grupesh: {'id', 'faces': [(record, box)], 'centroid', 'name'}."""
    items = [(r, f) for r in records for f in (r.get("faces") or [])]
    if not items:
        return []
    X = np.stack([f["emb"] for _, f in items]).astype(np.float32)
    W = np.array([f["box"][2] for _, f in items])
    labels = _cached_labels(X, W)
    groups = {}
    for (r, f), lab in zip(items, labels):
        if lab < 0:
            continue
        groups.setdefault(int(lab), []).append((r, f))
    known, rejected = load_people(), load_rejected()
    out = []
    for lab, members in groups.items():
        # Një person = foto të ndryshme; mos e numëro dy herë të njëjtën foto
        if len({m[0]["path"] for m in members}) < MIN_PHOTOS:
            continue
        cen = np.mean([f["emb"] for _, f in members], axis=0)
        cen /= np.linalg.norm(cen) + 1e-9
        out.append({"faces": members, "centroid": cen.astype(np.float32), "name": name_for(cen, known, rejected)})
    out.sort(key=lambda g: -len({m[0]["path"] for m in g["faces"]}))
    for i, g in enumerate(out):
        g["id"] = i
    return out


def name_for(cen, known, rejected=None):
    """Emri i ruajtur që i përket kësaj qendre grupi, ose "" (edhe kur përdoruesi e ka ndarë më parë nga ai emër)."""
    best, name = NAME_SIM, ""
    for n, vs in known.items():
        if not vs:
            continue
        s = float(np.max(np.asarray(vs, dtype=np.float32) @ cen))
        if s >= best:
            no = (rejected or {}).get(n)
            # i ngjan më shumë një grupi të ndarë me ✂️ nga ky emër sesa pjesëve të pranuara → nuk është ai
            if no and float(np.max(np.asarray(no, dtype=np.float32) @ cen)) >= max(REJECT_SIM, s):
                continue
            best, name = s, n
    return name


HIDE_SIM = 0.60  # si NAME_SIM: një grup kaq i ngjashëm me një person të fshehur fshihet edhe në skanimin tjetër


def _hidden_file():
    return PEOPLE.replace(".json", "_fshehur.json")


def load_hidden():
    """[qendrat e personave që përdoruesi i fshehu: "nuk e njoh / s'më duhet"]."""
    try:
        with open(_hidden_file(), encoding="utf-8") as f:
            return [list(map(float, v)) for v in json.load(f) if v]
    except Exception:
        return []


def _write_hidden(vs):
    p = _hidden_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump([[round(float(x), 5) for x in v] for v in vs], f)
    os.replace(p + ".tmp", p)


def hide(cens):
    """Mbaj mend: këta persona nuk i duhen përdoruesit (fshihen te Personat dhe s'marrin dosje)."""
    vs = [_unit(v) for v in load_hidden()]
    for c in map(_unit, cens):
        if not vs or max(float(v @ c) for v in vs) < SAME_PART:
            vs.append(c)
    _write_hidden(vs[-2000:])


def unhide(cens):
    """Kthe personat e fshehur (të gjitha qendrat që u ngjajnë këtyre ≥ HIDE_SIM)."""
    cens = [_unit(c) for c in cens]
    _write_hidden([v for v in load_hidden() if not cens or max(float(_unit(v) @ c) for c in cens) < HIDE_SIM])


def is_hidden(cen, hidden, known=None):
    """A i ngjan ky grup një personi të fshehur (≥ HIDE_SIM) më shumë se çdo emri të njohur?"""
    if not hidden:
        return False
    s = float(np.max(np.asarray(hidden, dtype=np.float32) @ cen))
    if s < HIDE_SIM:
        return False
    best_name = max((float(np.max(np.asarray(vs, dtype=np.float32) @ cen)) for vs in (known or {}).values() if vs),
                    default=0.0)
    return s > best_name


def load_rejected():
    """{emri: [qendrat e grupeve që përdoruesi i ndau me ✂️ nga ky emër]}."""
    try:
        with open(PEOPLE.replace(".json", "_jo.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def reject(name, cens):
    """Mbaj mend: këto grupe NUK janë ky person (që në skanimin tjetër të mos marrin këtë emër)."""
    name = (name or "").strip()
    if not name:
        return
    data = load_rejected()
    vs = [_unit(v) for v in data.get(name, [])]
    for c in cens:
        c = _unit(c)
        if not vs or max(float(v @ c) for v in vs) < SAME_PART:
            vs.append(c)
    data[name] = [[round(float(x), 5) for x in v] for v in vs[-MAX_PARTS:]]
    p = PEOPLE.replace(".json", "_jo.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def load_people():
    """{emri: [qendra, ...]}: një person mund të ketë disa pjesë (p.sh. në mosha të ndryshme)."""
    try:
        with open(PEOPLE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    out = {}
    for n, v in data.items():
        if v and isinstance(v[0], (int, float)):  # formati i vjetër: një qendër e vetme
            v = [v]
        out[n] = [list(map(float, x)) for x in v if x]
    return out


SAME_PART = 0.95  # dy qendra kaq të ngjashme = e njëjta pjesë (mos e ruaj dy herë / hiqe kur ndahet)
LOST_BACKUP = 1  # kur një shkrim fshin kaq emra njëherësh, ruhet cache/personat_<data-ora>.json


def _unit(c):
    c = np.asarray(c, dtype=np.float32)
    return c / (np.linalg.norm(c) + 1e-9)


def _write_people(known):
    """Shkrim i sigurt: së pari skedar i përkohshëm, pastaj zëvendësim; versioni i mëparshëm mbetet si kopje."""
    os.makedirs(os.path.dirname(PEOPLE), exist_ok=True)
    known = {n: [[round(float(x), 5) for x in v] for v in vs] for n, vs in known.items() if vs}
    before = load_people()
    lost = set(before) - set(known)
    shrunk = [n for n, vs in before.items() if n in known and len(known[n]) * 2 <= len(vs) and len(vs) >= 2]
    if (len(lost) >= LOST_BACKUP or shrunk) and os.path.exists(PEOPLE):
        # një veprim po fshin shumë emra njëherësh (ndodhi më 13.11: 20 emra): ruaj një kopje me datë
        import glob
        import shutil
        import time as _t

        shutil.copy2(PEOPLE, PEOPLE.replace(".json", _t.strftime("_%Y%m%d-%H%M%S.json")))
        for old in sorted(glob.glob(PEOPLE.replace(".json", "_2*.json")))[:-10]:
            os.remove(old)
    tmp = PEOPLE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(known, f, ensure_ascii=False)
    if os.path.exists(PEOPLE):
        try:
            os.replace(PEOPLE, PEOPLE.replace(".json", "_kopje.json"))
        except OSError:
            pass
    os.replace(tmp, PEOPLE)


def _strip(vs, cens):
    return [v for v in vs if not cens or max(float(_unit(v) @ c) for c in cens) < SAME_PART]


def remember(name, cens, steal_from=()):
    """Lidh përgjithmonë këto pjesë (qendra) me emrin. Herën tjetër çdo pjesë e njeh vetë emrin.
    Pjesët u hiqen VETËM emrave te steal_from (riemërtim i qartë: emri i vjetër i kartës). Më parë u hiqeshin
    të gjithë emrave: një kartë e përzier (një person me grupe të të tjerëve) ua merrte pjesët emrave të tjerë
    dhe kujtesa boshatisej pak e nga pak."""
    name = (name or "").strip()
    if not name:
        return
    cens = [_unit(c) for c in cens]
    steal = {s.casefold() for s in steal_from if s}
    known = {n: (_strip(vs, cens) if n.casefold() in steal else vs) for n, vs in load_people().items() if n != name}
    vs = [_unit(v) for v in load_people().get(name, [])]
    for c in cens:
        if not vs or max(float(v @ c) for v in vs) < SAME_PART:
            vs.append(c)
    known[name] = vs[-MAX_PARTS:]
    _write_people(known)
    no = load_rejected()
    if no.get(name):  # përdoruesi e bashkoi sërish: nuk është më "jo ky"
        kept = _strip(no[name], cens)
        if len(kept) != len(no[name]):
            no[name] = kept
            p = PEOPLE.replace(".json", "_jo.json")
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(no, f, ensure_ascii=False)
            os.replace(p + ".tmp", p)


def forget(cens, names):
    """Këto pjesë nuk i përkasin më këtyre emrave (p.sh. u ndanë me ✂️ ose u fshi emri i kartës).
    Vetëm emrat e dhënë preken: emrat e tjerë që kanë pjesë të ngjashme mbeten siç janë."""
    only = {n.casefold() for n in names if n}
    if not only:
        return
    cens = [_unit(c) for c in cens]
    _write_people({n: (_strip(vs, cens) if n.casefold() in only else vs) for n, vs in load_people().items()})


def forget_name(name):
    _write_people({n: vs for n, vs in load_people().items() if n != name})
    fixes = load_fixes()
    if fixes:  # edhe vendimet për fytyra me këtë emër
        for e in fixes:
            e["jo"] = [n for n in e.get("jo", []) if n.casefold() != name.casefold()]
            if (e.get("po") or "").casefold() == name.casefold():
                e["po"] = ""
        _write_fixes(fixes)


# ---- Vendimet për fytyra të veçanta: "kjo fytyrë NUK është X" / "ËSHTË Y" / "askush" ----
FIX_SAME = 0.85  # e njëjta foto + fytyrë kaq e ngjashme = e njëjta fytyrë (në skanimin tjetër)


def _fixes_file():
    d, b = os.path.split(PEOPLE)
    return os.path.join(d, b.replace("personat", "fotot_e_korrigjuara"))


def load_fixes():
    """[{path, emb, jo: [emrat], po: emri, askush: bool}]."""
    try:
        with open(_fixes_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _write_fixes(fixes):
    fixes = [e for e in fixes if e.get("jo") or e.get("po") or e.get("askush")]
    p = _fixes_file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(fixes, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


def fix_faces(items):
    """items: [(foto, emb, veprimi, emri)]; veprimi: jo / unjo / po / unpo / askush / unaskush."""
    fixes = load_fixes()
    idx = {}
    for e in fixes:
        idx.setdefault(os.path.normcase(e["path"]), []).append(e)
    for path, emb, op, name in items:
        emb, name = _unit(emb), (name or "").strip()
        same = idx.setdefault(os.path.normcase(path), [])
        e = next((e for e in same if float(_unit(e["emb"]) @ emb) >= FIX_SAME), None)
        if e is None:
            if op.startswith("un"):
                continue
            e = {"path": path, "emb": [round(float(x), 5) for x in emb], "jo": [], "po": "", "askush": False}
            fixes.append(e)
            same.append(e)
        jo = [n for n in e.get("jo", []) if n.casefold() != name.casefold()]
        if op == "jo" and name:
            e["jo"] = jo + [name]
            if (e.get("po") or "").casefold() == name.casefold():
                e["po"] = ""
        elif op == "unjo":
            e["jo"] = jo
        elif op == "po" and name:
            e["po"], e["jo"], e["askush"] = name, jo, False
        elif op == "unpo" and (e.get("po") or "").casefold() == name.casefold():
            e["po"] = ""
        elif op in ("askush", "unaskush"):
            e["askush"] = op == "askush"
    _write_fixes(fixes)


THUMBS = paths.data("fytyrat")
PHOTO_THUMBS = paths.data("fotot")
VIDEO_THUMBS = paths.data("videot")


def _short_path(p):
    """Shtegu i shkurtër i Windows-it (8.3): OpenCV nuk hap dot disa shtigje me ë, ç..."""
    if os.name != "nt" or p.isascii():
        return None
    import ctypes

    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024)
    return buf.value if 0 < n < 1024 else None


def video_thumb(path, size=360):
    """(pamja e një kuadri nga videoja, kohëzgjatja në sekonda). Ruhen në disk; (None, None) nëse s'hapet."""
    import hashlib

    try:
        m = int(os.path.getmtime(path))
    except OSError:
        return None, None
    key = hashlib.md5(f"{path}|{m}|{size}".encode()).hexdigest()
    fp = os.path.join(VIDEO_THUMBS, key[:2], key + ".jpg")
    info = fp[:-4] + ".txt"
    if os.path.exists(info):
        try:
            txt = open(info, encoding="utf-8").read().strip()
        except OSError:
            txt = ""
        return (fp if os.path.exists(fp) else None), (float(txt) if txt else None)
    import cv2

    cap, img, dur = None, None, None
    for p in (path, _short_path(path)):
        if p:
            cap = cv2.VideoCapture(p)
            if cap.isOpened():
                break
            cap.release()
            cap = None
    if cap is not None:
        try:
            n, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0, cap.get(cv2.CAP_PROP_FPS) or 0
            if n > 0 and fps > 0:
                dur = n / fps
            if n > 10:  # jo kuadri i parë (shpesh i zi)
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * 0.1))
            ok, fr = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, fr = cap.read()
            if ok and fr is not None:
                im = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                im.thumbnail((size, size))
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                im.save(fp, quality=82)
                img = fp
        except Exception:
            pass
        finally:
            cap.release()
    try:
        os.makedirs(os.path.dirname(info), exist_ok=True)
        with open(info, "w", encoding="utf-8") as f:
            f.write(f"{dur:.1f}" if dur else "")
    except OSError:
        pass
    return img, dur


def photo_thumb(path, size=360):
    """Pamje e vogël e fotos së plotë (pa prerje), e ruajtur në disk."""
    import hashlib

    try:
        m = int(os.path.getmtime(path))
    except OSError:
        return None
    key = hashlib.md5(f"{path}|{m}|{size}".encode()).hexdigest()
    fp = os.path.join(PHOTO_THUMBS, key[:2], key + ".jpg")
    if os.path.exists(fp):
        return fp
    try:
        with Image.open(path) as im:
            im.draft("RGB", (size * 2, size * 2))
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((size, size))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            im.save(fp, quality=82)
            return fp
    except Exception:
        return None


def face_thumb(path, box, size=96, square=False):
    """Kthen shtegun e një pamjeje të vogël të fytyrës (ruhet në disk, herën e dytë del menjëherë).
    square=True: katror size×size me fytyrën në mes (për dritaret e vogla të personave)."""
    import hashlib

    key = hashlib.md5(f"{path}|{tuple(round(float(b), 5) for b in box)}|{size}{'|sq2' if square else ''}"
                      .encode()).hexdigest()
    fp = os.path.join(THUMBS, key[:2], key + ".jpg")
    if os.path.exists(fp):
        return fp
    try:
        with Image.open(path) as im:
            im.draft("RGB", (1400, 1400))  # JPEG: lexo të zvogëluar, shumë më shpejt
            im = ImageOps.exif_transpose(im).convert("RGB")
            x, y, w, h = box[0] * im.width, box[1] * im.height, box[2] * im.width, box[3] * im.height
            if square:
                side = min(max(w, h) * 1.45, im.width, im.height)  # e ngushtë: të mos duket fqinji
                left = min(max(0, x + w / 2 - side / 2), im.width - side)
                top = min(max(0, y + h / 2 - side / 2), im.height - side)
                c = im.crop((int(left), int(top), int(left + side), int(top + side))).resize((size, size), Image.LANCZOS)
            else:
                pad = int(max(w, h) * 0.35)
                c = im.crop((int(max(0, x - pad)), int(max(0, y - pad)), int(x + w + pad), int(y + h + pad)))
                c.thumbnail((size, size))
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            c.save(fp, quality=85)
            return fp
    except Exception:
        return None
