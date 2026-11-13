"""Faqja 1 · Skano: ku janë fotot, ku dalin, çfarë analizohet. Historiku i skanimeve rihapet me një klikim."""
import datetime as dt
import os
from collections import Counter

import streamlit as st

import ui
from ui import ss

core, historiku, ai = ui.core, ui.historiku, ui.ai
sources, out_dir, bad = ui.scan_context()
hist = historiku.items()

ui.header("Skano fotot", "Analizon fotot një herë; pastaj i emërton dhe i rendit si të duash. "
          "Gjithçka punon në kompjuterin tënd, origjinalet nuk preken.", ":material/search:")

# ----- versioni dhe përditësimet (vetëm kodi nga GitHub; të dhënat e tua nuk preken) -----
try:
    import perditeso

    perditeso = ui.fresh(perditeso)
except Exception:
    perditeso = None


@st.cache_data(ttl=3600, show_spinner=False)
def _update_check(nr, repo):
    return perditeso.check()


if perditeso is not None:
    _v = perditeso.local()
    _has, _, _rem = _update_check(_v.get("nr"), _v.get("repo")) if _v.get("repo") else (False, _v, None)
    if ss.get("update_msg"):
        ok, msg = ss.pop("update_msg")
        (st.success if ok else st.error)(msg + ("\n\n**Mbyll dritaren e Renditësit dhe hape përsëri** që të nisë "
                                                "versioni i ri." if ok else ""), icon=":material/system_update:")
    elif _has:
        with st.container(border=True):
            u1, u2 = st.columns([4, 1.3], vertical_alignment="center")
            u1.markdown(f":material/new_releases: **Ka version të ri:** {_rem.get('versioni')} "
                        f":gray[(ti ke {_v.get('versioni')})]" + (f"  \n{_rem['shenim']}" if _rem.get("shenim") else ""))
            if u2.button("Përditëso", icon=":material/system_update:", type="primary", width="stretch",
                         key="update_go", help="Merr vetëm kodin e ri; emrat, pema dhe fotot e tua nuk preken"):
                with st.spinner("Po përditësoj..."):
                    ss.update_msg = perditeso.apply()
                _update_check.clear()
                st.rerun()
    vr = st.container(horizontal=True, vertical_alignment="center")
    vr.caption(f":material/info: Versioni {_v.get('versioni')}" + ("" if _v.get("repo") else " · përditësimet nuk janë lidhur ende"))
    if _v.get("repo") and vr.button("Kontrollo për përditësime", icon=":material/refresh:", type="tertiary",
                                    key="update_check"):
        _update_check.clear()
        st.rerun()

# ----- rihap menjëherë skanimin e fundit -----
if hist and ss.records is None:
    last = hist[0]
    with st.container(border=True):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(f":material/bolt: **Skanimi i fundit** · {last['koha']} · {last['gjithsej']:,} skedarë".replace(",", " ")
                    + f"  \n:gray[{' · '.join(last['dosjet'])}]")
        c2.button("Hape menjëherë", icon=":material/folder_open:", type="primary", on_click=ui.open_scan,
                  args=(last["id"],), width="stretch", key="hist_last",
                  help="Rihap rezultatet e ruajtura, pa e lexuar diskun përsëri")

# ----- burimi dhe analiza -----
left, right = st.columns([3, 2], gap="medium")
with left.container(border=True):
    st.markdown("**:material/folder: Ku janë fotot?**")
    st.text_area("Dosjet për skanim (një për rresht)", key="sources", height=96, persist_state="session",
                 label_visibility="collapsed")
    c1, c2 = st.columns(2)
    c1.button("Shto dosje", icon=":material/create_new_folder:", on_click=ui.add_source, width="stretch")
    c2.button("Gjithë PC-ja", icon=":material/computer:", on_click=ui.whole_pc, width="stretch",
              help="Dosja jote e përdoruesit + disqet e tjera (D:, E:...). Dosjet e sistemit anashkalohen.")
    st.markdown("**:material/drive_file_move: Ku të dalin të renditura?**")
    o1, o2 = st.columns([3, 1])
    o1.text_input("Dosja e re", key="out", label_visibility="collapsed", persist_state="session")
    o2.button("Zgjidh", on_click=ui.pick_out, width="stretch")
    if bad:
        st.error("Këto dosje nuk ekzistojnë: " + ", ".join(bad), icon=":material/error:")

with right.container(border=True):
    st.markdown("**:material/auto_awesome: Çfarë të analizoj?**")
    use_content = st.toggle("Përmbajtja + filtri (AI)", True, key="opt_content", persist_state="session",
                            help="Njeh plazh, ushqim, natyrë... dhe ndan fotot reale nga lojërat, logot, screenshot-et.")
    use_faces = st.toggle("Personat (AI)", True, key="opt_faces", persist_state="session",
                          help="Gjen fytyrat dhe i grupon sipas personit.")
    include_videos = st.toggle("Përfshi videot", True, key="opt_videos", persist_state="session")
    with st.expander("Opsione të tjera"):
        min_kb = st.number_input("Kapërce skedarët nën (KB)", 0, 5000, 50, 10, key="opt_minkb",
                                 persist_state="session",
                                 help="Ikonat dhe figurat e vogla të programeve nuk janë foto personale.")

catalog = core.load_catalog(out_dir) if out_dir else None
if catalog and ss.records is None:
    try:
        when = dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(out_dir, core.CATALOG_NAME)))
        when = when.strftime("%d.%m.%Y %H:%M")
    except OSError:
        when = "?"
    st.info(f"Te dosja e daljes ka një katalog me **{len(catalog)} foto** (analizuar më {when}). "
            "Mund ta ri-rendisësh **pa skanuar** te faqja **Rendit**, ose skano përsëri për fotot e reja.",
            icon=":material/menu_book:")

err = ss.pop("hist_err", None)
if err:
    st.error(err, icon=":material/error:")

if st.button("Skano dhe analizo", icon=":material/search:", type="secondary" if (hist or catalog) else "primary",
             width="stretch", disabled=not sources or bool(bad)):
    status = st.empty()
    found = []
    scan_stats = {}
    for i, (p, size, kind) in enumerate(core.iter_files(sources, include_videos, min_kb, [out_dir], scan_stats)):
        found.append({"path": p, "size": size, "kind": kind})
        if i % 200 == 0:
            status.info(f"Duke kërkuar... u gjetën {len(found)} skedarë\n\n`{os.path.dirname(p)}`")
    status.info(f"U gjetën {len(found)} skedarë. Po lexoj datat dhe vendet (vetëm të rejat; të tjerat janë "
                "të ruajtura nga skanimet e mëparshme)...")
    bar = st.progress(0.0)
    meta_cache = core.load_meta_cache()
    n_new = core.read_meta_all(found, meta_cache, lambda i, n, new: bar.progress(
        i / max(1, n), text=f"Data dhe vendi: {i} / {n} · lexuar nga disku: {new}"))
    bar.progress(1.0, text="Po kërkoj fotot e dyfishta...")
    core.mark_duplicates(found, meta_cache["sha1"])
    try:
        core.save_meta_cache(meta_cache)
    except OSError:
        pass
    bar.progress(1.0, text="Po gjej emrat e vendeve...")
    core.geocode(found)
    groups = None
    if (use_content or use_faces) and found and ai:
        uniq = [r for r in found if not r.get("dup_of")]
        bar.progress(0.0, text="Po ngarkoj modelet AI... (herën e parë mund të zgjasë pak)")
        ai.analyze(uniq, use_content, use_faces,
                   lambda i, n: bar.progress(i / n, text=f"AI po shikon fotot: {i} / {n}"))
        if use_faces:
            bar.progress(1.0, text="Po grupoj fytyrat...")
            groups = ai.cluster_faces(uniq)
    bar.empty()
    status.empty()
    ss.records, ss.groups = found, groups
    ss.removed, ss.people_for = {}, None
    per_src = Counter()
    for r in found:
        for s in sources:
            if os.path.normcase(r["path"]).startswith(os.path.normcase(os.path.join(s, ""))):
                per_src[s] += 1
                break
    ss.scan_report = {"per_src": dict(per_src), **scan_stats, "lexuar": n_new}
    try:  # historiku: herën tjetër ky skanim hapet me një klikim, pa lexuar diskun
        ss.scan_id = historiku.save(found, groups, ss.scan_report, {
            "dosjet": sources, "dalja": out_dir, "min_kb": min_kb, "videot": include_videos,
            "permbajtja": use_content, "personat": use_faces})
        ss.scan_from_hist = None
    except Exception as e:
        ss.hist_err = f"Skanimi nuk u ruajt te historiku: {e}"
    core.log_scan({
        "koha": dt.datetime.now().strftime("%d.%m.%Y %H:%M"), "gjithsej": len(found),
        "foto": sum(r["kind"] == "foto" for r in found), "video": sum(r["kind"] == "video" for r in found),
        "dosjet": " | ".join(sources), "dalja": out_dir, "min_kb": min_kb,
        "videot": "po" if include_videos else "jo", **scan_stats,
    })
    st.toast("Skanimi mbaroi", icon=":material/check_circle:")
    st.rerun()

# ----- rezultati i skanimit -----
recs = ss.records
if recs is not None and not recs:
    st.info("Nuk u gjet asnjë foto në këto dosje.", icon=":material/image_not_supported:")
elif recs:
    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gjithsej", len(recs))
        m2.metric("Me datë të vërtetë", sum(1 for r in recs if r.get("date_src") == "exif"))
        m3.metric("Me vendndodhje", sum(1 for r in recs if r.get("vendi")))
        m4.metric("Të dyfishta", sum(1 for r in recs if r.get("dup_of")))
        if ss.get("scan_from_hist"):
            st.caption(f":material/history: Skanim i hapur nga historiku ({ss.scan_from_hist['koha']}). Për fotot e "
                       "shtuara pas tij, shtyp **Skano dhe analizo** (lexon vetëm skedarët e rinj ose të ndryshuar).")
        elif (ss.get("scan_report") or {}).get("lexuar") is not None:
            n_read = ss.scan_report["lexuar"]
            st.caption(f":material/bolt: U lexuan nga disku vetëm {n_read} skedarë të rinj/të ndryshuar; "
                       f"{len(recs) - n_read} të tjerët u morën nga skanimet e mëparshme.")
        with st.expander("Detajet e skanimit (pse ndryshon numri?)"):
            rep = ss.get("scan_report") or {}
            st.dataframe([{"Dosja": k, "Skedarë": v} for k, v in (rep.get("per_src") or {}).items()],
                         hide_index=True, width="stretch")
            st.caption(
                f"Video: {sum(r['kind'] == 'video' for r in recs)} · "
                f"Kapërcyer si të vogla (nën {min_kb} KB): {rep.get('te_vogla', 0)} · "
                f"Dosje/skedarë pa akses: {rep.get('pa_akses', 0)} · "
                f"Dosje të përjashtuara (dosja e daljes): {rep.get('perjashtuar', 0)}")
            scans = core.load_scans()[-6:]
            if len(scans) > 1:
                st.markdown("**Skanimet e fundit (për krahasim):**")
                st.dataframe([{"Koha": s["koha"], "Gjithsej": s["gjithsej"], "Foto": s["foto"], "Video": s["video"],
                               "Min KB": s["min_kb"], "Videot": s["videot"], "Dosjet": s["dosjet"],
                               "Dalja": s["dalja"]} for s in reversed(scans)], hide_index=True, width="stretch")
    if ss.get("groups"):
        ui.next_step("Vazhdo: Personat", "personat")
    else:
        ui.next_step("Vazhdo: Rendit", "rendit")
elif catalog:
    ui.next_step("Ri-rendit nga katalogu", "rendit", icon=":material/folder_copy:")

# ----- historiku -----
if hist:
    with st.expander(f":material/history: Historiku i skanimeve ({len(hist)})"):
        st.caption("Çdo skanim ruhet i plotë dhe rihapet menjëherë (fotot e shtuara pas tij nuk shihen: për to "
                   "shtyp Skano, që tani lexon vetëm të rejat). Një skanim i ri i të njëjtave dosje zëvendëson "
                   f"të vjetrin; mbahen {historiku.KEEP} më të fundit.")
        for h in hist:
            hc1, hc2, hc3 = st.columns([7, 2, 1], vertical_alignment="center")
            now_open = ss.get("scan_id") == h["id"] and ss.records is not None
            hc1.markdown(f"**{h['koha']}** · {h['gjithsej']} skedarë ({h['foto']} foto, {h['video']} video)"
                         + (f" · {h['grupe']} grupe fytyrash" if h.get("grupe") else "")
                         + (" · :green[i hapur]" if now_open else "") + f"  \n:gray[{' · '.join(h['dosjet'])}]")
            hc2.button("Hap", icon=":material/folder_open:", key=f"hist_open_{h['id']}", on_click=ui.open_scan,
                       args=(h["id"],), width="stretch", disabled=now_open)
            hc3.button(":material/delete:", key=f"hist_del_{h['id']}", on_click=ui.delete_scan, args=(h["id"],),
                       help=f"Hiqe nga historiku ({h.get('mb', '?')} MB). Fotot nuk preken.")
