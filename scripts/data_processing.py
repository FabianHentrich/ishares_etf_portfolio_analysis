# data_processing.py

import logging
import os
import unicodedata

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_str(s) -> str:
    """Entfernt non-printable/Whitespace-Artefakte und normalisiert Unicode (NFC)."""
    if not isinstance(s, str):
        return s
    s = unicodedata.normalize('NFC', s)
    s = s.replace('\xa0', '').replace('\u200b', '').strip()
    return s

# Tatsächliche Sektornamen aus den iShares-CSVs → einheitliche deutsche Bezeichnungen
SECTOR_MAPPING = {
    # Englische Originalbezeichnungen
    "Information Technology": "Technologie",
    "Financials":             "Finanzen",
    "Health Care":            "Gesundheit",
    "Consumer Discretionary": "Zyklischer Konsum",
    "Consumer Staples":       "Basiskonsumgüter",
    "Communication Services": "Kommunikation",
    "Industrials":            "Industrie",
    "Energy":                 "Energie",
    "Materials":              "Rohstoffe",
    "Real Estate":            "Immobilien",
    "Utilities":              "Versorger",
    # Deutsche Bezeichnungen aus iShares-CSVs (nach _normalize_str bereits bereinigt)
    "IT":                          "Technologie",
    "Gesundheitsversorgung":       "Gesundheit",
    "Zyklische Konsumgüter":       "Zyklischer Konsum",
    "Zyklische Konsumgter":        "Zyklischer Konsum",
    "Nichtzyklische Konsumgüter":  "Basiskonsumgüter",
    "Nichtzyklische Konsumgter":   "Basiskonsumgüter",
    "Materialien":                 "Rohstoffe",
}

LOCATION_MAPPING = {
    "United States": "USA",
    "Vereinigte Staaten": "USA",
    "United Kingdom": "Großbritannien",
    "Vereinigtes Königreich": "Großbritannien",
    "Vereinigtes Knigreich": "Großbritannien",
    "Grobritannien": "Großbritannien",       # Encoding-Variante (fehlendes ß+i)
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
_EXCLUDED_ASSET_CLASSES = {'FX', 'Futures', 'Cash', 'Cash und/oder Derivate', 'Cash and/or Derivatives'}
# Sektoren die als zweite Sicherheitsstufe gefiltert werden
_EXCLUDED_SECTORS = {'Cash und/oder Derivate', 'Cash and/or Derivatives', 'FX'}


def clean_etf_data(df):
    """
    Bereinigt ETF-Daten aus iShares-CSVs:
    - Entfernt NaN-Zeilen, 0%-Zeilen und Cash/Derivate-Einträge
    - Normalisiert Sektor- und Ländernamen (inkl. Encoding-Artefakte)
    """
    df = df.copy()  # Kein Mutieren des übergebenen DataFrames
    df['ETF'] = df['ETF'].apply(
        lambda x: os.path.splitext(os.path.basename(str(x)))[0]
        if (os.sep in str(x) or '/' in str(x) or str(x).endswith('.csv'))
        else str(x)
    )

    # Encoding-Artefakte aus Text-Spalten entfernen und Unicode normalisieren
    for col in ['Sektor', 'Standort', 'Name']:
        if col in df.columns:
            df[col] = df[col].apply(_normalize_str)
            df[col] = df[col].replace('nan', pd.NA).replace('', pd.NA)

    df['Gewichtung (%)'] = df['Gewichtung (%)'].astype(str).str.replace(',', '.', regex=False)
    df['Gewichtung (%)'] = pd.to_numeric(df['Gewichtung (%)'], errors='coerce')

    # Zeilen ohne Name oder Gewichtung und Zeilen mit Gewichtung ≤ 0 entfernen
    df = df.dropna(subset=['Name', 'Gewichtung (%)'])
    df = df[df['Gewichtung (%)'] > 0].copy()

    # Nach Anlageklasse filtern – nur echte Aktien behalten (falls Spalte vorhanden)
    if 'Anlageklasse' in df.columns:
        df['Anlageklasse'] = df['Anlageklasse'].astype(str).str.replace('\xa0', '', regex=False).str.strip()
        df = df[~df['Anlageklasse'].isin(_EXCLUDED_ASSET_CLASSES)].copy()
        df = df[df['Anlageklasse'].str.lower() == 'aktien'].copy()

    # Cash/Derivate-Zeilen nach Sektor ausschließen (zweite Sicherheitsstufe)
    df = df[~df['Sektor'].isin(_EXCLUDED_SECTORS)].copy()
    df = df[df['Sektor'].notna()].copy()

    # Sektor- und Länder-Normalisierung
    df['Sektor']   = df['Sektor'].replace(SECTOR_MAPPING)
    df['Standort'] = df['Standort'].replace(LOCATION_MAPPING)

    # Nach dem Mapping: Werte die NOCH im Source-Key-Set stehen wurden nicht aufgelöst → Sonstige
    # Alle anderen Werte (auch unbekannte Länder/Sektoren aus der CSV) bleiben wie sie sind –
    # sie sind einfach nicht im Mapping und müssen ggf. ergänzt werden, aber nicht pauschal 'Sonstige'
    unresolved_sector_keys = set(SECTOR_MAPPING.keys()) - set(SECTOR_MAPPING.values())
    unresolved_loc_keys    = set(LOCATION_MAPPING.keys()) - set(LOCATION_MAPPING.values())

    unk_s_mask = df['Sektor'].notna()   & df['Sektor'].isin(unresolved_sector_keys)
    unk_l_mask = df['Standort'].notna() & df['Standort'].isin(unresolved_loc_keys)

    if unk_s_mask.any():
        unk_vals = df.loc[unk_s_mask, 'Sektor'].value_counts().to_dict()
        logger.warning(f"Nicht aufgelöste Sektoren → 'Sonstige': {unk_vals}")
    if unk_l_mask.any():
        unk_vals = df.loc[unk_l_mask, 'Standort'].value_counts().to_dict()
        logger.warning(f"Nicht aufgelöste Länder → 'Sonstige': {unk_vals}")

    df.loc[unk_s_mask, 'Sektor']   = 'Sonstige'
    df.loc[unk_l_mask, 'Standort'] = 'Sonstige'

    # Leere Strings nach allen Operationen auffangen
    df['Sektor']   = df['Sektor'].replace('', pd.NA)
    df['Standort'] = df['Standort'].replace('', pd.NA)

    logger.info(f"ETF-Daten bereinigt: {len(df)} verwertbare Positionen (ohne Cash/Derivate/0%-Zeilen).")
    return df


def calculate_relative_weighting(etf_stocks, depot_components):
    """
    Berechnet die relative Gewichtung der ETF-Einzelpositionen im Gesamtdepot.

    :param etf_stocks: DataFrame mit ETF-Positionen und ihrer Gewichtung innerhalb des ETFs
    :param depot_components: DataFrame mit den Depot-Positionen und ihrem Marktwertanteil
    :return: Tuple (DataFrame mit ergänzter Spalte 'relative Gewichtung (%)', Zusammenfassungs-String)
    """
    if 'Marktwert (%)' not in depot_components.columns:
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

    # Spalte vorab mit 0 initialisieren – so existiert sie auch wenn kein ETF gemappt wurde
    if 'relative Gewichtung (%)' not in etf_stocks.columns:
        etf_stocks['relative Gewichtung (%)'] = 0.0

    for etf_name in etfs:
        if etf_name not in etf_stocks["ETF"].unique():
            available = etf_stocks["ETF"].unique().tolist()
            logger.warning(
                f"ETF '{etf_name}' nicht in ETF-CSV-Daten gefunden – übersprungen. "
                f"Verfügbare ETFs: {available}"
            )
            continue

        mask = depot_components["Position"] == etf_name
        etf_weight = depot_components.loc[mask, "Marktwert (%)"].values[0]

        if etf_weight <= 0:
            logger.warning(f"ETF '{etf_name}' hat Depotgewicht {etf_weight:.4f}% – kein Kurs? Gewichtung wird 0.")

        etf_stocks.loc[etf_stocks["ETF"] == etf_name, 'relative Gewichtung (%)'] = \
            etf_stocks.loc[etf_stocks["ETF"] == etf_name, 'Gewichtung (%)'] * etf_weight / 100
        logger.info(f"ETF '{etf_name}' erfolgreich verarbeitet (Depotgewicht: {etf_weight:.2f}%).")

    total_relative_weighting = etf_stocks['relative Gewichtung (%)'].sum()
    message = (f"Relative Gewichtung erfolgreich berechnet. "
               f"ETF-Anteil im Depot: {round(total_relative_weighting, 2)}%.")
    return etf_stocks, message
