import pandas as pd
import ijson
import re
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

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

def apply_filters(df, filters, types, media_filter):
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

    # --- Medienfilter (global) ---
    if media_filter != "Alle Medien":
        is_image = df["SourceFile"].str.lower().str.endswith(
            tuple(IMAGE_EXTS)
        )
        is_video = df["SourceFile"].str.lower().str.endswith(
            tuple(VIDEO_EXTS)
        )

        if media_filter == "Nur Bilder":
            mask &= is_image
        elif media_filter == "Nur Videos":
            mask &= is_video

    return df[mask]


# In ui_auxiliary.py

def apply_filters_except(df, filters, types, media_filter, exclude_attr=None):
    mask = pd.Series(True, index=df.index)

    for attr, f in filters.items():
        if attr == exclude_attr or not f:
            continue  # WICHTIG: Wenn f leer ist, ignoriere diesen Filter (lässt alles durch)

        t = types[attr]
        if t == "datetime":
            dt = parse_exif_datetime_series(df[attr])
            if pd.api.types.is_datetime64_any_dtype(dt):
                # Nur Komponenten filtern, die nicht leer sind
                if f.get("year"): mask &= dt.dt.year.isin(f["year"])
                if f.get("month"): mask &= dt.dt.month.isin(f["month"])
                if f.get("weekday"): mask &= dt.dt.weekday.isin(f["weekday"])
                if f.get("hour"): mask &= dt.dt.hour.isin(f["hour"])

        elif t == "numeric":
            mask &= df[attr].between(f[0], f[1])

        else:  # categorical
            if isinstance(f, list) and len(f) > 0:
                mask &= df[attr].isin(f)

    # Globaler Medienfilter bleibt immer aktiv
    if media_filter != "Alle Medien":
        is_image = df["SourceFile"].str.lower().str.endswith(tuple(IMAGE_EXTS))
        is_video = df["SourceFile"].str.lower().str.endswith(tuple(VIDEO_EXTS))
        if media_filter == "Nur Bilder":
            mask &= is_image
        elif media_filter == "Nur Videos":
            mask &= is_video

    return df[mask]

from moviepy import VideoFileClip

def get_video_duration(path: str) -> float:
    try:
        with VideoFileClip(path) as clip:
            return clip.duration or 0
    except Exception:
        return 0

from PIL import Image

def load_and_scale_image(path, max_width=600, max_height=400):
    img = Image.open(path)
    img.thumbnail((max_width, max_height), Image.LANCZOS)
    return img

from pathlib import Path

def get_media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"


import streamlit as st

def reset_all_filters():
    # Alle Widget-Keys im Session State löschen
    for key in list(st.session_state.keys()):
        if any(s in key for s in ["_year", "_month", "_weekday", "_hour", "_range", "_cat"]):
            del st.session_state[key]

    # Filter-Dictionary leeren
    st.session_state.filters = {}
    st.session_state.media_type_filter = "Alle Medien"

    # Seite neu laden, damit Widgets ihre Defaults annehmen
    st.rerun()