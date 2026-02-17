# Fortnox Transaction Statement Converter

A simple web tool that converts transaction statements from various sources into the CSV format that Fortnox accepts for bank reconciliation ("Stäm av konto").

## What it does

1. **Upload** a CSV or Excel file with transactions (e.g. from Pleo, Mynt, Revolut, or any other source)
2. **Map columns** — drag and drop your file's columns to match the three Fortnox fields (Datum, Beskrivning, Belopp). Save mappings as presets so you don't have to redo this each time.
3. **Handle currencies** — for non-SEK transactions, the app automatically fetches the closing FX rate from Riksbanken for the previous month-end. You can override with a manual rate if needed.
4. **Filter by date** — narrow down which rows to include in the export
5. **Download** — get a ready-to-import Fortnox CSV file

## Pre-configured presets

- Mynt (Settlement Date)
- Pleo
- Pleo (Running Balance Statement)
- Revolut

You can also save your own presets for other sources.

## How to run

```
cd C:\FortnoxAccountReconciliation
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
