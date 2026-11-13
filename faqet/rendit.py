"""Faqja 3 · Rendit: çfarë përfshihet, si dalin dosjet, pamja paraprake, vendi në disk dhe kopjimi."""
import os
from collections import Counter

import streamlit as st

import ui
from ui import ss

core, ai = ui.core, ui.ai
sources, out_dir, _ = ui.scan_context()
recs = ss.get("records")
rows, source = ui.current_rows()

ui.header("Rendit fotot", "Zgjidh çfarë të përfshish dhe si të dalin dosjet; djathtas sheh menjëherë çfarë do "
          "të krijohet.", ":material/folder_copy:")
if not rows:
    ui.no_scan_yet("Renditja ka nevojë për një skanim, ose për një katalog të mëparshëm te dosja e daljes "
                   f"(`{out_dir}`).")
    st.stop()
if source == "katalog":
    st.info(f"Po rendit nga katalogu i dosjes `{out_dir}` (pa skanuar). Për foto të reja: faqja **Skano**.",
            icon=":material/menu_book:")


def keep_valid(key, options, multi=False):
    """Vlera e ruajtur e një widget-i mund të mos jetë më mes opsioneve (skanim tjetër): pastroje."""
    if key in ss:
        v = ss[key]
        if multi:
            ss[key] = [x for x in (v or []) if x in options]
        elif v not in options:
            del ss[key]


left, right = st.columns([3, 2], gap="medium")

# ================= majtas: zgjedhjet =================
with left:
    with st.container(border=True):
        st.markdown("**:material/filter_alt: Çfarë të përfshij?**")
        skip_dups = st.toggle("Kapërce fotot e dyfishta", True, key="opt_skipdups", persist_state="session")
        live = [r for r in rows if not (skip_dups and r["dyfishe"])]
        cats = Counter(r["kategoria"] for r in live if r["kategoria"] and r["lloji"] != "video")
        allowed = None
        if cats:
            label = lambda c: ui.CAT_LABELS.get(c, c)  # noqa: E731
            fmt = lambda c: f"{label(c)} ({cats[c]})"  # noqa: E731
            opts = sorted(cats, key=lambda c: -cats[c])
            real = [c for c in opts if ui.CAT_REAL.get(c, True)]
            fake = [c for c in opts if not ui.CAT_REAL.get(c, True)]
            keep_valid("keep_real", real, multi=True)
            keep_valid("keep_fake", fake, multi=True)
            keep_real = st.pills(":material/photo_camera: Foto reale", real,
                                 selection_mode="multi", format_func=fmt, key="keep_real", persist_state="session",
                                 default=[c for c in real if c in ui.CAT_DEFAULT or c in ("video", "gabim")])
            keep_fake = st.pills(":material/sports_esports: Jo foto (lojëra, logo, screenshot...)", fake,
                                 selection_mode="multi", format_func=fmt, key="keep_fake", persist_state="session",
                                 default=[]) if fake else []
            allowed = set(keep_real or []) | set(keep_fake or [])
            st.caption("Ato që heq nuk kopjohen (mbeten në katalog; mund t'i shtosh më vonë).")
            with st.expander("Shiko shembuj për çdo kategori", icon=":material/visibility:"):
                pick = st.selectbox("Kategoria", opts, format_func=fmt)
                sample = [r["shtegu"] for r in live if r["kategoria"] == pick and r["lloji"] == "foto"
                          and os.path.exists(r["shtegu"])][:12]
                if sample:
                    st.image(sample, width=110)
        vids = [r for r in live if r["lloji"] == "video"]
        vid_paths = {r["shtegu"] for r in vids}
        vmode, voff = "none", None
        if vids:
            voff = ss.setdefault("video_off", set())
            v_on = [r for r in vids if r["shtegu"] not in voff]
            v_size = sum(int(r.get("madhesia_kb") or 0) for r in v_on) * 1024
            st.markdown(f"**:material/movie: Videot** · {len(v_on)} nga {len(vids)} të zgjedhura · "
                        f"{core.human_size(v_size)}")
            v1, v2 = st.columns([3, 1], vertical_alignment="center")
            keep_valid("vmode", [ui.V_OWN, ui.V_WITH, ui.V_NONE])
            vm = v1.segmented_control("Ku të shkojnë videot?", [ui.V_OWN, ui.V_WITH, ui.V_NONE], default=ui.V_OWN,
                                      key="vmode", required=True, persist_state="session",
                                      label_visibility="collapsed",
                                      help="AI-ja nuk shikon brenda videove, prandaj ato renditen sipas datës.")
            if v2.button("Zgjidh", icon=":material/checklist:", width="stretch", disabled=vm == ui.V_NONE,
                         help="Shiko të gjitha videot dhe zgjidh cilat të kopjohen"):
                ss.vid_n = 30
                ui.videos_dialog(vids)
            vmode = ui.V_MODE[vm]
            if allowed is not None:
                allowed.add("video")

    with st.container(border=True):
        st.markdown("**:material/account_tree: Si të dalin dosjet?**")
        presets = list(ui.PRESETS)
        keep_valid("struktura", presets)
        choice = st.pills("Struktura e dosjeve", presets, default=ui.PER_PERSON if ss.get("groups") else "Viti → Muaji",
                          key="struktura", required=True, persist_state="session",
                          format_func=lambda p: f"{ui.PRESET_ICON.get(p, '')} {p}", label_visibility="collapsed")
        if choice in ui.PRESET_HELP:
            st.caption(ui.PRESET_HELP[choice])
        levels = ui.PRESETS[choice]
        if levels is None:
            l1, l2, l3 = st.columns(3)
            none = "—"
            levels = [
                l1.selectbox("Niveli 1", core.LEVELS, 0, key="lvl1", persist_state="session"),
                l2.selectbox("Niveli 2", [none] + core.LEVELS, 2, key="lvl2", persist_state="session"),
                l3.selectbox("Niveli 3", [none] + core.LEVELS, 0, key="lvl3", persist_state="session"),
            ]
            levels = [lv for lv in levels if lv != none]
        per_person = choice == ui.PER_PERSON
        others = True
        if per_person:
            others = st.toggle(f"Përfshi edhe dosjen '{core.OTHERS}'", True, key="opt_others", persist_state="session",
                               help="Fotot me njerëz ku nuk u njoh asnjë nga personat (p.sh. njerëz që dalin rrallë "
                                    "ose fytyra të vogla në sfond).")
        with st.expander("Më shumë opsione", icon=":material/tune:"):
            fallback = st.toggle("Përdor datën e skedarit kur mungon data e fotos", True, key="opt_fallback",
                                 persist_state="session",
                                 help="Nëse e heq, fotot pa datë të vërtetë shkojnë te 'Pa Datë'.")
            mode = st.segmented_control("Mënyra", ["Kopjo (e sigurt)", "Zhvendos"], default="Kopjo (e sigurt)",
                                        key="opt_mode", required=True, persist_state="session")
        move = mode.startswith("Zhvendos")
        if move:
            st.warning("Zhvendosja i heq fotot (dhe videot) nga vendi i tyre. Mund ta anulosh, por kopjimi është "
                       "më i sigurt.", icon=":material/warning:")
        if per_person and vmode == "with":
            st.caption(f"Te 'Çdo person' videot shkojnë te dosja '{core.VIDEOS}' → Viti → Muaji "
                       "(AI-ja nuk njeh persona brenda videove).")

planned = core.plan_layout(rows, levels, allowed, skip_dups, fallback, per_person, others, videos=vmode, skip=voff)
n_vid = sum(1 for s, _ in planned if s in vid_paths)
n_ph = len(planned) - n_vid

# ================= djathtas: pamja paraprake dhe veprimi =================
with right, st.container(border=True):
    st.markdown("**:material/preview: Pamja paraprake**")
    if not planned:
        st.caption("Asgjë për të kopjuar me këto zgjedhje.")
    else:
        top = Counter(d[0].split(os.sep)[0] for _, d in planned)
        sub = Counter(os.sep.join(d[0].split(os.sep)[:2]) for _, d in planned if len(levels) > 1)
        st.code(f"{os.path.basename(out_dir) or out_dir}\\{planned[0][1][0]}", language=None)
        st.dataframe([{levels[0]: k, "Foto": v} for k, v in top.most_common()], hide_index=True, width="stretch",
                     height=min(36 * (len(top) + 1) + 2, 250))
        if sub:
            with st.expander(f"Nën-dosjet ({len(sub)})"):
                st.dataframe([{" / ".join(levels[:2]): k.replace(os.sep, " / "), "Foto": v}
                              for k, v in sub.most_common()], hide_index=True, width="stretch")
    skipped = len(live) - len(planned)
    if per_person and planned:
        multi = sum(1 for _, d in planned if len(d) > 1)
        st.caption(f"{n_ph} foto me njerëz → {sum(len(d) for s, d in planned if s not in vid_paths)} vende në "
                   f"dosje ({multi} janë me disa persona)." + (f" Plus {n_vid} video." if n_vid else ""))
    if skipped:
        st.caption(f"{skipped} foto nuk kopjohen (sipas filtrave" + (", ose pa njerëz" if per_person else "") + ").")

    # ----- vendi në disk -----
    space_ok = True
    if planned and out_dir:
        sizes = {r["path"]: r["size"] for r in recs} if recs else {
            r["shtegu"]: int(r["madhesia_kb"]) * 1024 for r in rows if str(r.get("madhesia_kb") or "").isdigit()}
        sp = core.space_check(planned, out_dir, move, sizes)
        space_ok = sp["mjafton"]
        s1, s2 = st.columns(2)
        s1.metric("Do të " + ("zhvendosen" if move else "kopjohen"), core.human_size(sp["nevojitet"]),
                  help="Madhësia gjithsej e fotove që do të shkruhen në dosjen e re.")
        s2.metric(f"E lirë në {sp['disku']}", "?" if sp["te_lira"] is None else core.human_size(sp["te_lira"]),
                  delta=None if sp["mbetet"] is None else f"mbetet {core.human_size(max(0, sp['mbetet']))}",
                  delta_color="off", delta_arrow="off",
                  help=("Kopjet e vjetra që fshihen te ri-renditja lirojnë edhe " + core.human_size(sp["liruar"]))
                  if sp["liruar"] else None)
        if sp["shtese"]:
            st.caption(f":material/link: {sp['shtese']} kopjet shtesë (e njëjta foto te disa persona) bëhen lidhje të "
                       "forta: duken si foto të zakonshme, por nuk zënë vend shtesë." if sp["lidhje"] else
                       f"Disku {sp['disku']} nuk lejon lidhje: {sp['shtese']} kopjet shtesë zënë vend (është "
                       "përfshirë në llogari).")
        if not space_ok:
            st.error(f"Nuk ka vend në {sp['disku']}: duhen {core.human_size(sp['nevojitet'])}, ka "
                     f"{core.human_size(sp['te_lira'] or 0)} (+1 GB rezervë). Zgjidh një disk tjetër ose më pak foto.",
                     icon=":material/error:")
        elif sp["mbetet"] is not None and sp["mbetet"] < 10 * 1024 ** 3:
            st.warning(f"Pas kopjimit në {sp['disku']} mbeten vetëm {core.human_size(sp['mbetet'])}.",
                       icon=":material/warning:")

    # ----- veprimi -----
    import report

    def make_report(executed, errors=(), bar=None):
        skipped_scan = (ss.get("scan_report") or {}).get("lista", []) if recs else []
        return report.build(
            out_dir, rows, planned, errors, skipped_scan, executed=executed, move=move, skip_dups=skip_dups,
            layout=" → ".join(levels), sources=sources if recs else [],
            progress=(lambda i, n: bar.progress(i / max(1, n), text=f"Raporti: pamjet e fotove {i} / {n}"))
            if bar else None)

    has_log = os.path.exists(os.path.join(out_dir, core.LOG_NAME)) if out_dir else False
    verb = "Zhvendos" if move else "Kopjo"
    what = f"{n_ph} foto" + (f" + {n_vid} video" if n_vid else "")
    st.caption(f"Te: `{out_dir}`" + (" · renditja e mëparshme këtu do të zëvendësohet" if has_log else ""))
    if st.button(f"Ri-rendit {what}" if has_log else f"{verb} {what}",
                 icon=":material/autorenew:" if has_log else ":material/play_arrow:", type="primary",
                 width="stretch", disabled=not planned or not out_dir or not space_ok):
        bar = st.progress(0.0, text="Duke filluar...")
        if has_log:
            bar.progress(0.0, text="Po heq renditjen e mëparshme...")
            core.undo(out_dir)
        if recs:  # skanim i ri → ruaj katalogun
            core.save_catalog(out_dir, rows)
        done, errors = core.execute(planned, out_dir, move, lambda i, n: bar.progress(i / n, text=f"{i} / {n}"))
        bar.progress(0.0, text="Po krijoj raportin...")
        rep_path = make_report(True, errors, bar)
        bar.empty()
        st.success(f"U krye: {done} foto u renditën te `{out_dir}`. Katalogu u ruajt (`{core.CATALOG_NAME}`): "
                   f"mund ta ri-rendisësh kur të duash pa skanuar. Raporti: `{report.REPORT_HTML}`.",
                   icon=":material/check_circle:")
        ui.open_file(rep_path)
        if errors:
            with st.expander(f"{len(errors)} gabime", icon=":material/warning:"):
                for p, e in errors[:200]:
                    st.text(f"{p}: {e}")
    c1, c2, c3 = st.columns(3)
    if c1.button("Raporti", icon=":material/description:", width="stretch", disabled=not out_dir,
                 help="Krijon raportin me të gjithë skedarët dhe çfarë do të ndodhë me secilin, pa kopjuar asgjë."):
        bar = st.progress(0.0, text="Po krijoj raportin...")
        rep_path = make_report(False, (), bar)
        bar.empty()
        st.success(f"Raporti u krijua: `{rep_path}`", icon=":material/description:")
        ui.open_file(rep_path)
    if c2.button("Hap dosjen", icon=":material/folder_open:", width="stretch",
                 disabled=not (out_dir and os.path.isdir(out_dir))):
        ui.open_file(out_dir)
    with c3.popover("Anulo", icon=":material/undo:", width="stretch"):
        st.write("Fshin kopjet e bëra nga ky program (dhe kthen në vend fotot e zhvendosura). "
                 "Origjinalet dhe katalogu mbeten.")
        if st.button("Po, anuloje", type="primary", disabled=not out_dir):
            n, errs = core.undo(out_dir)
            st.success(f"U anuluan {n} skedarë.")
            for e in errs[:50]:
                st.caption(e)
