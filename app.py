"""Fortnox Account Reconciliation — Streamlit App.

Converts bank statement files (CSV/Excel) into Fortnox-compatible CSV format
for bank reconciliation (Stäm av konto).
"""

import os
from datetime import date

import pandas as pd
import yaml
import streamlit as st
from streamlit_sortables import sort_items

from riksbanken import get_available_currencies, get_fx_rate
from converter import transform_data, export_csv

PRESETS_PATH = os.path.join(os.path.dirname(__file__), "presets.yaml")
FORTNOX_FIELDS = ["Datum", "Beskrivning", "Belopp"]
OPTIONAL_FIELDS = ["Fee"]
ALL_MAPPING_FIELDS = FORTNOX_FIELDS + OPTIONAL_FIELDS
DISPLAY_NAMES = {"Datum": "Date", "Beskrivning": "Description", "Belopp": "Amount", "Fee": "Fee"}


# ── Preset helpers ──────────────────────────────────────────────────────────

def _load_presets() -> list[dict]:
    try:
        with open(PRESETS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("presets", [])
    except FileNotFoundError:
        return []


def _save_presets(presets: list[dict]) -> None:
    with open(PRESETS_PATH, "w", encoding="utf-8") as f:
        yaml.dump({"presets": presets}, f, allow_unicode=True, default_flow_style=False)


# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Fortnox Transaction Statement Converter", page_icon="📊", layout="wide")
st.title("📊 Fortnox Transaction Statement Converter")
st.caption("Convert transaction statements to Fortnox import format (Datum;Beskrivning;Belopp)")

# ── Step 1: File upload ─────────────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Upload transaction statement",
    type=["csv", "xlsx", "xls"],
    help="CSV or Excel file with transactions",
)

if uploaded_file is None:
    st.info("Upload a CSV or Excel file with transactions to get started.")
    st.stop()

# Read file into DataFrame
try:
    if uploaded_file.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        # Try common CSV delimiters, use python engine for robustness
        content = uploaded_file.getvalue().decode("utf-8", errors="replace")
        best_df = None
        for sep in [";", ",", "\t"]:
            try:
                candidate = pd.read_csv(
                    pd.io.common.StringIO(content),
                    sep=sep,
                    dtype=str,
                    engine="python",
                    on_bad_lines="skip",
                )
                if best_df is None or len(candidate.columns) > len(best_df.columns):
                    best_df = candidate
                if len(candidate.columns) > 1:
                    break
            except Exception:
                continue
        if best_df is not None:
            df = best_df
        else:
            raise ValueError("Could not parse CSV with any common delimiter.")
except Exception as e:
    st.error(f"Could not read file: {e}")
    st.stop()

source_columns = list(df.columns)

st.subheader("Source data preview")
st.dataframe(df.head(10), use_container_width=True)

# ── Step 2: Column mapping (drag-and-drop) ──────────────────────────────────

st.subheader("Column mapping")

# Load presets
presets = _load_presets()
preset_names = ["(No preset)"] + [p["name"] for p in presets]
selected_preset = st.selectbox("Select preset mapping", preset_names)

# Initialize mapping from preset or empty
initial_mapping = {}
if selected_preset != "(No preset)":
    preset = next((p for p in presets if p["name"] == selected_preset), None)
    if preset:
        initial_mapping = preset.get("mapping", {})

# Build sortable items: each Fortnox field is a bucket, plus "Available" bucket
# If preset loaded, pre-assign columns; otherwise all in Available
assigned = {}
available = list(source_columns)

for field in ALL_MAPPING_FIELDS:
    preset_col = initial_mapping.get(field, "")
    if preset_col and preset_col in available:
        assigned[field] = [preset_col]
        available.remove(preset_col)
    else:
        assigned[field] = []

# Build the items structure for streamlit-sortables using display names
display_to_internal = {v: k for k, v in DISPLAY_NAMES.items()}
items = [
    {"header": "Available columns", "items": available},
]
for field in ALL_MAPPING_FIELDS:
    items.append({"header": DISPLAY_NAMES[field], "items": assigned[field]})

st.caption("Drag column names from 'Available columns' to the correct field. Fee is optional — if mapped, Amount = (Amount − Fee) × FX rate.")

sorted_items = sort_items(items, multi_containers=True, direction="horizontal")

# Parse results back into a mapping dict (convert display names back to internal)
required_display = {DISPLAY_NAMES[f] for f in FORTNOX_FIELDS}
optional_display = {DISPLAY_NAMES[f] for f in OPTIONAL_FIELDS}
mapping = {}
mapping_complete = True
for group in sorted_items:
    header = group["header"] if isinstance(group, dict) else None
    group_items = group["items"] if isinstance(group, dict) else group
    internal = display_to_internal.get(header)

    if header in required_display:
        if len(group_items) == 1:
            mapping[internal] = group_items[0]
        elif len(group_items) == 0:
            mapping_complete = False
        else:
            st.warning(f"**{header}** can only have one column. Remove extras.")
            mapping_complete = False
    elif header in optional_display:
        if len(group_items) == 1:
            mapping[internal] = group_items[0]
        elif len(group_items) > 1:
            st.warning(f"**{header}** can only have one column. Remove extras.")

if not mapping_complete:
    st.warning("Date, Description and Amount must each have exactly one column mapped. Fee is optional.")

# Save preset
with st.expander("Save as new preset"):
    new_preset_name = st.text_input("Preset name", key="new_preset_name")
    if st.button("Save") and new_preset_name.strip() and mapping_complete:
        new_preset = {"name": new_preset_name.strip(), "mapping": mapping}
        # Replace if name exists, otherwise append
        presets = [p for p in presets if p["name"] != new_preset_name.strip()]
        presets.append(new_preset)
        _save_presets(presets)
        st.success(f"Preset '{new_preset_name}' saved!")
        st.rerun()

if not mapping_complete:
    st.stop()

# ── Step 3: Currency & FX rate ──────────────────────────────────────────────

# Determine default reference date from the mapped date column
try:
    file_max_date = pd.to_datetime(df[mapping["Datum"]], dayfirst=True).max().date()
except Exception:
    file_max_date = date.today()

st.subheader("Currency")
col_curr, col_rate = st.columns(2)

with col_curr:
    currency_options = ["SEK"] + get_available_currencies()
    currency = st.selectbox("Source currency", currency_options, index=0)

fx_rate = None
if currency != "SEK":
    with col_rate:
        ref_date = st.date_input(
            "Reference date (rate fetched for previous month-end)",
            value=file_max_date,
        )
        auto_rate, rate_date = get_fx_rate(currency, ref_date)

        if auto_rate:
            st.info(f"Riksbanken rate {currency}/SEK: **{auto_rate:.4f}** (from {rate_date})")
        else:
            st.warning(f"Could not fetch rate for {currency}.")

        manual_rate = st.text_input(
            "Manual rate (leave empty to use Riksbanken rate)",
            value="",
            help="Enter rate e.g. 11.4325 or 11,4325",
        )

        if manual_rate.strip():
            try:
                fx_rate = float(manual_rate.replace(",", "."))
                st.success(f"Using manual rate: **{fx_rate:.4f}**")
            except ValueError:
                st.error("Invalid rate — enter a number.")
                st.stop()
        elif auto_rate:
            fx_rate = auto_rate
        else:
            st.error("No rate available. Enter a manual rate.")
            st.stop()

# ── Step 4: Transform, filter & preview ──────────────────────────────────────

try:
    result_df = transform_data(df, mapping, fx_rate)

    # Date range filter
    st.subheader("Date filter")
    dates = pd.to_datetime(result_df["Datum"])
    min_date = dates.min().date()
    max_date = dates.max().date()

    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input("From date", value=min_date, min_value=min_date, max_value=max_date)
    with col_to:
        date_to = st.date_input("To date", value=max_date, min_value=min_date, max_value=max_date)

    # Apply filter
    mask = (dates >= pd.Timestamp(date_from)) & (dates <= pd.Timestamp(date_to))
    filtered_df = result_df[mask].reset_index(drop=True)

    st.subheader(f"Output preview ({len(filtered_df)} rows)")
    st.dataframe(filtered_df.head(20), use_container_width=True)

    # ── Step 5: Export ──────────────────────────────────────────────────
    csv_bytes = export_csv(filtered_df)
    preset_label = selected_preset.split(" - ")[0].strip() if selected_preset != "(No preset)" else "Custom"
    file_name = f"{preset_label}-{currency}-{date_from.isoformat()}-{date_to.isoformat()}.csv"

    st.download_button(
        label="⬇️ Download Fortnox CSV",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
    )
except Exception as e:
    st.error(f"Conversion error: {e}")
