import streamlit as st
import pandas as pd
import ijson
import re
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

_EXIF_DATE_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})(.*)$")


def parse_exif_datetime_series(series: pd.Series) -> pd.Series:
    # 1. Konvertierung zu String und Normalisierung
    s = series.dropna().astype(str)

    def normalize(v: str) -> str:
        if not isinstance(v, str) or v.strip() == "":
            return v
        # Exif Standard YYYY:MM:DD HH:MM:SS zu YYYY-MM-DD HH:MM:SS
        m = _EXIF_DATE_RE.match(v)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}{m.group(4)}"
        return v

    normalized = s.map(normalize)

    # 2. Umwandlung mit utc=True um Mixed-Offsets zu handhaben
    return pd.to_datetime(
        normalized,
        errors="coerce",
        utc=True  # Behebt die FutureWarning und sorgt für einheitlichen Typ
    )

def get_datetime_components(series):
    dt = parse_exif_datetime_series(series)
    valid_dt = dt.dropna()

    # Falls nach der Konvertierung nichts übrig bleibt oder der Typ falsch ist
    if valid_dt.empty or not pd.api.types.is_datetime64_any_dtype(valid_dt):
        return {"year": [], "month": [], "weekday": [], "hour": []}

    # Sicherstellen, dass die Series als Datetime erkannt wird
    valid_dt = pd.to_datetime(valid_dt)

    return {
        "year": sorted(valid_dt.dt.year.unique().astype(int)),
        "month": sorted(valid_dt.dt.month.unique().astype(int)),
        "weekday": sorted(valid_dt.dt.weekday.unique().astype(int)),
        "hour": sorted(valid_dt.dt.hour.unique().astype(int)),
    }

def apply_filters(df, filters, types):
    mask = pd.Series(True, index=df.index)

    for attr, f in filters.items():
        t = types[attr]

        if t == "datetime":
            dt = parse_exif_datetime_series(df[attr])

            # Falls die Spalte keine Datumsangaben enthält, überspringen oder alles ausblenden
            if not pd.api.types.is_datetime64_any_dtype(dt):
                mask &= False
                continue

            # Erstelle eine Maske für gültige (nicht NaT) Werte
            temp_mask = dt.notna()

            # Nur filtern, wenn Werte vorhanden sind
            # Wir verwenden hier .dt nur auf den validen Werten
            temp_mask &= dt.dt.year.isin(f["year"])
            temp_mask &= dt.dt.month.isin(f["month"])
            temp_mask &= dt.dt.weekday.isin(f["weekday"])
            temp_mask &= dt.dt.hour.isin(f["hour"])

            mask &= temp_mask

        elif t == "numeric":
            lo, hi = f
            mask &= df[attr].between(lo, hi)

        else:  # categorical
            mask &= df[attr].isin(f)

    return df[mask]


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

            comps = get_datetime_components(df[attr])

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
    filtered_df = apply_filters(
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
