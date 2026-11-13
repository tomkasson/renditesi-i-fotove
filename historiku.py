"""Historiku i skanimeve: çdo skanim ruhet i plotë (fotot, datat, fytyrat, grupet) te cache/skanimet/,
që të rihapet menjëherë, pa kaluar diskun dhe pa lexuar fotot përsëri.

historiku.json mban vetëm përmbledhjet (për listën); rezultatet e plota janë te <id>.pkl.
Një skanim i ri i të njëjtave dosje me të njëjtat opsione zëvendëson të vjetrin; mbahen KEEP më të fundit.
"""
import datetime as dt
import json
import os
import pickle
import time as _time

_LOADED = _time.time()  # app.py e krahason me datën e skedarit: rilexon modulin kur ndryshon

HERE = os.path.dirname(os.path.abspath(__file__))
import paths  # noqa: E402

DIR = os.environ.get("RENDITESI_HISTORIKU") or paths.data("skanimet")  # për prova
KEEP = 5


def _index_path():
    return os.path.join(DIR, "historiku.json")


def items():
    """Përmbledhjet e skanimeve të ruajtura, më i riu së pari."""
    try:
        with open(_index_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return [i for i in data if os.path.exists(os.path.join(DIR, i["id"] + ".pkl"))]


def _write_index(data):
    os.makedirs(DIR, exist_ok=True)
    tmp = _index_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _index_path())


def _same(a, b):
    keys = ("dosjet", "min_kb", "videot", "permbajtja", "personat")
    norm = lambda i: [sorted(os.path.normcase(d) for d in i.get("dosjet", []))] + [i.get(k) for k in keys[1:]]  # noqa: E731
    return norm(a) == norm(b)


def save(records, groups, report, info):
    """Ruan një skanim. info: {dosjet: [...], dalja, min_kb, videot, permbajtja, personat}. Kthen id-në."""
    os.makedirs(DIR, exist_ok=True)
    now = dt.datetime.now()
    sid = now.strftime("%Y%m%d-%H%M%S-%f")
    path = os.path.join(DIR, sid + ".pkl")
    with open(path + ".tmp", "wb") as f:
        pickle.dump({"records": records, "groups": groups, "report": report}, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(path + ".tmp", path)
    info = dict(info, id=sid, koha=now.strftime("%d.%m.%Y %H:%M"),
                gjithsej=len(records), foto=sum(r["kind"] == "foto" for r in records),
                video=sum(r["kind"] == "video" for r in records), grupe=len(groups or []),
                mb=round(os.path.getsize(path) / 2 ** 20, 1))
    old = items()
    keep = [info] + [i for i in old if not _same(i, info)]
    for i in keep[KEEP:] + [i for i in old if _same(i, info)]:
        delete_file(i["id"])
    _write_index(keep[:KEEP])
    return sid


def load(sid):
    """(info, records, groups, report) i një skanimi të ruajtur."""
    info = next((i for i in items() if i["id"] == sid), None)
    if info is None:
        raise FileNotFoundError("Ky skanim nuk është më në historik.")
    with open(os.path.join(DIR, sid + ".pkl"), "rb") as f:
        data = pickle.load(f)
    return info, data["records"], data["groups"], data.get("report") or {}


def delete_file(sid):
    try:
        os.remove(os.path.join(DIR, sid + ".pkl"))
    except OSError:
        pass


def delete(sid):
    delete_file(sid)
    _write_index([i for i in items() if i["id"] != sid])
