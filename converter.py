"""Data transformation and Fortnox CSV export."""

import io
import pandas as pd


def _parse_numeric(series: pd.Series) -> pd.Series:
    """Parse a string series into numeric, handling Unicode minus, Swedish decimals, etc."""
    return pd.to_numeric(
        series
        .astype(str)
        .str.replace("\u2212", "-", regex=False)  # Unicode minus → hyphen-minus
        .str.replace("\u2013", "-", regex=False)  # en-dash → hyphen-minus
        .str.replace("\xa0", "", regex=False)     # non-breaking space
        .str.replace(" ", "", regex=False)        # regular space
        .str.replace(",", ".", regex=False),      # Swedish decimal -> Python float
        errors="coerce",
    )


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
                 Optional key "Fee" for a fee column to subtract.
        fx_rate: If set, multiply Belopp by this rate (foreign currency -> SEK).

    Returns:
        DataFrame with columns [Datum, Beskrivning, Belopp].
        Belopp = (amount - fee) * fx_rate
    """
    result = pd.DataFrame()

    result["Datum"] = pd.to_datetime(
        df[mapping["Datum"]], dayfirst=True, format="mixed"
    ).dt.strftime("%Y-%m-%d")
    result["Beskrivning"] = df[mapping["Beskrivning"]].astype(str).str.strip()

    belopp = _parse_numeric(df[mapping["Belopp"]])

    if "Fee" in mapping and mapping["Fee"]:
        fee = _parse_numeric(df[mapping["Fee"]]).fillna(0)
        belopp = belopp - fee.abs()

    if fx_rate is not None and fx_rate != 1.0:
        belopp = belopp * fx_rate

    result["Belopp"] = belopp

    return result


def export_csv(df: pd.DataFrame) -> bytes:
    """Export DataFrame as Fortnox-compatible CSV bytes.

    Format: semicolon-separated, Swedish decimals (comma),
    UTF-8 with BOM, Windows line endings (CRLF).
    """
    lines = ["Datum;Ingående saldo-Beskrivning;Belopp"]

    for _, row in df.iterrows():
        datum = row["Datum"]
        beskrivning = str(row["Beskrivning"]).replace(";", ",")[:100]  # escape semicolons, max 100 chars
        belopp = f"{row['Belopp']:.2f}".replace(".", ",")
        lines.append(f"{datum};{beskrivning};{belopp}")

    lines.append("This will not be imported")

    content = "\r\n".join(lines) + "\r\n"
    return b"\xef\xbb\xbf" + content.encode("utf-8")
