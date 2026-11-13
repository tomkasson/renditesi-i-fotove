"""Ku ruhen të dhënat e përdoruesit (emrat, pema, korrigjimet, skanimet, pamjet e vogla).

Të dhënat mbahen VEÇ kodit, që përditësimi (kodi i ri nga GitHub) të mos i prekë kurrë:
    %LOCALAPPDATA%\\RenditesiFotove\\data   (ose RENDITESI_DATA, p.sh. për prova)
Herën e parë, nëse ekziston dosja e vjetër 'cache' pranë kodit, ajo kopjohet atje (origjinali mbetet si kopje).
Shtegu mbahet me shkronja ASCII: OpenCV nuk lexon dot shtigje me ë/ç.
"""
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_CACHE = os.path.join(HERE, "cache")
_base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
APP_HOME = os.path.join(_base, "RenditesiFotove")
DATA = os.environ.get("RENDITESI_DATA") or os.path.join(APP_HOME, "data")
_MARK = ".migruar"


def data(*parts):
    """Shtegu i një skedari/dosjeje te të dhënat e përdoruesit."""
    return os.path.join(DATA, *parts)


def ensure():
    """Krijon dosjen e të dhënave; herën e parë kopjon atje 'cache' e vjetër (pa e fshirë)."""
    os.makedirs(DATA, exist_ok=True)
    if os.environ.get("RENDITESI_DATA") or os.path.exists(os.path.join(DATA, _MARK)):
        return
    if os.path.isdir(OLD_CACHE) and os.path.abspath(OLD_CACHE) != os.path.abspath(DATA):
        for name in os.listdir(OLD_CACHE):
            src, dst = os.path.join(OLD_CACHE, name), os.path.join(DATA, name)
            if os.path.exists(dst):
                continue
            try:
                (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
            except OSError:
                pass
    with open(os.path.join(DATA, _MARK), "w", encoding="utf-8") as f:
        f.write(f"Kopjuar nga {OLD_CACHE}\n" if os.path.isdir(OLD_CACHE) else "E re\n")


ensure()
