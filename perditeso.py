"""Përditësimi nga GitHub: merret VETËM kodi; të dhënat e përdoruesit (te paths.DATA) nuk preken kurrë.

versioni.json: {"nr": numri i versionit, "versioni": "data", "repo": "pronari/emri", "dega": "main"}.
Kontrolli lexon versioni.json nga GitHub-i; përditësimi shkarkon zip-in e degës dhe zëvendëson skedarët e kodit.
Asnjë foto apo e dhënë personale nuk dërgohet: vetëm një kërkesë për skedarët publikë të kodit.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
VFILE = os.path.join(HERE, "versioni.json")
KEEP = {".venv", ".git", "cache", "__pycache__", ".streamlit_secrets"}  # nuk preken kurrë nga përditësimi
TIMEOUT = 20


def local():
    try:
        with open(VFILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"nr": 0, "versioni": "?", "repo": "", "dega": "main"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "RenditesiFotove"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def remote(v=None):
    """versioni.json në GitHub, ose None (pa internet / pa repo)."""
    v = v or local()
    if not v.get("repo"):
        return None
    url = f"https://raw.githubusercontent.com/{v['repo']}/{v.get('dega', 'main')}/versioni.json"
    try:
        return json.loads(_get(url).decode("utf-8"))
    except Exception:
        return None


def check():
    """(ka_të_re, versioni_lokal, versioni_në_github ose None)."""
    v = local()
    r = remote(v)
    return (r is not None and int(r.get("nr", 0)) > int(v.get("nr", 0))), v, r


def apply(log=print):
    """Shkarkon kodin e ri dhe zëvendëson skedarët; nëse ndryshuan libraritë, i instalon. Kthen (ok, mesazhi)."""
    v = local()
    if not v.get("repo"):
        return False, "Nuk është caktuar ende vendi i përditësimeve (repo) te versioni.json."
    url = f"https://codeload.github.com/{v['repo']}/zip/refs/heads/{v.get('dega', 'main')}"
    try:
        data = _get(url)
    except Exception as e:
        return False, f"Shkarkimi dështoi (ka internet?): {e}"
    old_req = _read(os.path.join(HERE, "requirements.txt"))
    tmp = tempfile.mkdtemp(prefix="renditesi_")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tmp)
        roots = [os.path.join(tmp, d) for d in os.listdir(tmp)]
        src = roots[0] if len(roots) == 1 and os.path.isdir(roots[0]) else tmp
        n = 0
        for dirpath, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in KEEP]
            rel = os.path.relpath(dirpath, src)
            dst_dir = HERE if rel == "." else os.path.join(HERE, rel)
            os.makedirs(dst_dir, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(dirpath, f), os.path.join(dst_dir, f))
                n += 1
        log(f"U zëvendësuan {n} skedarë kodi.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if _read(os.path.join(HERE, "requirements.txt")) != old_req:
        log("Po instaloj libraritë e reja (mund të zgjasë disa minuta)...")
        r = subprocess.run([_python(), "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")],
                           capture_output=True, text=True, creationflags=0x08000000)
        if r.returncode != 0:
            return False, "Kodi u përditësua, por libraritë jo:\n" + (r.stderr or r.stdout)[-1500:]
    nv = local()
    return True, f"U përditësua në versionin {nv.get('versioni')} (nr. {nv.get('nr')})."


def _read(p):
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _python():
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-5] + ".exe"
    return exe


if __name__ == "__main__":  # nga komanda: python perditeso.py
    has, v, r = check()
    print("Versioni këtu:", v.get("versioni"), "| në GitHub:", (r or {}).get("versioni", "?"))
    if has:
        print(apply()[1])
