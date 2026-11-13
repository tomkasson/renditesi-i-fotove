"""Renditësi i Fotove: hyrja e aplikacionit (Streamlit) dhe shiriti i navigimit lart.

Faqet: Skano → Personat → Rendit (faqet/), plus 🌳 Pema (faqet/pema_lidhjet.py). Pjesët e përbashkëta janë te ui.py;
logjika pa ndërfaqe te core.py, ai.py, historiku.py, pema.py.
"""
import importlib
import os
import sys

import streamlit as st

import ui


def _fresh(m):
    """Si ui.fresh: rilexo modulin kur skedari ka ndryshuar pas ngarkimit (pa rinisur serverin)."""
    try:
        if os.path.getmtime(m.__file__) > getattr(m, "_LOADED", 0):
            return importlib.reload(m)
    except Exception:
        pass
    return m


ui = _fresh(ui)
for _name in ("core", "historiku", "ai", "pema", "report"):  # reload i ndryshon në vend: ui.core etj. mbeten të sakta
    if _name in sys.modules:
        _fresh(sys.modules[_name])

st.set_page_config(page_title="Renditësi i Fotove", page_icon=":material/photo_library:", layout="wide")
ui.init_state()
# më pak hapësirë bosh mbi titull (shiriti lart e zë tashmë vendin e kokës së faqes)
st.html("<style>[data-testid='stMainBlockContainer']{padding-top:3.25rem;padding-bottom:3rem}</style>")

ss = st.session_state
n_people = len({ui.root(g["id"]) for g in ss.groups}) if ss.get("groups") and "owner" in ss else (
    len(ss.groups) if ss.get("groups") else 0)
pages = [
    st.Page("faqet/skano.py", title="Skano", icon=":material/search:", url_path="skano", default=True),
    st.Page("faqet/personat.py", title="Personat" + (f" · {n_people}" if n_people else ""),
            icon=":material/groups:", url_path="personat"),
    st.Page("faqet/databaza.py", title="Databaza", icon=":material/table_rows:", url_path="databaza"),
    st.Page("faqet/rendit.py", title="Rendit", icon=":material/folder_copy:", url_path="rendit"),
    st.Page("faqet/pema_lidhjet.py", title="Pema", icon=":material/account_tree:", url_path="pema"),
]
st.navigation(pages, position="top").run()
