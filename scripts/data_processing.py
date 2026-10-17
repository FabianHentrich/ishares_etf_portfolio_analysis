# data_processing.py

import logging
import os
import re
import unicodedata

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_str(s) -> str:
    """Entfernt non-printable/Whitespace-Artefakte und normalisiert Unicode (NFC)."""
    if not isinstance(s, str):
        return s
    s = unicodedata.normalize("NFC", s)
    s = s.replace("\xa0", "").replace("\u200b", "").strip()
    return s


# Tatsächliche Sektornamen aus den iShares-CSVs → einheitliche deutsche Bezeichnungen
SECTOR_MAPPING = {
    # Englische Originalbezeichnungen
    "Information Technology": "Technologie",
    "Financials": "Finanzen",
    "Finanzwesen": "Finanzen",  # iShares-CSV-Bezeichnung seit Website-Umstellung 2026
    "Health Care": "Gesundheit",
    "Consumer Discretionary": "Zyklischer Konsum",
    "Consumer Staples": "Basiskonsumgüter",
    "Communication Services": "Kommunikation",
    "Industrials": "Industrie",
    "Energy": "Energie",
    "Materials": "Rohstoffe",
    "Real Estate": "Immobilien",
    "Utilities": "Versorger",
    # Deutsche Bezeichnungen aus iShares-CSVs (nach _normalize_str bereits bereinigt)
    "IT": "Technologie",
    "Gesundheitsversorgung": "Gesundheit",
    "Zyklische Konsumgüter": "Zyklischer Konsum",
    "Zyklische Konsumgter": "Zyklischer Konsum",
    "Nichtzyklische Konsumgüter": "Basiskonsumgüter",
    "Nichtzyklische Konsumgter": "Basiskonsumgüter",
    "Materialien": "Rohstoffe",
}

LOCATION_MAPPING = {
    "United States": "USA",
    "Vereinigte Staaten": "USA",
    "United Kingdom": "Großbritannien",
    "Vereinigtes Königreich": "Großbritannien",
    "Vereinigtes Knigreich": "Großbritannien",
    "Grobritannien": "Großbritannien",  # Encoding-Variante (fehlendes ß+i)
    "Germany": "Deutschland",
    # Türkei
    "Türkei": "Türkei",
    "Trkei": "Türkei",
    # Südafrika
    "Südafrika": "Südafrika",
    "Sdafrika": "Südafrika",
    # Österreich
    "Österreich": "Österreich",
    "sterreich": "Österreich",
    # Ägypten
    "Ägypten": "Ägypten",
    "gypten": "Ägypten",
    # Dänemark
    "Dänemark": "Dänemark",
    "Dnemark": "Dänemark",
    # Europäische Union
    "Europäische Union": "EU",
    "Europische Union": "EU",
    # Tschechien
    "Tschechien": "Tschechien",
    "Tschechische Republik": "Tschechien",
}

# Anlageklassen, die aus ETF-Positionen herausgefiltert werden sollen
_EXCLUDED_ASSET_CLASSES = {"FX", "Futures", "Cash", "Cash und/oder Derivate", "Cash and/or Derivatives"}
# Sektoren die als zweite Sicherheitsstufe gefiltert werden
_EXCLUDED_SECTORS = {"Cash und/oder Derivate", "Cash and/or Derivatives", "FX"}

# Öffentliche Filterkonstanten – auch in main.py für Chart-DataFrames verwendet
# (zentral hier definiert, um Duplikation zu vermeiden)
EXCL_SECTORS = {"-", "nan", "Cash und/oder Derivate", "Cash and/or Derivatives"}
EXCL_LOCATIONS = {"-", "nan", "Krypto", "Cash", "Cash (Euro)"}


def clean_etf_data(df):
    """
    Bereinigt ETF-Daten aus iShares-CSVs:
    - Entfernt NaN-Zeilen, 0%-Zeilen und Cash/Derivate-Einträge
    - Normalisiert Sektor- und Ländernamen (inkl. Encoding-Artefakte)
    """
    df = df.copy()  # Kein Mutieren des übergebenen DataFrames
    df["ETF"] = df["ETF"].apply(
        lambda x: (
            os.path.splitext(os.path.basename(str(x)))[0]
            if (os.sep in str(x) or "/" in str(x) or str(x).endswith(".csv"))
            else str(x)
        )
    )

    # Encoding-Artefakte aus Text-Spalten entfernen und Unicode normalisieren
    for col in ["Sektor", "Standort", "Name"]:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_str)
            df[col] = df[col].replace("nan", pd.NA).replace("", pd.NA)

    df["Gewichtung (%)"] = df["Gewichtung (%)"].astype(str).str.replace(",", ".", regex=False)
    df["Gewichtung (%)"] = pd.to_numeric(df["Gewichtung (%)"], errors="coerce")

    # Zeilen ohne Name oder Gewichtung und Zeilen mit Gewichtung ≤ 0 entfernen
    df = df.dropna(subset=["Name", "Gewichtung (%)"])
    df = df[df["Gewichtung (%)"] > 0].copy()

    # Nach Anlageklasse filtern – nur echte Aktien behalten (falls Spalte vorhanden)
    if "Anlageklasse" in df.columns:
        df["Anlageklasse"] = df["Anlageklasse"].astype(str).str.replace("\xa0", "", regex=False).str.strip()
        df = df[~df["Anlageklasse"].isin(_EXCLUDED_ASSET_CLASSES)].copy()
        df = df[df["Anlageklasse"].str.lower() == "aktien"].copy()

    # Cash/Derivate-Zeilen nach Sektor ausschließen (zweite Sicherheitsstufe)
    df = df[~df["Sektor"].isin(_EXCLUDED_SECTORS)].copy()
    df = df[df["Sektor"].notna()].copy()

    # Sektor- und Länder-Normalisierung
    df["Sektor"] = df["Sektor"].replace(SECTOR_MAPPING)
    df["Standort"] = df["Standort"].replace(LOCATION_MAPPING)

    # Sektoren: Die Zielwerte des Mappings sind die vollständige Sektorliste.
    # Alles, was danach nicht darin liegt, ist unbekannt → WARNING + 'Sonstige'
    # (sonst entstünden still doppelte Kategorien wie 'Finanzwesen' neben 'Finanzen').
    unk_s_mask = df["Sektor"].notna() & ~df["Sektor"].isin(set(SECTOR_MAPPING.values()))
    if unk_s_mask.any():
        unk_vals = df.loc[unk_s_mask, "Sektor"].value_counts().to_dict()
        logger.warning(f"Nicht aufgelöste Sektoren → 'Sonstige' (SECTOR_MAPPING ergänzen): {unk_vals}")
    df.loc[unk_s_mask, "Sektor"] = "Sonstige"

    # Länder: keine abschließende Liste – unbekannte Länder bleiben erhalten.
    # Nur Encoding-Artefakte (Ersatzzeichen) werden gemeldet, damit das Mapping ergänzt werden kann.
    bad_l_mask = df["Standort"].notna() & df["Standort"].astype(str).str.contains("�", regex=False)
    if bad_l_mask.any():
        bad_vals = df.loc[bad_l_mask, "Standort"].value_counts().to_dict()
        logger.warning(f"Länder mit Encoding-Fehlern (LOCATION_MAPPING ergänzen): {bad_vals}")

    # Leere Strings nach allen Operationen auffangen
    df["Sektor"] = df["Sektor"].replace("", pd.NA)
    df["Standort"] = df["Standort"].replace("", pd.NA)

    logger.info(f"ETF-Daten bereinigt: {len(df)} verwertbare Positionen (ohne Cash/Derivate/0%-Zeilen).")
    return df


# Rechtsform-/Gattungszusätze, die beim Namensabgleich Einzelaktie ↔ ETF-Position ignoriert werden
_NAME_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "SE", "AG", "SA",
    "NV", "AS", "ASA", "AB", "SPA", "OYJ", "KGAA", "HOLDING", "HOLDINGS", "GROUP",
}  # fmt: skip


def _name_key(name) -> str:
    """Normalisierter Vergleichsschlüssel für Firmennamen.

    'NVIDIA Corp.' → 'NVIDIA', 'Novo Nordisk A/S' → 'NOVO NORDISK', 'NOVO NORDISK CLASS B' → 'NOVO NORDISK'
    """
    if not isinstance(name, str):
        return ""
    s = _normalize_str(name).upper()
    s = re.sub(r"[./']", "", s)  # N.V. → NV, A/S → AS
    s = re.sub(r"[^A-Z0-9&]+", " ", s)
    s = re.sub(r"\bCLASS [A-Z]\b", " ", s)
    tokens = s.split()
    # Zusätze nur am Ende entfernen, mindestens ein Token bleibt stehen
    while len(tokens) > 1 and (tokens[-1] in _NAME_SUFFIXES or len(tokens[-1]) == 1):
        tokens.pop()
    return " ".join(tokens)


def resolve_stock_names(depot, etf_names):
    """
    Ermittelt für jede Einzelaktie im Depot den Namen, unter dem sie in den ETF-CSVs geführt wird –
    damit Direktbesitz und ETF-Anteil im Durchblick zu EINER Position zusammengefasst werden.

    Reihenfolge:
    1. Optionale Spalte 'ETF-Name' in der Depot-Excel (manuelle Zuordnung, hat Vorrang)
    2. Exakt gleicher Name in den ETF-Daten
    3. Automatischer Abgleich über _name_key – nur bei eindeutigem Treffer

    :param depot: Depot-DataFrame mit Spalten 'Art', 'Position' (optional 'ETF-Name')
    :param etf_names: Iterable aller Positionsnamen aus den ETF-CSVs
    :return: Series (Index wie depot) mit dem zu verwendenden Namen; für Nicht-Aktien = 'Position'
    """
    etf_names = {n for n in etf_names if isinstance(n, str)}
    by_key: dict[str, set] = {}
    for n in etf_names:
        by_key.setdefault(_name_key(n), set()).add(n)

    names = depot["Position"].copy()
    has_manual = "ETF-Name" in depot.columns

    for idx, row in depot[depot["Art"] == "Aktie"].iterrows():
        position = row["Position"]
        manual = _normalize_str(row["ETF-Name"]) if has_manual else None
        if isinstance(manual, str) and manual not in ("", "-"):
            names.at[idx] = manual
            if manual not in etf_names:
                logger.warning(f"ETF-Name '{manual}' für '{position}' kommt in keiner ETF-CSV vor – bitte prüfen.")
            continue
        if position in etf_names:
            continue
        candidates = by_key.get(_name_key(position), set())
        if len(candidates) == 1:
            match = next(iter(candidates))
            names.at[idx] = match
            # Kein '→' im Log: Windows-Konsole (cp1252) kann es nicht ausgeben
            logger.info(f"Einzelaktie '{position}' -> ETF-Position '{match}' zugeordnet (Namensabgleich).")
        elif len(candidates) > 1:
            logger.warning(
                f"Einzelaktie '{position}' passt zu mehreren ETF-Positionen {sorted(candidates)} – "
                f"keine automatische Zuordnung. Bitte Spalte 'ETF-Name' in der Depot-Excel setzen."
            )
    return names


def calculate_relative_weighting(etf_stocks, depot_components):
    """
    Berechnet die relative Gewichtung der ETF-Einzelpositionen im Gesamtdepot.

    :param etf_stocks: DataFrame mit ETF-Positionen und ihrer Gewichtung innerhalb des ETFs
    :param depot_components: DataFrame mit den Depot-Positionen und ihrem Marktwertanteil
    :return: Tuple (DataFrame mit ergänzter Spalte 'relative Gewichtung (%)', Zusammenfassungs-String)
    """
    if "Marktwert (%)" not in depot_components.columns:
        raise KeyError("'Marktwert (%)' column is missing from depot_components DataFrame.")
    if etf_stocks.empty:
        raise ValueError("The input dataframe 'etf_stocks' is empty.")
    if depot_components.empty:
        raise ValueError("The input dataframe 'depot_components' is empty.")

    required_columns_etf_stocks = ["ETF", "Gewichtung (%)"]
    for column in required_columns_etf_stocks:
        if column not in etf_stocks.columns:
            raise ValueError(f"'etf_stocks' fehlt die Spalte '{column}'.")

    required_columns_depot_components = ["Art", "Position", "Marktwert (%)"]
    for column in required_columns_depot_components:
        if column not in depot_components.columns:
            raise ValueError(f"'depot_components' fehlt die Spalte '{column}'.")

    etfs = depot_components.loc[depot_components["Art"] == "ETF", "Position"].unique()
    logger.info(f"ETFs im Depot: {etfs}")

    # Kopie erstellen – kein In-Place-Mutieren des übergebenen DataFrames
    etf_stocks = etf_stocks.copy()

    # Spalte vorab mit 0 initialisieren – so existiert sie auch wenn kein ETF gemappt wurde
    if "relative Gewichtung (%)" not in etf_stocks.columns:
        etf_stocks["relative Gewichtung (%)"] = 0.0

    for etf_name in etfs:
        if etf_name not in etf_stocks["ETF"].unique():
            available = etf_stocks["ETF"].unique().tolist()
            logger.warning(
                f"ETF '{etf_name}' nicht in ETF-CSV-Daten gefunden – übersprungen. Verfügbare ETFs: {available}"
            )
            continue

        mask = (depot_components["Art"] == "ETF") & (depot_components["Position"] == etf_name)
        # Derselbe ETF kann in mehreren Zeilen stehen (z.B. in zwei Depots) → Gewichte addieren
        etf_weight = depot_components.loc[mask, "Marktwert (%)"].sum()
        if mask.sum() > 1:
            logger.info(f"ETF '{etf_name}' steht in {mask.sum()} Depot-Zeilen – Gewichte werden addiert.")

        if etf_weight <= 0:
            logger.warning(f"ETF '{etf_name}' hat Depotgewicht {etf_weight:.4f}% – kein Kurs? Gewichtung wird 0.")

        etf_stocks.loc[etf_stocks["ETF"] == etf_name, "relative Gewichtung (%)"] = (
            etf_stocks.loc[etf_stocks["ETF"] == etf_name, "Gewichtung (%)"] * etf_weight / 100
        )
        logger.info(f"ETF '{etf_name}' erfolgreich verarbeitet (Depotgewicht: {etf_weight:.2f}%).")

    total_relative_weighting = etf_stocks["relative Gewichtung (%)"].sum()
    message = f"Relative Gewichtung erfolgreich berechnet. ETF-Anteil im Depot: {round(total_relative_weighting, 2)}%."
    return etf_stocks, message
