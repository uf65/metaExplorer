import streamlit as st
import pandas as pd
import ijson
from pathlib import Path
from attribute_types import infer_all_attribute_types

# ---------- Hilfsfunktionen ----------

def normalize_sourcefile(meta_file: Path, sourcefile: str) -> str:
    base_dir = meta_file.parent
    if sourcefile.startswith("./"):
        return str(base_dir / sourcefile[2:])
    return str(base_dir / sourcefile)

def extract_directory_levels(sourcefile: str):
    p = Path(sourcefile)
    parts = p.parts[:-1]  # ohne Dateiname

    parts = [p for p in parts if p not in (".", "")]

    level_dirs = []
    year_found = False

    for d in parts:
        if d.isdigit() and len(d) == 4:
            year_found = True
            continue
        if year_found:
            level_dirs.append(d)

    return {
        f"Level{i+1}-Verzeichnis": name
        for i, name in enumerate(level_dirs)
    }

def load_metadata(meta_file: Path, max_items=None):
    rows = []

    with open(meta_file, "rb") as f:
        for i, item in enumerate(ijson.items(f, "item")):
            src = item.get("SourceFile")
            if not src:
                continue

            normalized = normalize_sourcefile(meta_file, src)
            item["SourceFile"] = normalized

            levels = extract_directory_levels(src)
            item.update(levels)

            rows.append(item)

            if max_items and i >= max_items:
                break

    return pd.DataFrame(rows)

def filter_attributes(attributes, query):
    if not query:
        return attributes
    q = query.lower()
    return [a for a in attributes if q in a.lower()]

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
            df = load_metadata(meta_path)
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

        with st.container(height=400):
            for attr in sorted(st.session_state.attributes_selected):
                col_a, col_b = st.columns([5, 1])
                col_a.write(attr)
                if col_b.button("❌", key=f"remove_{attr}"):
                    st.session_state.attributes_selected.remove(attr)
