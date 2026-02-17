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

st.set_page_config(page_title="Fortnox Kontoutdrag", page_icon="📊", layout="wide")
st.title("📊 Fortnox Kontoutdrag-konvertering")
st.caption("Konvertera bankutdrag till Fortnox importformat (Datum;Beskrivning;Belopp)")

# ── Step 1: File upload ─────────────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "Ladda upp bankutdrag",
    type=["csv", "xlsx", "xls"],
    help="CSV eller Excel-fil med banktransaktioner",
)

if uploaded_file is None:
    st.info("Ladda upp en CSV- eller Excel-fil för att komma igång.")
    st.stop()

# Read file into DataFrame
try:
    if uploaded_file.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        # Try common CSV delimiters
        content = uploaded_file.getvalue().decode("utf-8", errors="replace")
        for sep in [";", ",", "\t"]:
            df = pd.read_csv(
                pd.io.common.StringIO(content), sep=sep, dtype=str
            )
            if len(df.columns) > 1:
                break
except Exception as e:
    st.error(f"Kunde inte läsa filen: {e}")
    st.stop()

source_columns = list(df.columns)

st.subheader("Förhandsvisning av källdata")
st.dataframe(df.head(10), use_container_width=True)

# ── Step 2: Currency & FX rate ──────────────────────────────────────────────

st.subheader("Valuta")
col_curr, col_rate = st.columns(2)

with col_curr:
    currency_options = ["SEK"] + get_available_currencies()
    currency = st.selectbox("Källvaluta", currency_options, index=0)

fx_rate = None
if currency != "SEK":
    with col_rate:
        ref_date = st.date_input(
            "Referensdatum (kurs hämtas för föregående månadsslut)",
            value=date.today(),
        )
        auto_rate = get_fx_rate(currency, ref_date)

        if auto_rate:
            st.info(f"Riksbanken-kurs {currency}/SEK: **{auto_rate:.4f}**")
        else:
            st.warning(f"Kunde inte hämta kurs för {currency}.")

        manual_rate = st.text_input(
            "Manuell kurs (lämna tom för Riksbanken-kurs)",
            value="",
            help="Ange kurs som t.ex. 11,4325 eller 11.4325",
        )

        if manual_rate.strip():
            try:
                fx_rate = float(manual_rate.replace(",", "."))
                st.success(f"Använder manuell kurs: **{fx_rate:.4f}**")
            except ValueError:
                st.error("Ogiltig kurs — ange ett tal.")
                st.stop()
        elif auto_rate:
            fx_rate = auto_rate
        else:
            st.error("Ingen kurs tillgänglig. Ange en manuell kurs.")
            st.stop()

# ── Step 3: Column mapping (drag-and-drop) ──────────────────────────────────

st.subheader("Kolumnmappning")

# Load presets
presets = _load_presets()
preset_names = ["(Ingen förvald)"] + [p["name"] for p in presets]
selected_preset = st.selectbox("Välj förvald mappning", preset_names)

# Initialize mapping from preset or empty
initial_mapping = {}
if selected_preset != "(Ingen förvald)":
    preset = next((p for p in presets if p["name"] == selected_preset), None)
    if preset:
        initial_mapping = preset.get("mapping", {})

# Build sortable items: each Fortnox field is a bucket, plus "Available" bucket
# If preset loaded, pre-assign columns; otherwise all in Available
assigned = {}
available = list(source_columns)

for field in FORTNOX_FIELDS:
    preset_col = initial_mapping.get(field, "")
    if preset_col and preset_col in available:
        assigned[field] = [preset_col]
        available.remove(preset_col)
    else:
        assigned[field] = []

# Build the items structure for streamlit-sortables
items = [
    {"header": "Tillgängliga kolumner", "items": available},
]
for field in FORTNOX_FIELDS:
    items.append({"header": field, "items": assigned[field]})

st.caption("Dra kolumnnamn från 'Tillgängliga kolumner' till rätt Fortnox-fält.")

sorted_items = sort_items(items, multi_containers=True, direction="horizontal")

# Parse results back into a mapping dict
mapping = {}
mapping_complete = True
for group in sorted_items:
    header = group["header"] if isinstance(group, dict) else None
    group_items = group["items"] if isinstance(group, dict) else group

    if header in FORTNOX_FIELDS:
        if len(group_items) == 1:
            mapping[header] = group_items[0]
        elif len(group_items) == 0:
            mapping_complete = False
        else:
            st.warning(f"**{header}** kan bara ha en kolumn. Ta bort extra.")
            mapping_complete = False

if not mapping_complete:
    st.warning("Alla tre Fortnox-fält måste ha exakt en kolumn mappad.")

# Save preset
with st.expander("Spara som ny förvald mappning"):
    new_preset_name = st.text_input("Namn på mappning", key="new_preset_name")
    if st.button("Spara") and new_preset_name.strip() and mapping_complete:
        new_preset = {"name": new_preset_name.strip(), "mapping": mapping}
        # Replace if name exists, otherwise append
        presets = [p for p in presets if p["name"] != new_preset_name.strip()]
        presets.append(new_preset)
        _save_presets(presets)
        st.success(f"Mappning '{new_preset_name}' sparad!")
        st.rerun()

# ── Step 4: Transform & preview ─────────────────────────────────────────────

if mapping_complete and len(mapping) == 3:
    st.subheader("Förhandsvisning av resultat")
    try:
        result_df = transform_data(df, mapping, fx_rate)
        st.dataframe(result_df.head(20), use_container_width=True)

        # ── Step 5: Export ──────────────────────────────────────────────────
        csv_str = export_csv(result_df)
        file_name = f"Fortnox_import_{date.today().isoformat()}.csv"

        st.download_button(
            label="⬇️ Ladda ner Fortnox CSV",
            data=csv_str.encode("utf-8"),
            file_name=file_name,
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Fel vid konvertering: {e}")
