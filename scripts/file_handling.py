# file_handling.py

import os
import pandas as pd

def read_etf_data(file, skip_rows=2, encoding='utf-8', delimiter=','):
    if not os.path.exists(file):
        print(f"File '{file}' does not exist.")
        return None
    try:
        df = pd.read_csv(file, skiprows=skip_rows, encoding=encoding, delimiter=delimiter)
        df["ETF"] = str(file)
        return df
    except Exception as e:
        print(f"Error reading file '{file}': {e}")
        return None

def export_to_excel(output_file, depot, depot_data, depot_data_stocks, depot_data_etfs, depot_data_sectors, depot_data_locations):
    try:
        with pd.ExcelWriter(output_file) as writer:
            depot.to_excel(writer, sheet_name="Depotwerte", index=False)
            depot_data.to_excel(writer, sheet_name="Datengrundlage", index=False)
            depot_data_stocks.to_excel(writer, sheet_name="Aktien", index=False)
            depot_data_etfs.to_excel(writer, sheet_name="ETFs", index=False)
            depot_data_sectors.to_excel(writer, sheet_name="Sektoren", index=False)
            depot_data_locations.to_excel(writer, sheet_name="Länder", index=False)
        print(f"File '{output_file}' has been successfully written.")
    except Exception as e:
        print(f"Failed to write Excel file: {e}")
