"""Faqja · Databaza: të gjithë personat në një vend.

Skeda "Me foto": personat që AI-ja gjeti në foto (tabelë + karta djathtas). Skeda "Pa foto": personat e shtuar me
dorë (vetëm te pema, p.sh. gjyshërit). "Shto person" shton një person të ri (edhe me një lidhje te pema).
"""
import streamlit as st

import ui
from ui import ss

ai = ui.ai
try:
    import pema

    pema = ui.fresh(pema) if hasattr(ui, "fresh") else pema
except Exception:  # pema mungon: vetëm skeda "Me foto"
    pema = None

SEX = {"—": "", "Mashkull": "m", "Femër": "f"}


# ---------------- shto person ----------------
@st.dialog("Shto person", width="large")
def add_person_dialog():
    d = pema.load()
    names = pema.all_names(d, pema.face_names() | set(pema.load_index()))
    st.caption("Për dikë që nuk del në foto (p.sh. stërgjyshi) ose që AI-ja s'e ka gjetur ende. Ruhet te pema; "
               "po ta lidhësh me dikë, del menjëherë në vendin e duhur.")
    c1, c2 = st.columns([3, 2])
    name = c1.text_input("Emri", key="dbn_name", placeholder="p.sh. Hasan")
    c2.radio("Gjinia", list(SEX), key="dbn_sex", horizontal=True,
             help="Nga gjinia varen emërtimet: babai/nëna, xhaxhai/halla...")
    c3, c4 = st.columns(2)
    c3.text_input("Viti i lindjes (opsional)", key="dbn_lin")
    c4.text_input("Viti i vdekjes (opsional)", key="dbn_vdk")
    st.text_area("Shënim (opsional)", key="dbn_shen", height=68)
    st.markdown("**Lidhja** :gray[(opsionale; mund ta shtosh edhe më vonë te Pema)]")
    r1, r2 = st.columns(2)
    rel = r1.selectbox("është", list(pema.CHOICES), index=None, key="dbn_rel", placeholder="babai, gjyshi, shok...",
                       format_func=lambda c: f"{c} · {pema.HINT[c]}" if c in pema.HINT else c)
    who = r2.selectbox("i/e", names, index=None, key="dbn_who", placeholder="Zgjidh personin...")
    lloji = pema.CHOICES[rel][0] if rel else None
    if lloji in ("kusheri", "xhaxha_partner"):
        st.info("Për kushërinjtë dhe bashkëshortët e xhaxhallarëve përdor **Pema → Shto lidhje**: aty zgjedh edhe "
                "prindin e kushëririt.", icon=":material/info:")
    clean = " ".join((name or "").split())
    exists = clean and clean.casefold() in {n.casefold() for n in names}
    if exists:
        st.warning(f"**{clean}** ekziston tashmë. Gjeje te tabela dhe ndryshoje atje.", icon=":material/info:")
    ok = clean and not exists and not (rel and not who) and lloji not in ("kusheri", "xhaxha_partner")
    if st.button("Shto", icon=":material/person_add:", type="primary", disabled=not ok, width="stretch"):
        d = pema.load()
        try:
            if rel:
                pema.add_relation(d, clean, rel, who, names=names)
        except ValueError as e:
            st.error(str(e), icon=":material/error:")
            return
        pema.set_person(d, clean, gjinia=SEX[ss.get("dbn_sex", "—")] or pema.sex(d, clean),
                        lindja=(ss.get("dbn_lin") or "").strip(), vdekja=(ss.get("dbn_vdk") or "").strip(),
                        shenim=(ss.get("dbn_shen") or "").strip(), kontakt=False)
        pema.save(d)
        for k in ("dbn_name", "dbn_sex", "dbn_lin", "dbn_vdk", "dbn_shen", "dbn_rel", "dbn_who"):
            ss.pop(k, None)
        ss.dbp_sel, ss.db_tab_pa = clean, True
        st.toast(f"U shtua: {clean}", icon=":material/check_circle:")
        st.rerun()


# ---------------- personat pa foto ----------------
def save_nophoto(p):
    d = pema.load()
    pema.set_person(d, p, gjinia=SEX[ss[f"dbp_g_{p}"]], lindja=ss[f"dbp_lin_{p}"].strip(),
                    vdekja=ss[f"dbp_vdk_{p}"].strip(), shenim=ss[f"dbp_shen_{p}"].strip(), kontakt=ss[f"dbp_kon_{p}"])
    pema.save(d)
    st.toast(f"U ruajt: {p}", icon=":material/check_circle:")


def rename_nophoto(p):
    new = " ".join((ss.get(f"dbp_new_{p}") or "").split())
    d = pema.load()
    try:
        pema.rename(d, p, new)
    except ValueError as e:
        ss.dbp_msg = str(e)
        return
    pema.save(d)
    ss.dbp_sel = new


def delete_nophoto(p):
    d = pema.load()
    pema.delete_person(d, p)
    pema.save(d)
    ss.dbp_sel = None


def nophoto_tab(q):
    d = pema.load()
    faces = pema.face_names() | set(pema.load_index())
    rows = sorted((n for n in pema.in_tree(d) - faces if not n.startswith(pema.VIRTUAL)), key=str.casefold)
    t = q.strip().casefold()
    rows = [n for n in rows if not t or t in n.casefold()]
    if not rows:
        st.info("Asnjë person pa foto" + (" për këtë kërkim." if t else ". Shto me **Shto person**."),
                icon=":material/person_off:")
        return
    une = d.get("une", "")
    g = pema.graph(d)
    import pandas as pd

    table = [{"Emri": n, "Gjinia": {"m": "M", "f": "F"}.get(pema.sex(d, n), ""),
              "Te pema": ("ti" if n == une else pema.kinship(d, une, n, g)) if une else "",
              "Vitet": pema.years(d, n), "Lidhje": sum(n in (lk["a"], lk["b"]) for lk in d["links"]),
              "Shënim": pema.person(d, n).get("shenim", "")} for n in rows]
    left, right = st.columns([3, 2], gap="medium")
    with left:
        ev = st.dataframe(pd.DataFrame(table), key="dbp_tab", hide_index=True, on_select="rerun",
                          selection_mode="single-row", width="stretch", height=min(640, 36 * len(rows) + 40),
                          column_config={"Lidhje": st.column_config.NumberColumn(width=70),
                                         "Gjinia": st.column_config.TextColumn(width=60)})
    if ev is not None and ev.selection and ev.selection.rows:
        ss.dbp_sel = rows[ev.selection.rows[0]]
    p = ss.get("dbp_sel")
    with right:
        if p not in rows:
            with st.container(border=True):
                st.markdown("#### :material/touch_app: Zgjidh një person")
                st.caption("Kliko një rresht: këtu ndryshon emrin, gjininë, vitet, shënimin dhe sheh lidhjet.")
            return
        rec = pema.person(d, p)
        with st.container(border=True):
            st.markdown(f"#### :material/person: {p}")
            kin = ("ti" if p == une else pema.kinship(d, une, p, g)) if une else ""
            st.caption("Pa foto (i shtuar me dorë)" + (f" · për {une}: **{kin}**" if kin else ""))
            msg = ss.pop("dbp_msg", None)
            if msg:
                st.error(msg, icon=":material/error:")
            c1, c2, c3 = st.columns(3)
            c1.radio("Gjinia", list(SEX), index={"": 0, "m": 1, "f": 2}.get(rec.get("gjinia", ""), 0),
                     key=f"dbp_g_{p}", horizontal=True)
            c2.text_input("Viti i lindjes", rec.get("lindja", ""), key=f"dbp_lin_{p}")
            c3.text_input("Viti i vdekjes", rec.get("vdekja", ""), key=f"dbp_vdk_{p}")
            st.toggle("Kam kontakt me të", pema.is_contact(d, p), key=f"dbp_kon_{p}")
            st.text_area("Shënim", rec.get("shenim", ""), key=f"dbp_shen_{p}", height=68)
            b1, b2 = st.columns(2)
            b1.button("Ruaj", icon=":material/save:", type="primary", key=f"dbp_save_{p}", on_click=save_nophoto,
                      args=(p,), width="stretch")
            if b2.button("Hape te Pema", icon=":material/open_in_new:", key=f"dbp_tree_{p}", width="stretch"):
                ss.pema_qendra, ss.pema_menu, ss.pema_menu_open = p, p, True
                st.switch_page(ui.PAGES["pema"])
            der = pema.derived(d, p, g)
            if der:
                st.markdown("**:material/account_tree: Lidhjet**")
                art = pema._w("i", "e", "i/e", pema.sex(d, p))
                for w, others in der[:8]:
                    st.caption(f":material/link: **{w.split(' · ')[0]}** {art} " + ", ".join(others[:6])
                               + (f" +{len(others) - 6}" if len(others) > 6 else ""))
            else:
                st.caption("Ende pa lidhje: **Hape te Pema** → *Lidh me dikë*.")
            with st.expander(":material/edit: Riemërto ose hiq"):
                st.text_input("Emër i ri (ose emri i dikujt që ka foto, për t'i bashkuar)", key=f"dbp_new_{p}")
                st.button("Riemërto", icon=":material/edit:", key=f"dbp_ren_{p}", on_click=rename_nophoto, args=(p,),
                          disabled=not (ss.get(f"dbp_new_{p}") or "").strip())
                sure = st.checkbox(f"Po, hiqe {p} dhe lidhjet e tij/saj nga pema", key=f"dbp_sure_{p}")
                st.button("Hiqe", icon=":material/delete:", key=f"dbp_del_{p}", disabled=not sure,
                          on_click=delete_nophoto, args=(p,))


# ---------------- faqja ----------------
h1, h2 = st.columns([5, 1.4], vertical_alignment="bottom")
with h1:
    ui.header("Databaza e personave", "Të gjithë personat në një vend: me foto dhe pa foto. Kliko një rresht dhe "
              "ndrysho gjithçka te karta djathtas.", ":material/table_rows:")
if pema is not None and h2.button("Shto person", icon=":material/person_add:", type="primary", width="stretch",
                                  key="db_add", help="Shto dikë të ri (edhe pa foto), me një lidhje te pema"):
    add_person_dialog()

q = st.text_input("Kërko", key="db_q", placeholder="Kërko emrin ose numrin e personit...", icon=":material/search:",
                  label_visibility="collapsed")
has_scan = bool(ss.get("records") and ss.get("groups"))
n_nophoto = 0
if pema is not None:
    _d = pema.load()
    n_nophoto = len({n for n in pema.in_tree(_d) if not n.startswith(pema.VIRTUAL)}
                    - pema.face_names() - set(pema.load_index()))
labels = [":material/photo_library: Me foto", ":material/person_off: Pa foto"]
if ss.pop("db_tab_pa", False) or ss.get("db_tab_choice") not in labels:  # pas "Shto person": te "Pa foto"
    ss.db_tab_choice = labels[1] if ("dbp_sel" in ss or not has_scan) else labels[0]
s1, s2 = st.columns([2, 5], vertical_alignment="center")
tab = s1.segmented_control("Skeda", labels, key="db_tab_choice", required=True, label_visibility="collapsed")
s2.caption(f"**{n_nophoto}** persona pa foto (të shtuar me dorë, vetëm te pema)")

if tab == labels[1]:
    if pema is None:
        st.info("Pema nuk u ngarkua.")
    else:
        nophoto_tab(q)
else:
    if not ss.get("records"):
        ui.no_scan_yet("Personat me foto dalin pasi të skanosh (me opsionin **Personat (AI)**), ose pasi të hapësh "
                       "një skanim të ruajtur. Personat pa foto i sheh te skeda **Pa foto**.")
        st.stop()
    if not ss.get("groups"):
        st.info("Ky skanim nuk ka persona.", icon=":material/face_retouching_off:")
        st.stop()
    persons = ui.prepare_people()
    n_named = sum(1 for r in persons if ss.names.get(r, "").strip())
    c2, c3 = st.columns([1.4, 3.6], vertical_alignment="center")
    who = c2.segmented_control("Kush", ["Me emër", "Pa emër", "Të gjithë"], default="Të gjithë", key="db_who",
                               required=True, label_visibility="collapsed")
    c3.progress(n_named / max(1, len(persons)), text=f"**{n_named}** nga {len(persons)} kanë emër")

    def keep(r):
        name = ss.names.get(r, "").strip()
        if (who == "Me emër" and not name) or (who == "Pa emër" and name):
            return False
        t = q.strip().casefold()
        return not t or t in name.casefold() or t == str(r + 1)

    pool = sorted(persons, key=lambda r: (not ss.names.get(r, "").strip(), persons.index(r)))
    ui.person_db([r for r in pool if keep(r)])
err = ss.pop("save_err", None)
if err:
    st.error(err, icon=":material/error:")
