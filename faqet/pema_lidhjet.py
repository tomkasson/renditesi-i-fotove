"""🌳 Pema e lidhjeve: familja (sa breza të duash) dhe lidhjet e tjera (shoqëria, shkolla, puna...)."""
import base64
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dosja e aplikacionit
import pema  # noqa: E402
import pema_komponentet as kmp  # noqa: E402


def fresh(m):
    """Si te app.py: rilexo modulin kur skedari ka ndryshuar pas ngarkimit (pa rinisur serverin)."""
    import importlib

    try:
        if os.path.getmtime(m.__file__) > getattr(m, "_LOADED", 0):
            return importlib.reload(m)
    except Exception:
        pass
    return m


pema = fresh(pema)
try:
    import ai  # pamjet e vogla të fytyrave dhe fotove (pa ngarkuar modelet)

    ai = fresh(ai)
except Exception:
    ai = None

ss = st.session_state
GAL_STEP = 24  # sa foto shfaqen njëherësh te galeria

FACES = pema.face_names()
INDEX = pema.load_index()
data = pema.load()
names = pema.all_names(data, FACES | set(INDEX))


@st.cache_data(max_entries=24, show_spinner="Po vizatoj pemën...")
def cached_layout(js, center, up, down, only, faces, version):
    """Rregullimi i pemës zgjat 1-2 s: llogaritet vetëm kur ndryshojnë të dhënat ose zgjedhjet (jo në çdo klikim)."""
    return pema.layout(json.loads(js), center, up, down, only, set(faces))


# ---------------- fotot ----------------
@st.cache_data(max_entries=5000, show_spinner=False)
def data_uri(fp):
    """Pamja e vogël (skedar .jpg te cache/) si 'data:' URI, që të futet direkt te faqja."""
    with open(fp, "rb") as f:
        return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()


def face_uris(names_):
    """{emri: fytyra si data URI} për personat që kanë fytyrë te indeksi."""
    todo = [(n, INDEX[n]["fytyra"]) for n in names_ if n in INDEX and INDEX[n]["fytyra"]]
    if not todo or ai is None:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda t: ai.face_thumb(t[1][0], t[1][1], size=96, square=True), todo))
    return {n: data_uri(fp) for (n, _), fp in zip(todo, res) if fp}


def open_photo(p, folder=False):
    """Hap foton origjinale (ose dosjen me foton të zgjedhur) në Windows."""
    if not os.path.exists(p):
        st.warning(f"Fotoja nuk gjendet më këtu: {p}")
        return
    if not os.environ.get("RENDITESI_NO_OPEN"):  # testet automatike nuk hapin dritare
        if folder:
            subprocess.Popen(f'explorer /select,"{os.path.normpath(p)}"')
        else:
            os.startfile(p)
    st.toast(("📁 U hap dosja e " if folder else "🖼️ U hap ") + os.path.basename(p))


def gallery(paths, who):
    """Rrjetë me foto: klikimi hap origjinalin, 📁 hap dosjen."""
    if not paths:
        st.caption("Asnjë foto.")
        return
    if ai is None:
        st.warning("Pamjet e fotove nuk krijohen dot (moduli ai mungon).")
        return
    n = ss.get("pema_gal_n", GAL_STEP)
    shown = paths[:n]
    with ThreadPoolExecutor(max_workers=8) as ex:
        thumbs = list(ex.map(lambda p: ai.photo_thumb(p, 240), shown))
    items = []
    for i, (p, t) in enumerate(zip(shown, thumbs)):
        if t:
            y = pema.photos(INDEX, who).get(p, "")
            items.append({"i": i, "src": data_uri(t), "cap": (f"{y} · " if y else "") + os.path.basename(p)})
    if len(items) < len(shown):
        st.caption(f"⚠️ {len(shown) - len(items)} foto nuk u gjetën më (u zhvendosën ose u fshinë?).")
    res = kmp.gallery(data={"items": items}, key="pema_galeria", on_open_change=lambda: None,
                      on_folder_change=lambda: None)
    for kind in ("open", "folder"):
        i = getattr(res, kind, None)
        if i is not None and 0 <= int(i) < len(shown):
            open_photo(shown[int(i)], folder=kind == "folder")
    if n < len(paths):
        st.button(f"⬇ Shfaq edhe {min(GAL_STEP, len(paths) - n)} ({n} nga {len(paths)})", key="pema_gal_more",
                  on_click=lambda: ss.update(pema_gal_n=n + GAL_STEP), width="stretch")


# ---------------- zgjedhja (klikimi te pema) ----------------
def select(name):
    """1 klikim: fotot e personit. Klikim te një i dytë: fotot ku janë bashkë. Klikim te i zgjedhuri: hiqe."""
    sel = list(ss.get("pema_sel", []))
    if name in sel:
        sel.remove(name)
    elif len(sel) == 1:
        sel.append(name)
    else:
        sel = [name]
    ss.pema_sel, ss.pema_gal_n = sel, GAL_STEP


def select_pair(a, b):
    ss.pema_sel, ss.pema_gal_n = [a, b], GAL_STEP


# ---------------- veprimet (thirren para se të vizatohet faqja) ----------------
def _say(kind, text):
    ss.pema_msg = (kind, text)


def set_center(name):
    ss.pema_qendra = name


def set_me():
    d = pema.load()
    d["une"] = pema.canon(ss.pema_une, names)
    d["persons"].setdefault(d["une"], {})
    pema.save(d)
    ss.pema_qendra = d["une"]


def open_add(x=None, rel=None, y=None, replace=None):
    """Hap dritaren "Shto lidhje", e plotësuar paraprakisht (p.sh. nga butonat e shpejtë ose nga sugjerimet).
    replace = një lidhje ekzistuese që zëvendësohet me të renë (butoni "Ndrysho")."""
    ss.pema_dx, ss.pema_drel, ss.pema_dy = x, rel, y
    ss.pema_droli, ss.pema_dku, ss.pema_dvia, ss.pema_dvk = "", None, None, None
    ss.pema_drep = replace
    ss.pema_dialog = True
    ss.pema_close = True  # nëse thirret nga dritarja e personit: mbylle atë, që të hapet kjo


@st.dialog("Shto lidhje", width="large")
def add_dialog():
    rep = ss.get("pema_drep")
    if rep:
        st.info(f"Po ndryshon lidhjen **{pema.link_text(data, rep)}**. Zgjidh si është saktë dhe shtyp **Ruaj**: "
                "e vjetra zëvendësohet.", icon=":material/edit:")
    st.caption("Shkruaje si fjali. Për dikë pa foto (p.sh. stërgjyshin) shkruaj emrin e ri në listë. "
               "Për gjyshërit, xhaxhain/hallën/dajën/tezen dhe kushërinjtë ka zgjedhje të gatshme.")
    y = ss.get("pema_dy") or center
    near = pema.companions(INDEX, y, limit=8)  # kush del më shpesh me 'y': së pari në listë
    order = sorted(names, key=lambda n: (-dict(near).get(n, 0), n.casefold()))
    if near:  # vetëm si tekst: etiketa brenda listës do të ruhej si emër
        st.caption(f"Më shpesh në foto me {y}: " + ", ".join(f"{n} ({k})" for n, k in near))
    c1, c2, c3 = st.columns(3)
    c1.selectbox("Personi", order, index=None, key="pema_dx", accept_new_options=True,
                 placeholder="Zgjidh ose shkruaj emrin...")
    c2.selectbox("është", list(pema.CHOICES), index=None, key="pema_drel", placeholder="babai, xhaxhai, shok...",
                 format_func=lambda c: f"{c} · {pema.HINT[c]}" if c in pema.HINT else c,
                 help="Familja ruhet me prind, partner, vëlla/motër; gjyshi, xhaxhai, kushëriri lidhen vetë nëpërmjet "
                      "babait ose nënës. Shokët, shkolla, puna dalin anash pemës.")
    c3.selectbox("i/e", names, key="pema_dy", accept_new_options=True, placeholder="Zgjidh ose shkruaj emrin...")
    choice = ss.get("pema_drel")
    lloji = pema.CHOICES[choice][0] if choice else None
    via = via_kind = None
    blocked = False
    if lloji in ("gjysh", "xhaxha"):
        side = pema.SIDE[choice]
        p = pema.parent_of(data, y, side)
        if p:
            st.caption(f":material/link: Lidhet nëpërmjet {'babait' if side == 'm' else 'nënës'}: **{p}**")
        else:
            blocked = True
            st.warning(f"Shto më parë {'babain' if side == 'm' else 'nënën'} e {y} (zgjidh 'Babai' ose 'Nëna'), "
                       "pastaj këtë.", icon=":material/info:")
    elif lloji in ("kusheri", "xhaxha_partner"):
        known = pema.uncles_aunts(data, y)
        implied = pema.SPOUSE_OF.get(choice)  # xhaxheshja → xhaxhai etj.
        k1, k2 = st.columns([1, 1])
        if lloji == "kusheri":
            lbl, ph = "Fëmijë i/e (prindi i kushëririt)", "Zgjidh ose shkruaj emrin e xhaxhait..."
            hlp = ("Prindi i kushëririt: xhaxhai, halla, daja ose tezja. Nëse s'është në listë, shkruaj emrin (ose p.sh. "
                   "'Xhaxhai i Arbenit') dhe zgjidh djathtas kush është.")
        else:
            lbl = f"Bashkëshort/e i/e ({implied.lower()} i/e {y})"
            ph = f"Zgjidh ose shkruaj emrin (edhe thjesht '{implied}')..."
            hlp = (f"Nëse {implied.lower()} nuk ka foto dhe s'është në pemë, shkruaj emrin e tij/saj (ose thjesht "
                   f"'{implied}'): shtohet vetë si vëlla/motër e {'babait' if implied in ('Xhaxhai', 'Halla') else 'nënës'}.")
        tree = pema.in_tree(data)
        rest = sorted((n for n in tree - {u for u, _ in known} - {y} if not n.startswith(pema.VIRTUAL)), key=str.casefold)
        via = k1.selectbox(lbl, [u for u, _ in known] + rest, index=None, key="pema_dvia", accept_new_options=True,
                           placeholder=ph, help=hlp + " Lista: së pari xhaxhallarët e " + y + ", pastaj gjithë pema.")
        if known:
            k1.caption(f"Xhaxhallarët e {y}: " + ", ".join(f"{u} ({r})" for u, r in known))
        via_c = pema.canon(via, names) if via else ""
        is_new = via and via_c not in [u for u, _ in known] and via_c not in tree
        x_now = ss.get("pema_dx")
        if via and not is_new and x_now and lloji == "kusheri":  # si do të dalë: provë mbi një kopje
            import copy

            d2 = copy.deepcopy(data)
            try:
                pema.add_link(d2, via_c, pema.canon(x_now, names), "prind")
                gx = pema.CHOICES[choice][1]
                if gx and not pema.sex(d2, pema.canon(x_now, names)):
                    pema.set_person(d2, pema.canon(x_now, names), gjinia=gx)
                k2.caption(f":material/visibility: **{x_now}** do të dalë fëmijë i {via_c} → për {y}: "
                           f"**{pema.kinship(d2, y, pema.canon(x_now, names)) or 'pa lidhje familjare'}**")
            except ValueError as e:
                k2.warning(str(e), icon=":material/error:")
        if is_new and lloji == "kusheri":
            via_kind = k2.segmented_control(f"{via} është", list(pema.UNCLE), key="pema_dvk",
                                            help="Kështu e lidh me babain ose nënën tënde në të njëjtin hap.")
            blocked = not via_kind
        elif is_new:
            side = pema.UNCLE[implied][1]
            if pema.parent_of(data, y, side):
                k2.caption(f":material/person_add: **{via}** nuk është në pemë: do të shtohet si {implied.lower()} "
                           f"(pa foto), dhe {ss.get('pema_dx') or 'ky person'} si bashkëshort/e e tij/saj.")
            else:
                blocked = True
                k2.warning(f"Shto më parë {'babain' if side == 'm' else 'nënën'} e {y}.", icon=":material/info:")
    if lloji in pema.OTHER:
        c4, c5 = st.columns(2)
        c4.text_input("Roli (opsional)", key="pema_droli",
                      placeholder="p.sh. shoqe klase, kumbarë, trajner..." if lloji != "puna" else "p.sh. koleg, shef, klient")
        kus = sorted({lk.get("ku", "") for lk in data["links"] if lk["lloji"] == lloji} - {""}, key=str.casefold)
        c5.selectbox("Ku? (opsional: shkolla, firma, lagjja...)", kus, index=None, key="pema_dku",
                     accept_new_options=True, placeholder="p.sh. Gjimnazi X, Firma Y")
    ok = ss.get("pema_dx") and ss.get("pema_drel") and ss.get("pema_dy") and not blocked
    if st.button("Ruaj" if rep else "Shto", icon=":material/save:" if rep else ":material/add:", type="primary",
                 disabled=not ok, width="stretch"):
        d = pema.load()
        if rep:  # e vjetra hiqet vetëm te kjo kopje; nëse e reja refuzohet, asgjë nuk ruhet
            pema.delete_link(d, rep)
        try:
            lk = pema.add_relation(d, ss.pema_dx, ss.pema_drel, ss.pema_dy, ss.get("pema_droli") or "",
                                   ss.get("pema_dku") or "", names=FACES, via=via, via_kind=via_kind)
        except ValueError as e:
            st.error(str(e), icon=":material/error:")
            return
        ss.pema_drep = None
        pema.save(d)
        st.toast(("U ndryshua: " if rep else "U shtua: ") + pema.link_text(d, lk), icon=":material/check_circle:")
        st.rerun()


SEXES = {"—": "", "Mashkull": "m", "Femër": "f"}


def save_person(p, k="pema"):
    d = pema.load()
    pema.set_person(d, p, gjinia=SEXES[ss[f"{k}_g_{p}"]], lindja=ss[f"{k}_lin_{p}"].strip(),
                    vdekja=ss[f"{k}_vdk_{p}"].strip(), kontakt=ss[f"{k}_kon_{p}"], shenim=ss[f"{k}_shen_{p}"].strip())
    pema.save(d)
    _say("success", f"✔ U ruajt: {p}")


def rename_cb(p, k="pema"):
    new = pema.canon(ss.get(f"{k}_new_{p}"), names)
    d = pema.load()
    try:
        pema.rename(d, p, new)
    except ValueError as e:
        _say("error", str(e))
        return
    pema.save(d)
    for key in ("pema_qendra", "pema_p", "pema_menu"):
        if ss.get(key) == p:
            ss[key] = new
    ss.pema_sel = [new if n == p else n for n in ss.get("pema_sel", [])]
    _say("success", f"✔ {p} → {new}")


def delete_person_cb(p):
    d = pema.load()
    pema.delete_person(d, p)
    pema.save(d)
    if ss.get("pema_qendra") == p:
        ss.pema_qendra = d["une"] or None
    ss.pema_sel = [n for n in ss.get("pema_sel", []) if n != p]
    ss.pema_close = True
    _say("success", f"🗑 {p} u hoq nga pema")


def person_form(p, k):
    """Të dhënat e personit (gjinia, vitet, kontakti, shënimi), riemërtimi dhe heqja. k = prapashtesa e çelësave."""
    rec = pema.person(pema.load(), p)
    c1, c2, c3 = st.columns(3)
    gi = {"": 0, "m": 1, "f": 2}.get(rec.get("gjinia", ""), 0)
    c1.radio("Gjinia", list(SEXES), index=gi, key=f"{k}_g_{p}", horizontal=True,
             help="Nga gjinia varen emërtimet: babai/nëna, xhaxhai/halla, kushëriri/kushërira...")
    c2.text_input("Viti i lindjes", rec.get("lindja", ""), key=f"{k}_lin_{p}")
    c3.text_input("Viti i vdekjes", rec.get("vdekja", ""), key=f"{k}_vdk_{p}")
    st.toggle("Kam kontakt me të", pema.is_contact(data, p, FACES), key=f"{k}_kon_{p}")
    st.text_area("Shënim", rec.get("shenim", ""), key=f"{k}_shen_{p}", height=80)
    st.button("Ruaj", icon=":material/save:", type="primary", on_click=save_person, args=(p, k), key=f"{k}_save_{p}")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.selectbox("Emër i ri, ose bashkoje me", [n for n in names if n != p], index=None,
                     key=f"{k}_new_{p}", accept_new_options=True, placeholder="Shkruaj emrin e ri...")
        st.caption("Bashkimi me një emër që ka foto (p.sh. 'Gjyshi' → 'Arben') i bashkon lidhjet."
                   + (" Ky emër vjen nga fotot: po ta ndryshosh këtu, karta nuk lidhet më me fytyrën."
                      if p in FACES else ""))
        st.button("Riemërto", icon=":material/edit:", on_click=rename_cb, args=(p, k), key=f"{k}_ren_{p}",
                  disabled=not ss.get(f"{k}_new_{p}"))
    with c2.container(border=True):
        sure = st.checkbox(f"Po, hiqe {p} dhe lidhjet e tij/saj nga pema", key=f"{k}_sure_{p}")
        st.caption("Fotot dhe emri te Renditësi nuk preken.")
        st.button("Hiqe nga pema", icon=":material/delete:", disabled=not sure, on_click=delete_person_cb, args=(p,),
                  key=f"{k}_del_{p}")


def set_sex_cb(p, g):
    d = pema.load()
    pema.set_person(d, p, gjinia=g)
    pema.save(d)
    for k in (f"pema_m_g_{p}", f"pema_g_{p}"):  # forma e editimit lexon vlerën e re
        ss.pop(k, None)


def show_photos(sel_):
    ss.pema_sel, ss.pema_gal_n, ss.pema_close = list(sel_), GAL_STEP, True


def center_cb(p):
    ss.pema_qendra, ss.pema_close = p, True


@st.dialog("Personi", width="large")
def person_dialog():
    """Hapet kur klikon një kartë: veprimet (lidh, fotot, qendra), editimi i të dhënave dhe i lidhjeve."""
    if ss.pop("pema_close", False):  # një veprim këtu kërkon faqen e plotë (p.sh. dritaren 'Shto lidhje')
        st.rerun()
    d = pema.load()
    p = ss.get("pema_menu")
    if not p or p not in pema.all_names(d, FACES | set(INDEX)):
        st.info("Ky person nuk është më te pema.")
        return
    nph = len(pema.photos(INDEX, p))
    kin = pema.kinship(d, center, p)
    sx = {"m": "mashkull", "f": "femër"}.get(pema.sex(d, p), "gjinia pa caktuar")
    h1, h2 = st.columns([1, 6], vertical_alignment="center")
    face = face_uris([p]).get(p)
    if face:
        h1.html(f'<img src="{face}" style="width:72px;height:72px;border-radius:50%;object-fit:cover">')
    h2.markdown(f"### {p}")
    h2.caption(" · ".join(x for x in (
        f"{kin} i/e {center}" if kin else ("qendra e pemës" if p == center else ""),
        f"{nph} foto" if nph else "pa foto", sx, pema.years(d, p)) if x))
    show_msg()
    if not pema.sex(d, p):  # pa gjini: emërtimet dalin "kushëri/e"; një klikim e rregullon
        gr = st.container(horizontal=True, vertical_alignment="center")
        gr.caption(f":material/info: Zgjidh gjininë e {p} që emërtimet të dalin saktë (kushëriri / kushërira):")
        gr.button("Mashkull", icon=":material/male:", key="pema_m_sx_m", on_click=set_sex_cb, args=(p, "m"))
        gr.button("Femër", icon=":material/female:", key="pema_m_sx_f", on_click=set_sex_cb, args=(p, "f"))
    mine = [lk for lk in d["links"] if p in (lk["a"], lk["b"])]
    der = pema.derived(d, p)
    t1, t2, t3 = st.tabs([":material/bolt: Veprime", ":material/edit: Edito",
                          f":material/link: Lidhjet ({sum(len(v) for _, v in der) or len(mine)})"])
    with t1:
        r = st.container(horizontal=True)
        r.button("Lidh me dikë", icon=":material/add_link:", type="primary", key="pema_m_link", on_click=open_add,
                 kwargs={"y": p}, help=f"Hap dritaren: [dikush] është [babai, shok, kolege...] i/e {p}")
        prev = [n for n in ss.get("pema_sel", []) if n != p][:1]
        if prev:
            r.button(f"Fotot bashkë me {prev[0]}", icon=":material/group:", key="pema_m_pair", on_click=show_photos,
                     args=([prev[0], p],))
        r.button("Shiko fotot", icon=":material/photo_library:", key="pema_m_ph", on_click=show_photos,
                 args=([p],), disabled=not nph)
        r.button("Bëje qendër", icon=":material/my_location:", key="pema_m_c", on_click=center_cb, args=(p,),
                 disabled=p == center, help="Pema vizatohet rreth këtij personi")
        st.divider()
        quick_row(p, "pema_mq")
    with t2:
        person_form(p, "pema_m")
    with t3:
        if der:
            st.markdown("**:material/auto_awesome: Të gjitha lidhjet** :gray[· dalin vetë nga pema]")
            for w, others in der:
                st.markdown(f"{p} është **{w.split(' · ')[0]}** {pema._w('i', 'e', 'i/e', pema.sex(d, p))} "
                            + ", ".join(others) + (f" :gray[({w.split(' · ', 1)[1]})]" if ' · ' in w else ""))
            st.caption("Këto nuk duhen shtuar me dorë: mjafton një lidhje (p.sh. nëna e babait tënd) dhe pjesa tjetër "
                       "(gjyshja, nëna e vëllezërve të tij...) del vetë.")
            st.divider()
        st.markdown("**:material/edit: Lidhjet e ruajtura** :gray[· nga këto dalin të tjerat; mund t'i ndryshosh]")
        if not mine:
            st.caption("Asnjë lidhje ende.")
        for lk in mine:
            c1, c2, c3 = st.columns([8, 2, 1], vertical_alignment="center")
            c1.markdown(pema.link_text(d, lk))
            c2.button("Ndrysho", icon=":material/edit:", key=f"pema_m_ed_{lkey(lk)}", on_click=open_add,
                      kwargs={"x": lk["a"], "y": lk["b"], "replace": lk}, width="stretch",
                      help="Zgjidh llojin e saktë (p.sh. babai në vend të vëllait); e vjetra zëvendësohet")
            c3.button(":material/delete:", key=f"pema_m_del_{lkey(lk)}", on_click=delete_link_cb, args=(lk,),
                      help="Hiqe këtë lidhje")
        st.button("Shto lidhje", icon=":material/add_link:", key="pema_m_link2", on_click=open_add, kwargs={"y": p})


def delete_link_cb(lk):
    d = pema.load()
    pema.delete_link(d, lk)
    pema.save(d)
    _say("success", "🗑 U hoq: " + pema.link_text(d, lk))


def sug_add(a, b, lloji):
    """Sugjerimi pranohet: b është shok/shok shkolle/koleg i a."""
    d = pema.load()
    try:
        lk = pema.add_link(d, b, a, lloji)
    except ValueError as e:
        ss.pema_sug_msg = ("error", str(e))
        return
    d["persons"].setdefault(b, {})
    pema.save(d)
    ss.pema_sug_msg = ("success", "✔ U shtua: " + pema.link_text(d, lk))


def sug_family(a, b):
    """Familja ka shumë mundësi (babai, kunata...): hap dritaren me të dy dhe lëre përdoruesin të zgjedhë."""
    open_add(x=b, y=a)


def sug_no(a, b):
    d = pema.load()
    d["jo_sugjero"].append([a, b])
    pema.save(d)
    ss.pema_sug_msg = ("info", f"🚫 {b} dhe {a} nuk do të sugjerohen më.")


def show_msg(key="pema_msg"):
    m = ss.pop(key, None)
    if m:
        getattr(st, m[0])(m[1])


def lkey(lk):
    return hashlib.md5("|".join(pema._key(lk)).encode()).hexdigest()[:12]


# ---------------- shpjegimet ----------------
HELP_TEXT = """
**Kliko një kartë** → dritarja e personit: *Lidh me dikë*, *Shiko fotot*, *Edito* (emri, gjinia, vitet) dhe
*Lidhjet* (Ndrysho / Fshi).

**Lëvizja:** tërhiq pemën me maus · **Ctrl + rrota** = zmadho · butonat djathtas: zmadho, zvogëlo, gjithë pema,
te qendra, ekran i plotë.

**Pema ruan vetëm 3 lidhje familjare:** prind, partner, vëlla/motër. Gjyshi, xhaxhai, kushëriri, vjehrri,
kunati, stërgjyshi **dalin vetë** nga zinxhiri.

**Kushërinjtë:** zgjidh *Kushëriri* dhe te **Fëmijë i/e** prindin e tij (xhaxhain, hallën...). Nëse ai s'është
në pemë, shkruaj emrin dhe zgjidh *Xhaxhai/Halla/Daja/Tezja*: lidhet vetë me babain ose nënën.

**Dikush pa foto:** shkruaj emrin e ri në listë dhe shtyp Enter. *Xhaxheshja* + emri i xhaxhait i shton të dy.

**Stërgjyshërit:** kliko gjyshin → *Babai* / *Nëna*. Sa larg të duash: **Pamja → Breza lart**.

**Ngjyrat:** indigo = gjaku · rozë = nga martesa · blu/portokalli/jeshile = shoqëria/shkolla/puna ·
vija e ndërprerë = pa kontakt.
"""

QUICK_HELP = {"Babai": "babai i {p}", "Nëna": "nëna e {p}", "Vëllai": "vëllai i {p}", "Motra": "motra e {p}",
              "Partneri/ja": "bashkëshorti/ja ose partneri/ja i/e {p}", "Djali": "djali i {p}", "Vajza": "vajza e {p}",
              "Xhaxhai": "vëllai i babait të {p} (lidhet vetë me babain)",
              "Kushëri": "fëmija i xhaxhait/dajës/hallës/tezes së {p}"}


def quick_row(person, key, primary=()):
    """Butonat e shpejtë 'Shto për [person]': hapin dritaren të plotësuar (Babai i X, Kushëriri i X...)."""
    q = st.container(horizontal=True, vertical_alignment="center")
    q.caption(f"Shto për **{person}**:")
    partner = ("Bashkëshortja / Partnerja" if pema.sex(data, person) == "m"
               else "Bashkëshorti / Partneri" if pema.sex(data, person) == "f" else None)
    for lbl, rel in QUICK:
        q.button(lbl, icon=":material/add:", key=f"{key}_{lbl}", type="primary" if lbl in primary else "secondary",
                 on_click=open_add, kwargs={"rel": rel or partner, "y": person},
                 help="Hap dritaren: [emri] është " + QUICK_HELP.get(lbl, lbl).format(p=person))


# ---------------- faqja ----------------
QUICK = [("Babai", "Babai"), ("Nëna", "Nëna"), ("Vëllai", "Vëllai"), ("Motra", "Motra"),
         ("Partneri/ja", None), ("Djali", "Djali"), ("Vajza", "Vajza"), ("Xhaxhai", "Xhaxhai (vëllai i babait)"),
         ("Kushëri", "Kushëriri")]

if not data["une"]:
    import ui

    ui.header("Pema e lidhjeve", "Familja (sa breza të duash) dhe njerëzit e tu: shoqëria, shkolla, puna.",
              ":material/account_tree:")
    with st.container(border=True):
        st.markdown("**Fillimisht: kush je ti?** Pema ndërtohet rreth teje. Zgjidh një nga emrat që njeh Renditësi "
                    "nga fytyrat, ose shkruaj emrin.")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        idx = None
        c1.selectbox("Emri yt", names, index=idx, key="pema_une", accept_new_options=True,
                     placeholder="Zgjidh ose shkruaj emrin...")
        c2.button("Kjo jam unë", icon=":material/check:", type="primary", on_click=set_me,
                  disabled=not ss.get("pema_une"), width="stretch")
    st.stop()

une = data["une"]
if ss.get("pema_qendra") not in names:
    ss.pema_qendra = une


def open_menu(p):
    ss.pema_menu, ss.pema_menu_open = p, True


# ----- shiriti lart: titulli · qendra · pamja · ndihma · shto -----
h1, h2, h3, h4, h5 = st.columns([4.2, 2.4, 1.1, 0.6, 1.7], vertical_alignment="bottom")
with h1:
    st.markdown("### :material/account_tree: Pema e lidhjeve")
    st.caption(f"{len(data['persons'])} persona · {len(data['links'])} lidhje · kliko një kartë për ta lidhur ose edituar")
center = h2.selectbox("Qendra", names, key="pema_qendra",
                      help="Pema vizatohet rreth këtij personi; emërtimet (gjyshi, kushërira...) janë nga ana e tij.")
with h3.popover("Pamja", icon=":material/tune:", width="stretch", help="Sa breza, vetëm kë ke kontakt"):
    up = st.slider("Breza lart", 1, 8, 3, key="pema_lart", help="2 = gjyshërit, 3 = stërgjyshërit")
    down = st.slider("Breza poshtë", 0, 6, 2, key="pema_poshte", help="1 = fëmijët, 2 = nipërit/mbesat")
    only = st.toggle("Vetëm me kontakt", key="pema_kontakt",
                     help="Fsheh të afërmit pa kontakt. Të parët e tu dhe ata që lidhin dikë me ty mbeten gjithmonë.")
with h4.popover("", icon=":material/help:", width="stretch", help="Si funksionon?"):
    st.markdown(HELP_TEXT)
h5.button("Shto lidhje", icon=":material/add_link:", type="primary", width="stretch", key="pema_add_top",
          on_click=open_add, kwargs={"y": center or une},
          help="Familje (edhe gjyshër, xhaxhallarë, kushërinj), shok, shkollë, punë.")

# ----- pema -----
lay = cached_layout(json.dumps(data, sort_keys=True, ensure_ascii=False), center, up, down, only, tuple(sorted(FACES)),
                    getattr(pema, "_LOADED", 0))
sel = [n for n in ss.get("pema_sel", []) if n in names]
empty = len(lay["nodes"]) == 1
if empty:
    with st.container(border=True):
        st.markdown(f"#### :material/waving_hand: Fillo pemën e {center}")
        st.caption("Shto prindërit dhe vëllezërit/motrat. Gjyshërit, kushërinjtë dhe vjehrri dalin vetë më vonë, "
                   "kur shton prindërit e prindërve, vëllezërit e tyre, partnerin.")
        quick_row(center, "pema_q", primary=("Babai", "Nëna"))
counts = {n: len(pema.photos(INDEX, n)) for n in lay["nodes"]}
svg = pema.svg(lay, data, FACES, images=face_uris(lay["nodes"]), highlight=set(sel), counts=counts)
res = kmp.tree(data={"svg": svg, "sig": hashlib.md5(svg.encode()).hexdigest(), "center": center,
                     "w": lay["width"], "h": lay["height"]},
               key="pema_pema", on_person_change=lambda: None)
clicked = getattr(res, "person", None)
if clicked and clicked in names:  # klikimi hap dritaren e personit (veprimet, editimi, lidhjet)
    open_menu(clicked)
    st.rerun()
if not INDEX:
    st.info("Fytyrat dhe fotot dalin këtu pasi të skanosh dhe të hapësh faqen **Personat** (aty ruhen vetë fotot e "
            "personave me emër).", icon=":material/photo_library:")
ss.pop("pema_close", None)  # vlen vetëm për dritaren e personit
if ss.pop("pema_dialog", False):
    ss.pop("pema_menu_open", None)
    add_dialog()
elif ss.pop("pema_menu_open", False):
    person_dialog()

# ----- fotot e të zgjedhurve -----
if sel:
    with st.container(border=True):
        g1, g2, g3 = st.columns([5, 1.4, 1], vertical_alignment="center")
        if len(sel) == 1:
            a = sel[0]
            paths = sorted(pema.photos(INDEX, a), key=lambda p: (pema.photos(INDEX, a)[p] or "0000", p), reverse=True)
            g1.markdown(f"#### :material/photo_library: {a} · {len(paths)} foto")
        else:
            a, b = sel
            paths = pema.together(INDEX, sel)
            yrs = pema.span(INDEX, a, paths)
            g1.markdown(f"#### :material/photo_library: {a} & {b} · {len(paths)} foto bashkë" + (f" ({yrs})" if yrs else ""))
        g2.button("Lidh / Edito", icon=":material/edit:", key="pema_sel_menu", on_click=open_menu, args=(sel[-1],),
                  width="stretch")
        g3.button("Mbyll", icon=":material/close:", key="pema_sel_x", on_click=lambda: ss.update(pema_sel=[]),
                  width="stretch")
        if len(sel) == 1:
            comp = pema.companions(INDEX, a)
            if comp:
                cc = st.container(horizontal=True, vertical_alignment="center")
                cc.caption("Del më shpesh me:")
                for i, (o, k) in enumerate(comp):
                    cc.button(f"{o} · {k}", icon=":material/group:", key=f"pema_comp_{i}", on_click=select_pair,
                              args=(a, o), type="tertiary")
        else:
            kin = pema.kinship(data, a, b)
            rel = [pema.link_text(data, lk) for lk in pema.linked(data, a, b)]
            if kin:
                st.caption(f"Për {a}: {b} është **{kin}**")
            for t in rel:
                st.caption(":material/link: " + t)
            if not kin and not rel:
                st.button(f"Shto një lidhje mes {a} dhe {b}", icon=":material/add_link:", key="pema_sel_add",
                          on_click=open_add, kwargs={"x": b, "y": a})
        gallery(paths, a)

# ----- sugjerimet nga fotot -----
sug = pema.suggestions(data, INDEX)
if sug:
    with st.expander(f":material/auto_awesome: Sugjerime nga fotot · {len(sug)}", expanded=len(data["links"]) < 5):
        st.caption(f"Dalin bashkë në të paktën {pema.SUGJERO_MIN} foto, por nuk kanë ende lidhje te pema.")
        show_msg("pema_sug_msg")
        n_sug = ss.get("pema_sug_n", 6)
        for i, (a, b, k, yrs) in enumerate(sug[:n_sug]):
            row = st.container(horizontal=True, vertical_alignment="center")
            who = "ty" if a == une else f"**{a}**"
            row.markdown(f"**{b}** del me {who} në **{k}** foto" + (f" · :gray[{yrs}]" if yrs else ""), width="stretch")
            row.button("", icon=":material/visibility:", key=f"pema_sg_see_{i}", on_click=select_pair, args=(a, b),
                       help="Shiko fotot bashkë")
            row.button("Familje", icon=":material/family_restroom:", key=f"pema_sg_fa_{i}", on_click=sug_family,
                       args=(a, b), help="Hap dritaren: zgjidh si e ka (babai, motra, kunati...)")
            row.button("Shok", icon=":material/handshake:", key=f"pema_sg_sh_{i}", on_click=sug_add,
                       args=(a, b, "shoqeri"))
            row.button("Shkollë", icon=":material/school:", key=f"pema_sg_sk_{i}", on_click=sug_add,
                       args=(a, b, "shkolla"))
            row.button("Punë", icon=":material/work:", key=f"pema_sg_pu_{i}", on_click=sug_add, args=(a, b, "puna"))
            row.button("", icon=":material/block:", key=f"pema_sg_no_{i}", on_click=sug_no, args=(a, b),
                       help="Mos e sugjero më")
        if n_sug < len(sug):
            st.button(f"Shfaq edhe ({n_sug} nga {len(sug)})", icon=":material/expand_more:", key="pema_sug_more",
                      on_click=lambda: ss.update(pema_sug_n=n_sug + 6), type="tertiary")

# ----- menaxhimi: personat, lidhjet, familjet e tjera (të palosura) -----
with st.expander(f":material/manage_accounts: Menaxho personat dhe lidhjet · {len(data['links'])} lidhje"):
    others = [c for c in pema.other_families(data, center) if not set(c) <= set(lay["nodes"])]
    if others:
        oc = st.container(horizontal=True, vertical_alignment="center")
        oc.caption("Familje që nuk lidhen (ende) me këtë pemë:")
        for i, comp in enumerate(others[:8]):
            oc.button(", ".join(comp[:3]) + (f" +{len(comp) - 3}" if len(comp) > 3 else ""),
                      icon=":material/family_restroom:", key=f"pema_other_{i}", on_click=set_center, args=(comp[0],))
    t2, t3 = st.tabs([":material/person: Personat", f":material/link: Të gjitha lidhjet ({len(data['links'])})"])
    with t2:
        p = st.selectbox("Personi", names, index=names.index(center) if center in names else None, key="pema_p")
        if p:
            st.caption(("Ka foto te Renditësi" if p in FACES else "Pa foto (i shtuar me dorë)")
                       + (" · ti" if p == une else ""))
            person_form(p, "pema")
        show_msg()
    with t3:
        flt = st.text_input("Kërko", key="pema_flt", placeholder="emër, punë, shkollë...", icon=":material/search:")
        links = [lk for lk in data["links"] if not flt or flt.casefold() in pema.link_text(data, lk).casefold()]
        order = {"prind": 0, "partner": 1, "vella": 2, **{k: 3 + i for i, k in enumerate(pema.OTHER)}}
        for lk in sorted(links, key=lambda lk: (order[lk["lloji"]], lk["a"].casefold(), lk["b"].casefold())):
            c1, c0, c2 = st.columns([11, 2, 1], vertical_alignment="center")
            c1.markdown(pema.link_text(data, lk))
            c1.button("Ndrysho", icon=":material/edit:", key=f"pema_ed_{lkey(lk)}", type="tertiary",
                      on_click=open_add, kwargs={"x": lk["a"], "y": lk["b"], "replace": lk})
            nb = len(pema.together(INDEX, [lk["a"], lk["b"]]))
            if nb:
                c0.button(f"{nb} foto", icon=":material/photo_library:", key=f"pema_ph_{lkey(lk)}",
                          on_click=select_pair, args=(lk["a"], lk["b"]), help="Fotot bashkë (shfaqen sipër)",
                          width="stretch")
            c2.button(":material/delete:", key=f"pema_del_{lkey(lk)}", on_click=delete_link_cb, args=(lk,),
                      help="Hiqe këtë lidhje")
        if not links:
            st.caption("Asnjë lidhje.")
