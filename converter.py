"""Data transformation and Fortnox CSV export."""

import io
import pandas as pd


def transform_data(
    df: pd.DataFrame,
    mapping: dict[str, str],
    fx_rate: float | None = None,
) -> pd.DataFrame:
    """Transform source data using column mapping and optional FX conversion.

    Args:
        df: Source DataFrame from uploaded file.
        mapping: Dict mapping Fortnox field -> source column name,
                 e.g. {"Datum": "Date", "Beskrivning": "Text", "Belopp": "Amount"}
        fx_rate: If set, multiply Belopp by this rate (foreign currency -> SEK).

    Returns:
        DataFrame with columns [Datum, Beskrivning, Belopp].
    """
    result = pd.DataFrame()

    result["Datum"] = pd.to_datetime(df[mapping["Datum"]], dayfirst=False).dt.strftime(
        "%Y-%m-%d"
    )
    result["Beskrivning"] = df[mapping["Beskrivning"]].astype(str).str.strip()

    belopp = pd.to_numeric(
        df[mapping["Belopp"]]
        .astype(str)
        .str.replace("\xa0", "", regex=False)   # non-breaking space
        .str.replace(" ", "", regex=False)       # regular space
        .str.replace(",", ".", regex=False),     # Swedish decimal -> Python float
        errors="coerce",
    )

    if fx_rate is not None and fx_rate != 1.0:
        belopp = belopp * fx_rate

    result["Belopp"] = belopp

    return result


def export_csv(df: pd.DataFrame) -> str:
    """Export DataFrame as Fortnox-compatible CSV string.

    Format: semicolon-separated, Swedish decimals (comma), UTF-8.
    """
    buf = io.StringIO()
    buf.write("Datum;Beskrivning;Belopp\n")

    for _, row in df.iterrows():
        datum = row["Datum"]
        beskrivning = str(row["Beskrivning"]).replace(";", ",")  # escape semicolons
        belopp = f"{row['Belopp']:.2f}".replace(".", ",")
        buf.write(f"{datum};{beskrivning};{belopp}\n")

    return buf.getvalue()
