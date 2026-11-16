"""Faqja 2 · Personat: kush janë fytyrat e gjetura (emrat, bashkimet, korrigjimet) + databaza e të gjithëve."""
import streamlit as st

import ui
from ui import ss

ai = ui.ai

HELP = """
**Si funksionon**
- AI-ja i grupon fytyrat: çdo kartë është një person, edhe kur del vetëm në 1 foto. Më të shpeshtët dalin të parët.
- **Sa foto ka** (butonat nën shirit): shiko vetëm personat që dalin në 1 foto, 2, 3–5... Kliko përsëri = të gjithë.
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
    st.info("Ky skanim nuk ka persona: ose u bë pa **Personat (AI)**, ose nuk u gjet asnjë fytyrë e qartë.",
            icon=":material/face_retouching_off:")
    ui.next_step("Vazhdo: Rendit", "rendit")
    st.stop()

persons = ui.visible(ui.prepare_people())  # pa ata që u fshehën ("nuk e njoh / s'më duhet")
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
        st.slider("Sa persona të shfaq dhe përfshi", 1, len(groups), min(len(groups), 30), key="show_n",
                  persist_state="session",
                  help="Fotot e personave që nuk shfaqen shkojnë te 'Të tjerë'. Ata me emër shfaqen gjithmonë.")
with t5.popover("", icon=":material/help:", width="stretch", help="Si funksionon?"):
    st.markdown(HELP)
shown = ui.shown_persons(persons)
lost = ui.homeless()

# ----- filtri sipas numrit të fotove: personat që dalin 1 herë, 2 herë, 3-5... -----
BUCKETS = {"1 foto": (1, 1), "2 foto": (2, 2), "3–5": (3, 5), "6–20": (6, 20), "21+": (21, 10 ** 9)}
nphotos = ss.get("pcount") or {r: len(ui.person_paths(r)) for r in persons}  # nga prepare_people
bcount = {b: sum(1 for r in persons if lo <= nphotos.get(r, 0) <= hi) for b, (lo, hi) in BUCKETS.items()}
if ss.get("photo_bucket") not in BUCKETS:
    ss.pop("photo_bucket", None)
bucket = st.pills("Sa foto ka", list(BUCKETS), key="photo_bucket", persist_state="session",
                  format_func=lambda b: f"{b} · {bcount[b]}", label_visibility="collapsed",
                  help="Shfaq vetëm personat që dalin në kaq foto (p.sh. '1 foto' = ata që dalin vetëm një herë). "
                       "Kliko përsëri për t'i parë të gjithë.")
if bucket:  # filtri kalon mbi të gjithë personat, jo vetëm sa shfaqen ("Sa")
    lo, hi = BUCKETS[bucket]
    shown = [r for r in persons if lo <= nphotos.get(r, 0) <= hi]
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
    base = shown if bucket else persons
    pos = {r: i for i, r in enumerate(persons)}
    pool = sorted(base, key=lambda r: (not ss.names.get(r, "").strip(), pos[r]))
    ui.person_db([r for r in pool if keep(r, pool)])
else:
    # "Vetëm pa emër" dhe kërkimi kalojnë mbi TË GJITHË personat (si filtri "Sa foto ka"), jo vetëm mbi të parët e
    # "Sa": përndryshe, kur të parët kanë të gjithë emër, "Vetëm pa emër" nuk tregonte asgjë.
    base = persons if (only or q.strip()) and not bucket else shown
    tiles = [r for r in base if keep(r, base)]
    (ui.person_cards if view == ui.VIEW_CARDS else ui.person_grid)(tiles)

ui.prewarm(shown)  # pamjet e fytyrave për "Të gjitha fotot" përgatiten në sfond: hapja e parë s'pret diskun

err = ss.pop("save_err", None)
if err:
    st.error(err, icon=":material/error:")

hid = sorted(ss.get("hidden") or set(), key=lambda r: -len(ui.person_paths(r)))
if hid:
    with st.expander(f":material/visibility_off: Të fshehur · {len(hid)} persona që s'i njeh ose s'të duhen"):
        st.caption("Nuk dalin te lista dhe nuk marrin dosje (fotot e tyre shkojnë te 'Të tjerë'). Mbahen mend edhe në "
                   "skanimet e tjera. **Ktheje** nëse e fshehe gabimisht.")
        thumbs = {r: (ai.face_thumb(*c, size=120, square=True) if (c := ui.cover(r)) else None) for r in hid[:42]}
        for i in range(0, min(len(hid), 42), 7):
            cols = st.columns(7, gap="small")
            for col, r in zip(cols, hid[i:i + 7]):
                with col.container(border=True, gap="small"):
                    if thumbs.get(r):
                        st.image(thumbs[r], width="stretch")
                    st.caption(f"{len(ui.person_paths(r))} foto")
                    st.button("Ktheje", icon=":material/visibility:", key=ui.gk(f"unhide_{r}"), on_click=ui._unhide,
                              args=(r,), width="stretch")
        if len(hid) > 42:
            st.caption(f"... dhe {len(hid) - 42} të tjerë.")

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
