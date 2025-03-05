# file_handling.py

import os
import pandas as pd


def read_etf_data(file, skip_rows=2, encoding='utf-8', delimiter=','):
    """
    Read iShares ETF data from a CSV file.
    :param file: file path to the CSV file
    :param skip_rows: rows to skip from the beginning of the file. Default is 2.
    :param encoding: encoding of the file. Default is 'utf-8'
    :param delimiter: Delimiter used in the CSV file. Default is ','.
    :return: Returns a DataFrame with a column 'ETF' containing the ETF name.
    """
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
    try:
        with pd.ExcelWriter(output_file) as writer:
            try:
                depot.to_excel(writer, sheet_name="Depotwerte", index=False)
            except Exception as e:
                print(f"Failed to write 'Depotwerte' sheet from depot DataFrame: {e}")
            try:
                depot_data.to_excel(writer, sheet_name="Datengrundlage", index=False)
            except Exception as e:
                print(f"Failed to write 'Datengrundlage' sheet from depot_data DataFrame: {e}")
            try:
                depot_data_stocks.to_excel(writer, sheet_name="Aktien", index=False)
            except Exception as e:
                print(f"Failed to write 'Aktien' sheet from depot_data_stocks DataFrame: {e}")
            try:
                depot_data_etfs.to_excel(writer, sheet_name="ETFs", index=False)
            except Exception as e:
                print(f"Failed to write 'ETFs' sheet from depot_data_etfs DataFrame: {e}")
            try:
                depot_data_sectors.to_excel(writer, sheet_name="Sektoren", index=False)
            except Exception as e:
                print(f"Failed to write 'Sektoren' sheet from depot_data_sectors DataFrame: {e}")
            try:
                depot_data_locations.to_excel(writer, sheet_name="Länder", index=False)
            except Exception as e:
                print(f"Failed to write 'Länder' sheet from depot_data_locations DataFrame: {e}")
        print(f"File '{output_file}' has been successfully written.")
    except Exception as e:
        print(f"Failed to write Excel file: {e}")
