# attribute_types.py

from datetime import datetime
from typing import Dict
# attribute_types.py

# attribute_types.py

import pandas as pd
from datetime import datetime
import re

KNOWN_DATETIME_FORMATS = [
    # ExifTool ohne Subsekunden
    "%Y:%m:%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S%z",

    # ExifTool mit Subsekunden
    "%Y:%m:%d %H:%M:%S.%f",
    "%Y:%m:%d %H:%M:%S.%f%z",

    # ISO-ähnlich
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S.%f%z",

    # Datum-only
    "%Y-%m-%d",
    "%Y:%m:%d",
]

YEAR_REGEX = re.compile(r"\b(19|20)\d{2}\b")


def is_datetime_value(value) -> bool:
    if value is None or not isinstance(value, str):
        return False

    v = value.strip()
    if not v:
        return False

    # schneller Vorfilter
    if not YEAR_REGEX.search(v):
        return False

    # bekannte Formate
    for fmt in KNOWN_DATETIME_FORMATS:
        try:
            datetime.strptime(v, fmt)
            return True
        except Exception:
            pass

    # pandas-Fallback
    try:
        pd.to_datetime(v, errors="raise", infer_datetime_format=True)
        return True
    except Exception:
        return False

# -------------------------------
# Attribut-Typ bestimmen
# -------------------------------

def infer_attribute_type(
    series: pd.Series,
    sample_size: int = 200,
    min_numeric_unique: int = 10,
    datetime_threshold: float = 0.7,  # ← neu
) -> str:

    non_null = series.dropna()
    if non_null.empty:
        return "categorical"

    sample = (
        non_null.sample(sample_size, random_state=42)
        if len(non_null) > sample_size
        else non_null
    )

    # --- Zeit prüfen (mit Schwelle) ---
    datetime_hits = sum(is_datetime_value(v) for v in sample)
    if datetime_hits / len(sample) >= datetime_threshold:
        return "datetime"

    # --- Numerisch ---
    if pd.api.types.is_numeric_dtype(non_null):
        if non_null.nunique() > min_numeric_unique:
            return "numeric"

    return "categorical"


# -------------------------------
# Alle Attribute klassifizieren
# -------------------------------

def infer_all_attribute_types(
    df: pd.DataFrame,
    sample_size: int = 200
) -> Dict[str, str]:
    """
    Liefert dict: {attributname: typ}
    """
    types = {}

    for col in df.columns:
        try:
            types[col] = infer_attribute_type(
                df[col],
                sample_size=sample_size
            )
        except Exception:
            types[col] = "categorical"

    return types
