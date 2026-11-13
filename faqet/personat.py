"""Faqja 2 · Personat: kush janë fytyrat e gjetura (emrat, bashkimet, korrigjimet) + databaza e të gjithëve."""
import streamlit as st

import ui
from ui import ss

ai = ui.ai

HELP = """
**Si funksionon**
- AI-ja i grupon fytyrat: çdo kartë është një person (në të paktën disa foto). Më të shpeshtët dalin të parët.
- **Shkruaj emrin** te karta. I njëjti emër te dy karta i **bashkon**. Emri ruhet vetë dhe njihet në çdo skanim.
- AI-ja shpesh e ndan të njëjtin person në disa grupe (mosha, syze, dritë): :material/person_search: **Gjej** i
  gjen dhe i bashkon. Numri te butoni = sa grupe ngjajnë shumë.
- :material/photo_library: **Fotot**: kontrollo dhe hiq me ❌ ato që s'janë ky person. Shkojnë te *Fotot pa vend*.
- **Databaza**: të gjithë në një tabelë. Kliko një rresht: djathtas ndryshon emrin, gjininë, përfshirjen, fotot,
  pjesët dhe lidhjet me pemën.
"""

if not ss.get("records"):
    ui.header("Personat", "Këtu i jep emër fytyrave që gjen AI-ja.", ":material/groups:")
    ui.no_scan_yet("Personat dalin pasi të skanosh (me opsionin **Personat (AI)**), ose pasi të hapësh një skanim "
                   "të ruajtur.")
    st.stop()
groups = ss.get("groups")
if not groups:
    ui.header("Personat", None, ":material/groups:")
    st.info("Ky skanim nuk ka persona: ose u bë pa **Personat (AI)**, ose asnjë fytyrë nuk del në më shumë se "
            "një foto.", icon=":material/face_retouching_off:")
    ui.next_step("Vazhdo: Rendit", "rendit")
    st.stop()

persons = ui.prepare_people()
n_named = sum(1 for r in persons if ss.names.get(r, "").strip())

# ----- koka: titulli + përparimi -----
h1, h2 = st.columns([3, 2], vertical_alignment="bottom")
with h1:
    st.markdown("### :material/groups: Kush janë?")
    st.caption(f"{len(persons)} persona të gjetur në fotot e tua · shkruaj emrat e atyre që njeh")
with h2:
    st.progress(n_named / max(1, len(persons)), text=f"**{n_named}** nga {len(persons)} kanë emër")

# ----- shiriti i veglave -----
t1, t2, t3, t4, t5, t6 = st.columns([2.6, 2.4, 1.5, 1.2, 0.55, 1.9], vertical_alignment="center")
if ss.get("pview") not in (ui.VIEW_GRID, ui.VIEW_DB, ui.VIEW_CARDS):  # emri i vjetër "Të gjithë"
    ss.pop("pview", None)
view = t1.segmented_control("Pamja", [ui.VIEW_GRID, ui.VIEW_DB, ui.VIEW_CARDS], default=ui.VIEW_GRID, key="pview",
                            required=True, persist_state="session", label_visibility="collapsed")
q = t2.text_input("Kërko", key="people_q", placeholder="Kërko emrin...", icon=":material/search:",
                  label_visibility="collapsed")
only = t3.toggle("Vetëm pa emër", key="only_unnamed", persist_state="session",
                 help="Fshih personat që i ke emërtuar, që të shohësh vetëm ata që mbeten.")
with t4.popover("Sa", icon=":material/tune:", width="stretch", help="Sa persona të shfaqen"):
    if len(groups) > 1:
        if ss.get("show_n") and ss.show_n > len(groups):
            ss.show_n = len(groups)
        st.slider("Sa persona të shfaq dhe përfshi", 1, len(groups), min(len(persons), 30), key="show_n",
                  persist_state="session",
                  help="Fotot e personave që nuk shfaqen shkojnë te 'Të tjerë'. Ata me emër shfaqen gjithmonë.")
with t5.popover("", icon=":material/help:", width="stretch", help="Si funksionon?"):
    st.markdown(HELP)
shown = ui.shown_persons(persons)
lost = ui.homeless()
if t6.button(f"Fotot pa vend ({len(lost)})", icon=":material/inventory_2:", width="stretch", key="inbox_open",
             disabled=not lost, help="Fytyrat që i hoqe nga një person. AI-ja propozon kujt mund t'i përkasin; deri "
                                     "atëherë shkojnë te 'Të tjerë'."):
    ss.inbox_n = 48
    ui.inbox_dialog()


def keep(r, pool):
    """Filtri i përbashkët: kërkimi (emri ose 'Personi N') dhe 'vetëm pa emër'."""
    name = ss.names.get(r, "").strip()
    if only and name:
        return False
    if q.strip():
        t = q.strip().casefold()
        return t in name.casefold() or t == str(r + 1)
    return True


if view == ui.VIEW_DB:  # databaza: të gjithë personat (jo vetëm sa shfaqen), me emër të parët
    pool = sorted(persons, key=lambda r: (not ss.names.get(r, "").strip(), persons.index(r)))
    ui.person_db([r for r in pool if keep(r, pool)])
elif view == ui.VIEW_CARDS:
    ui.person_cards([r for r in shown if keep(r, shown)])
else:
    ui.person_grid([r for r in shown if keep(r, shown)])

err = ss.pop("save_err", None)
if err:
    st.error(err, icon=":material/error:")

known = ai.load_people()
with st.expander(f":material/bookmark: Kujtesa e emrave · {len(known)} emra"):
    st.caption("Emrat ruhen vetë në këtë kompjuter (`cache/personat.json`) dhe njihen në çdo skanim tjetër. "
               "Asgjë nuk dërgohet jashtë. Këtu janë edhe emrat që nuk dalin në këtë skanim.")
    st.markdown(" · ".join(f"**{n}** :gray[{len(vs)}]" for n, vs in sorted(known.items(), key=lambda x: x[0].casefold())))
    k1, k2, k3 = st.columns([2, 2, 1], vertical_alignment="bottom")
    fn = k1.selectbox("Harro një emër", sorted(known, key=str.casefold), index=None, key="forget_pick",
                      placeholder="Zgjidh emrin...")
    sure = k2.checkbox(f"Po, harroje {fn}" if fn else "Po, harroje", key="forget_sure", disabled=not fn)
    if k3.button("Harroje", icon=":material/delete:", key="forget_go", disabled=not (fn and sure), width="stretch"):
        ai.forget_name(fn)
        ss.pop("forget_pick", None)
        ss.pop("forget_sure", None)
        st.rerun()

ui.next_step("Vazhdo: Rendit", "rendit")
