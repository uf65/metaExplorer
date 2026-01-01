import streamlit as st
import ui_auxiliary as uia
from attribute_types import infer_all_attribute_types

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

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
            st.session_state.applied_attributes = list(
                st.session_state.attributes_selected
            )
            st.session_state.filters = {}  # reset Filterzustand

if "applied_attributes" in st.session_state:
    st.subheader("🔧 Filter")

    types = st.session_state.attribute_types
    filters = st.session_state.filters

    for attr in st.session_state.applied_attributes:
        attr_type = types[attr]

        if attr_type == "datetime":
            st.markdown(f"#### 🕒 {attr}")

            comps = uia.get_datetime_components(df[attr])

            col1, col2, col3, col4 = st.columns(4)

            filters[attr] = {
                "year": col1.multiselect(
                    "Jahr",
                    comps["year"],
                    default=comps["year"],
                    key=f"{attr}_year"
                ),
                "month": col2.multiselect(
                    "Monat",
                    comps["month"],
                    default=comps["month"],
                    key=f"{attr}_month"
                ),
                "weekday": col3.multiselect(
                    "Wochentag (0=Mo)",
                    comps["weekday"],
                    default=comps["weekday"],
                    key=f"{attr}_weekday"
                ),
                "hour": col4.multiselect(
                    "Stunde",
                    comps["hour"],
                    default=comps["hour"],
                    key=f"{attr}_hour"
                ),
            }

        elif attr_type == "numeric":
            st.markdown(f"#### 🔢 {attr}")

            series = df[attr].dropna()
            min_val, max_val = float(series.min()), float(series.max())

            filters[attr] = st.slider(
                attr,
                min_value=min_val,
                max_value=max_val,
                value=(min_val, max_val),
                key=f"{attr}_range"
            )

        else:
            st.markdown(f"#### 📦 {attr}")

            values = sorted(df[attr].dropna().unique())

            filters[attr] = st.multiselect(
                attr,
                values,
                default=values,
                key=f"{attr}_cat"
            )

if "filters" in st.session_state:
    filtered_df = uia.apply_filters(
        df,
        st.session_state.filters,
        st.session_state.attribute_types
    )

    st.session_state.filtered_df = filtered_df

    st.divider()
    st.metric(
        "🎯 Anzahl Mediendateien, die den Filterkriterien entsprechen",
        f"{len(filtered_df):,}"
    )

    import time

    col_a, col_b = st.columns(2)

    # -----------------
    # ▶️ Slideshow
    # -----------------
    with col_a:
        if st.button("▶️ Slideshow", disabled=len(filtered_df) == 0):
            media_files = filtered_df["SourceFile"].tolist()

            placeholder = st.empty()

            for path in media_files:
                ext = Path(path).suffix.lower()

                placeholder.empty()

                try:
                    if ext in IMAGE_EXTS:
                        placeholder.image(path, use_container_width=True)
                    elif ext in VIDEO_EXTS:
                        placeholder.video(path)
                    else:
                        continue

                    time.sleep(2)

                except Exception as e:
                    st.warning(f"Fehler beim Anzeigen von {path}: {e}")

# -----------------
# 📄 Export
# -----------------
    with col_b:
        if st.button("📄 Export", disabled=len(filtered_df) == 0):
            export_path = meta_path.parent / "filelist.csv"

            filtered_df[["SourceFile"]].to_csv(
                export_path,
                index=False,
                encoding="utf-8"
            )

            st.success(f"Exportiert nach: {export_path}")

