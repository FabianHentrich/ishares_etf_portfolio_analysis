# file_handling.py

import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)


def read_etf_data(file, skip_rows=2, encoding='utf-8', delimiter=','):
    """
    Read iShares ETF data from a CSV file.
    :param file: file path to the CSV file
    :param skip_rows: rows to skip from the beginning of the file. Default is 2.
    :param encoding: encoding of the file. Default is 'utf-8'
    :param delimiter: Delimiter used in the CSV file. Default is ','.
    :return: Returns a DataFrame with a column 'ETF' containing the ETF name (without path/extension).
    """
    if not os.path.exists(file):
        logger.error(f"Datei '{file}' nicht gefunden.")
        return None
    try:
        df = pd.read_csv(file, skiprows=skip_rows, encoding=encoding, delimiter=delimiter)
        # Direkt sauberen ETF-Namen speichern (kein vollständiger Pfad)
        df["ETF"] = os.path.splitext(os.path.basename(file))[0]
        logger.info(f"ETF-Datei '{file}' erfolgreich gelesen ({len(df)} Zeilen).")
        return df
    except Exception as e:
        logger.error(f"Fehler beim Lesen von '{file}': {e}")
        return None


def export_to_excel(output_file, depot, depot_data, depot_data_stocks, depot_data_etfs, depot_data_sectors,
                    depot_data_locations):
    """
    Export the depot data to an Excel file in different sheets.
    :param output_file: file path to save the Excel file.
    :param depot: Contains the depot data and saved in the 'Depotwerte' sheet.
    :param depot_data: Can be used to save the raw data in the 'Datengrundlage' sheet.
    :param depot_data_stocks: Contains the stock data in the 'Aktien' sheet.
    :param depot_data_etfs: Contains the ETF data in the 'ETFs' sheet.
    :param depot_data_sectors: Contains the sector data in the 'Sektoren' sheet.
    :param depot_data_locations: Contains the location data in the 'Länder' sheet.
    :return: Returns an Excel file with the depot data.
    """
    sheets = {
        "Depotwerte": depot,
        "Datengrundlage": depot_data,
        "Aktien": depot_data_stocks,
        "ETFs": depot_data_etfs,
        "Sektoren": depot_data_sectors,
        "Länder": depot_data_locations,
    }
    try:
        with pd.ExcelWriter(output_file) as writer:
            for sheet_name, df in sheets.items():
                try:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    logger.info(f"Sheet '{sheet_name}' erfolgreich geschrieben.")
                except Exception as e:
                    logger.error(f"Fehler beim Schreiben von Sheet '{sheet_name}': {e}")
        logger.info(f"Excel-Datei '{output_file}' erfolgreich gespeichert.")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben der Excel-Datei: {e}")
