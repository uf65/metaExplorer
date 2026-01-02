import streamlit as st
import ui_auxiliary as uia
import open_in_explorer as oie
from attribute_types import infer_all_attribute_types
import time

def reset_all_filters():
    """
    Setzt alle Filter (Zeit, numerisch, kategorial, Medientyp)
    auf den Ausgangszustand zurück.
    """

    keys_to_delete = []

    for key in st.session_state.keys():
        if (
            key.endswith("_year")
            or key.endswith("_month")
            or key.endswith("_weekday")
            or key.endswith("_hour")
            or key.endswith("_range")
            or key.endswith("_cat")
        ):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        del st.session_state[key]

    # Filter-Datenstruktur leeren
    st.session_state.filters = {}

    # Medientyp zurücksetzen
    st.session_state.media_type_filter = "Alle Medien"

def sanitize_filter_selections(attr, attr_type, context_df):
    """
    Stellt sicher, dass die aktuell gesetzten Filterwerte
    im gültigen Wertebereich des context_df liegen.
    """

    # --- Zeitfilter ---
    if attr_type == "datetime":
        comps = uia.get_datetime_components(context_df[attr])

        for comp in ["year", "month", "weekday", "hour"]:
            key = f"{attr}_{comp}"
            valid = set(comps[comp])
            selected = set(st.session_state.get(key, []))

            new_selection = sorted(valid & selected)

            # Fall 1: Nutzer hat bewusst alles gelöscht → leer lassen
            if not selected:
                st.session_state[key] = []
                return

            # Fall 2: Auswahl existiert, aber ist im neuen Kontext ungültig → reset
            if not new_selection and selected:
                new_selection = sorted(valid)

            st.session_state[key] = new_selection

    # --- Numerisch ---
    elif attr_type == "numeric":
        key = f"{attr}_range"

        if key in st.session_state:
            series = context_df[attr].dropna()
            if series.empty:
                return

            min_val, max_val = float(series.min()), float(series.max())
            cur_min, cur_max = st.session_state[key]

            new_min = max(min_val, cur_min)
            new_max = min(max_val, cur_max)

            if new_min > new_max:
                new_min, new_max = min_val, max_val

            st.session_state[key] = (new_min, new_max)

    # --- Kategorisch ---
    else:
        key = f"{attr}_cat"
        valid = set(context_df[attr].dropna().unique())
        selected = set(st.session_state.get(key, []))

        new_selection = sorted(valid & selected)

        if not selected:
            st.session_state[key] = []
            return

        if not new_selection:
            new_selection = sorted(valid)

        st.session_state[key] = new_selection


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
    col_h, col_reset = st.columns([6, 1])

    with col_h:
        st.subheader("🔧 Filter")

    with col_reset:
        if st.button("🔄 Reset", help="Alle Filter zurücksetzen"):
            reset_all_filters()
            st.rerun()

    media_filter = st.radio(
        "Medientyp",
        options=["Alle Medien", "Nur Bilder", "Nur Videos"],
        horizontal=True,
        key="media_type_filter"
    )

    types = st.session_state.attribute_types
    filters = st.session_state.filters

    for attr in st.session_state.applied_attributes:
        attr_type = types[attr]

        if attr_type == "datetime":
            context_df = uia.apply_filters_except(
                df,
                filters,
                types,
                st.session_state.media_type_filter,
                exclude_attr=attr
            )

            sanitize_filter_selections(attr, attr_type, context_df)

            comps = uia.get_datetime_components(context_df[attr])

            for part in ["year", "month", "weekday", "hour"]:
                key = f"{attr}_{part}"
                if key in st.session_state:
                    st.session_state[key] = [
                        v for v in st.session_state[key]
                        if v in comps[part]
                    ]

            col_h, col_btn = st.columns([4, 1])

            with col_h:
                st.markdown(f"#### 🕒 {attr}")

            with col_btn:
                if st.button("Alles auswählen", key=f"{attr}_select_all_time"):
                    st.session_state[f"{attr}_year"] = comps["year"]
                    st.session_state[f"{attr}_month"] = comps["month"]
                    st.session_state[f"{attr}_weekday"] = comps["weekday"]
                    st.session_state[f"{attr}_hour"] = comps["hour"]

            col1, col2, col3, col4 = st.columns(4)

            filters[attr] = {
                "year": col1.multiselect(
                    "Jahr",
                    comps["year"],
                    #default=comps["year"],
                    key=f"{attr}_year"
                ),
                "month": col2.multiselect(
                    "Monat",
                    comps["month"],
                    #default=comps["month"],
                    key=f"{attr}_month"
                ),
                "weekday": col3.multiselect(
                    "Wochentag (0=Mo)",
                    comps["weekday"],
                    #default=comps["weekday"],
                    key=f"{attr}_weekday"
                ),
                "hour": col4.multiselect(
                    "Stunde",
                    comps["hour"],
                    #default=comps["hour"],
                    key=f"{attr}_hour"
                ),
            }

        elif attr_type == "numeric":
            st.markdown(f"#### 🔢 {attr}")

            context_df = uia.apply_filters_except(
                df,
                filters,
                types,
                st.session_state.media_type_filter,
                exclude_attr=attr
            )

            sanitize_filter_selections(attr, attr_type, context_df)
            series = context_df[attr].dropna()
            key = f"{attr}_range"
            lo, hi = float(series.min()), float(series.max())

            current = st.session_state.get(key, (lo, hi))
            current = (
                max(current[0], lo),
                min(current[1], hi)
            )

            filters[attr] = st.slider(
                attr,
                min_value=lo,
                max_value=hi,
                value=current,
                key=key
            )

        else:
            context_df = uia.apply_filters_except(
                df,
                filters,
                types,
                st.session_state.media_type_filter,
                exclude_attr=attr
            )

            sanitize_filter_selections(attr, attr_type, context_df)
            values = sorted(context_df[attr].dropna().unique())
            key = f"{attr}_cat"

            if key in st.session_state:
                st.session_state[key] = [
                    v for v in st.session_state[key]
                    if v in values
                ]

            col_h, col_btn = st.columns([4, 1])

            with col_h:
                st.markdown(f"#### 📦 {attr}")

            with col_btn:
                if st.button("Alles auswählen", key=f"{attr}_select_all_cat"):
                    st.session_state[f"{attr}_cat"] = list(values)

            filters[attr] = st.multiselect(
                attr,
                values,
                key=key
            )

if "filters" in st.session_state:
    filtered_df = uia.apply_filters(
        df,
        st.session_state.filters,
        st.session_state.attribute_types,
        st.session_state.media_type_filter
    )

    st.session_state.filtered_df = filtered_df

    st.divider()

    col_a, col_b = st.columns(2)
    left, center, right = st.columns([1, 4, 1])
    with center:
        viewer_container = st.container(height=500)

    with col_a:
        st.metric(
            "🎯 Anzahl Mediendateien, die den Filterkriterien entsprechen",
            f"{len(filtered_df):,}"
        )
        st.caption(f"Medientyp: {st.session_state.media_type_filter}")

    # -----------------
    # ▶️ Slideshow
    # -----------------
    with viewer_container:
        if st.button("▶️ Slideshow", disabled=len(filtered_df) == 0):
            media_files = filtered_df["SourceFile"].tolist()

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
        if st.button("📄 Export", disabled=len(filtered_df) == 0):
            export_path = meta_path.parent / "filelist.csv"

            filtered_df[["SourceFile"]].to_csv(
                export_path,
                index=False,
                encoding="utf-8"
            )

            st.success(f"Exportiert nach: {export_path}")

        if st.button("🗂 Im Explorer öffnen", disabled=len(filtered_df) == 0):
            oie.open_in_explorer(
                filtered_df["SourceFile"].tolist(),
                meta_path.parent
            )
