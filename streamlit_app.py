import streamlit as st
import ui_auxiliary as uia
import open_in_explorer as oie
from attribute_types import infer_all_attribute_types
import time

# ---------- Streamlit UI ----------

st.set_page_config(layout="wide")
st.title("📸 Medien-Metadaten Explorer")

import os
from pathlib import Path

# --- Dateiauswahl ---

base_dir = st.text_input(
    "Basisverzeichnis",
    r"E:\Medienordner"
)

meta_path = None

if base_dir and os.path.isdir(base_dir):
    json_files = sorted(
        f for f in os.listdir(base_dir)
        if f.lower().endswith(".json")
    )

    if json_files:
        meta_file = st.selectbox(
            "Metadatenfile",
            json_files
        )
        meta_path = Path(base_dir) / meta_file
        st.caption(f"Ausgewählte Datei: `{meta_path}`")
    else:
        st.warning("Keine JSON-Dateien im Verzeichnis gefunden.")

elif base_dir:
    st.error("Basisverzeichnis existiert nicht.")

# --- Einlesen-Button ---

read_clicked = st.button(
    "📥 Metadaten einlesen",
    disabled=meta_path is None
)

# --- Laden nur bei Button-Klick ---

if read_clicked:
    if not meta_path.exists():
        st.error("Datei existiert nicht.")
    else:
        with st.spinner("Lese Metadaten (Streaming)…"):
            df = uia.load_metadata(meta_path)
            st.session_state.df = df

        st.success(f"{len(df):,} Mediendateien geladen")

# --- Anzeige nach erfolgreichem Laden ---

if "df" in st.session_state:

    df = st.session_state.df
    if "attribute_types" not in st.session_state:
        with st.spinner("Bestimme Attribut-Typen…"):
            st.session_state.attribute_types = infer_all_attribute_types(df)

    attributes = sorted(df.columns)
    st.write(f"**{len(attributes)}** Attribute gefunden")

    st.subheader("Attribut-Auswahl")

    # --- Initialisierung ---

    if "attributes_all" not in st.session_state:
        st.session_state.attributes_all = list(df.columns)
        st.session_state.attributes_selected = set()
        st.session_state.attribute_filter_text = ""

    if "attribute_stats" not in st.session_state:
        total = len(df)
        stats = {}
        for col in df.columns:
            cnt = df[col].notna().sum()
            stats[col] = {
                "count": int(cnt),
                "percent": 100.0 * cnt / total
            }
        st.session_state.attribute_stats = stats

    if "attribute_sort_mode" not in st.session_state:
        st.session_state.attribute_sort_mode = "alphabetisch"

    stats = st.session_state.attribute_stats

    # --- Layout ---

    col_left, col_right = st.columns([2, 1])

    # =========================
    # LINKS: Attribute finden
    # =========================

    with col_left:
        st.markdown("### 🔍 Attribute filtern")

        types = st.session_state.attribute_types

        filter_text = st.text_input(
            "Filter (Substring, z.B. 'gps', 'time', 'date')",
            value=st.session_state.attribute_filter_text
        )
        st.session_state.attribute_filter_text = filter_text

        col_sort1, col_sort2 = st.columns(2)
        with col_sort1:
            if st.button("🔤 Alphabetisch"):
                st.session_state.attribute_sort_mode = "alphabetisch"
        with col_sort2:
            if st.button("📊 Nach Häufigkeit"):
                st.session_state.attribute_sort_mode = "häufigkeit"

        filtered_attributes = [
            a for a in st.session_state.attributes_all
            if filter_text.lower() in a.lower()
               and a not in st.session_state.attributes_selected
        ]

        if st.session_state.attribute_sort_mode == "alphabetisch":
            filtered_attributes = sorted(filtered_attributes)
        else:
            filtered_attributes = sorted(
                filtered_attributes,
                key=lambda a: stats[a]["percent"],
                reverse=True
            )

        st.caption(f"{len(filtered_attributes)} Attribute gefunden")

        with st.container(height=400):
            for attr in filtered_attributes:
                label = f"{attr} ({types[attr]} / {stats[attr]['count']:,} / {stats[attr]['percent']:.1f}%)"
                if st.checkbox(label, key=f"attr_check_{attr}"):
                    st.session_state.attributes_selected.add(attr)

    # =========================
    # RECHTS: Ausgewählte
    # =========================

    with col_right:
        st.markdown("### ✅ Ausgewählte Attribute")
        st.caption(f"{len(st.session_state.attributes_selected)} ausgewählt")

        with st.container(height=300):
            for attr in sorted(st.session_state.attributes_selected):
                col_a, col_b = st.columns([5, 1])
                col_a.write(attr)
                if col_b.button("❌", key=f"remove_{attr}"):
                    st.session_state.attributes_selected.remove(attr)

        st.divider()

        if st.button("🚀 Anwenden"):
            selected_attrs = list(st.session_state.attributes_selected)
            st.session_state.applied_attributes = selected_attrs
            st.session_state.filters = {}  # reset Filterzustand
            # filtered_df löschen, damit die neue Auswahl auf dem ganzen Datensatz startet
            if "filtered_df" in st.session_state:
                del st.session_state["filtered_df"]

            # NEU: Vor-Initialisierung mit ALLEN Werten
            for attr in selected_attrs:
                attr_type = st.session_state.attribute_types[attr]
                if attr_type == "datetime":
                    comps = uia.get_datetime_components(df[attr])
                    st.session_state[f"{attr}_year"] = comps["year"]
                    st.session_state[f"{attr}_month"] = comps["month"]
                    st.session_state[f"{attr}_weekday"] = comps["weekday"]
                    st.session_state[f"{attr}_hour"] = comps["hour"]
                elif attr_type == "categorical":
                    st.session_state[f"{attr}_cat"] = sorted(df[attr].dropna().unique().tolist())
                # numeric Slider initialisieren sich meist von selbst über min/max
            st.rerun()

if "applied_attributes" in st.session_state:
    # 1. Kopfbereich mit Reset und dem neuen globalen Apply-Button
    st.divider()
    col_h, col_reset, col_apply = st.columns([2, 1, 4])
    with col_h:
        st.subheader("🔧 Filter")

    with col_reset:
        if st.button("🔄 Reset"):
            uia.reset_all_filters()

    media_filter = st.radio("Medientyp", ["Alle Medien", "Nur Bilder", "Nur Videos"],
                            horizontal=True, key="media_type_filter")

    types = st.session_state.attribute_types

    # 1. Sicherstellen, dass die Filter-Struktur existiert
    if "filters" not in st.session_state:
        st.session_state.filters = {}

    # Bestimme die Basis für die Kreuzfilter-Optionen (Snapshot des letzten Klicks)
    current_base_df = st.session_state.get("filtered_df", df)

    for attr in st.session_state.applied_attributes:
        attr_type = types[attr]

        # 2. Kontext berechnen
        # Wir nutzen das Original-df als Basis für die Kreuzfilterung der Optionen,
        # damit wir nicht in eine "Leere-Menge-Sackgasse" geraten.
        context_df = uia.apply_filters_except(
            df,
            st.session_state.filters,
            types,
            st.session_state.media_type_filter,
            exclude_attr=attr
        )

        # --- CATEGORICAL FILTER ---
        if attr_type == "categorical":
            st.markdown(f"#### 📦 {attr}")
            key = f"{attr}_cat"

            # Werte aus dem Kontext und der aktuellen Auswahl
            current_sel = st.session_state.get(key, [])
            available_vals = context_df[attr].dropna().unique().tolist()

            # WICHTIG: Wenn der Kontext leer ist (z.B. beim ersten Start),
            # nehmen wir alle Werte des Attributs aus dem Original-Datensatz.
            all_opts = sorted(list(set(current_sel) | set(available_vals)))
            if not all_opts:
                all_opts = sorted(df[attr].dropna().unique().tolist())

            # Widget anzeigen und Wert im Filter-Dict speichern
            selected = st.multiselect("Werte auswählen", options=all_opts, key=key)
            st.session_state.filters[attr] = selected

        # --- DATETIME FILTER ---
        elif attr_type == "datetime":
            st.markdown(f"#### 🕒 {attr}")
            comps = uia.get_datetime_components(context_df[attr])
            full_comps = uia.get_datetime_components(df[attr])

            col1, col2, col3, col4 = st.columns(4)
            time_parts = [("year", "Jahr", col1), ("month", "Monat", col2),
                          ("weekday", "Wochentag", col3), ("hour", "Stunde", col4)]

            if attr not in st.session_state.filters:
                st.session_state.filters[attr] = {}

            for p_key, label, col in time_parts:
                key = f"{attr}_{p_key}"
                current_sel = st.session_state.get(key, [])

                # Auch hier: Auswahl + Kontext-Optionen
                opts = sorted(list(set(current_sel) | set(comps[p_key])))
                if not opts:
                    opts = full_comps[p_key]

                col.multiselect(label, options=opts, key=key)
                st.session_state.filters[attr][p_key] = st.session_state.get(key, [])

        # --- NUMERIC FILTER ---
        elif attr_type == "numeric":
            st.markdown(f"#### 🔢 {attr}")
            series = df[attr].dropna()
            if not series.empty:
                lo, hi = float(series.min()), float(series.max())
                st.session_state.filters[attr] = st.slider(attr, lo, hi, key=f"{attr}_range")

    # 3. Der zentrale Trigger-Button
    st.divider()
    if st.button("🚀 Filter auf Medienbestand anwenden", type="primary", use_container_width=True):
        st.session_state.filtered_df = uia.apply_filters(
            df, st.session_state.filters, types, st.session_state.media_type_filter
        )
        st.rerun()

    # 4. Anzeige des Ergebnisses (nur wenn bereits gefiltert wurde)
    if "filtered_df" in st.session_state:
        f_df = st.session_state.filtered_df

        st.divider()
        col_a, col_b = st.columns(2)
        left, center, right = st.columns([1, 4, 1])
        with center:
            viewer_container = st.container(height=500)

        with col_a:
            st.metric(
                "🎯 Anzahl Mediendateien, die den Filterkriterien entsprechen",
                f"{len(f_df):,}"
            )
            st.caption(f"Medientyp: {st.session_state.media_type_filter}")

        # -----------------
        # ▶️ Slideshow
        # -----------------
        with viewer_container:
            if st.button("▶️ Slideshow", disabled=len(f_df) == 0):
                media_files = f_df["SourceFile"].tolist()

                placeholder = st.empty()

                for path in media_files:
                    ext = Path(path).suffix.lower()

                    placeholder.empty()

                    try:
                        if ext in uia.IMAGE_EXTS:
                            img = uia.load_and_scale_image(path)
                            placeholder.image(img)
                            time.sleep(2)
                        elif ext in uia.VIDEO_EXTS:
                            placeholder.video(path)
                            duration = uia.get_video_duration(path)
                            time.sleep(duration + 5)
                        else:
                            continue


                    except Exception as e:
                        st.warning(f"Fehler beim Anzeigen von {path}: {e}")

    # -----------------
    # 📄 Export
    # -----------------
        with col_b:
            if st.button("📄 Export", disabled=len(f_df) == 0):
                export_path = meta_path.parent / "filelist.csv"

                f_df[["SourceFile"]].to_csv(
                    export_path,
                    index=False,
                    encoding="utf-8"
                )

                st.success(f"Exportiert nach: {export_path}")

            if st.button("🗂 Im Explorer öffnen", disabled=len(f_df) == 0):
                oie.open_in_explorer(
                    f_df["SourceFile"].tolist(),
                    meta_path.parent
                )
