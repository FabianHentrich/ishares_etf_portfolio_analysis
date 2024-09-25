# data_processing.py

import pandas as pd
import os

#SECTOR_MAPPING = [
#    ['IT'],
#    ['Technologie']
#]

#LOCATION_MAPPING = [
#    ["Vereinigte Staaten"],
#    ["USA"]
#]


def clean_etf_data(df):
    """
    Clean the ETF data.
    :param df: DataFrame containing ETF data.
    :return: DataFrame with cleaned ETF data.
    """
    #df['Sektor'].replace(SECTOR_MAPPING[0], SECTOR_MAPPING[1], inplace=True)
    #df["Standort"].replace(LOCATION_MAPPING[0], LOCATION_MAPPING[1], inplace=True)
    df['ETF'] = df['ETF'].apply(lambda x: os.path.splitext(os.path.basename(x))[0])
    df['Gewichtung (%)'] = df['Gewichtung (%)'].str.replace(',', '.')
    df['Gewichtung (%)'] = pd.to_numeric(df['Gewichtung (%)'])
    return df


def calculate_relative_weighting(etf_stocks, depot_components):
    """
    Calculate the relative weighting ETF stock components in the depot.
    :param etf_stocks: ETF stocks DataFrame
    :param depot_components: depot components from the portfolio
    :return: DataFrame with relative weighting and a message
    """
    # Check if 'Marktwert (%)' exists
    if 'Marktwert (%)' not in depot_components.columns:
        raise KeyError("'Marktwert (%)' column is missing from depot_components DataFrame.")

    # Check if the input dataframes are not empty
    if etf_stocks.empty:
        raise ValueError("The input dataframe 'etf_stocks' is empty.")
    if depot_components.empty:
        raise ValueError("The input dataframe 'depot_components' is empty.")

    # Check if the input dataframes contain the necessary columns
    required_columns_etf_stocks = ["ETF", "Gewichtung (%)"]
    for column in required_columns_etf_stocks:
        if column not in etf_stocks.columns:
            raise ValueError(f"The input dataframe 'etf_stocks' does not contain the required column '{column}'.")

    required_columns_depot_components = ["Art", "Position", "Marktwert (%)"]
    for column in required_columns_depot_components:
        if column not in depot_components.columns:
            raise ValueError(f"The input dataframe 'depot_components' does not contain the required column '{column}'.")

    etfs = depot_components.loc[depot_components["Art"] == "ETF", "Position"].unique()
    print(f"ETFs in {depot_components}: {etfs}")

    for etf_name in etfs:
        if etf_name not in etf_stocks["ETF"].unique():
            print(f"ETF '{etf_name}' not found in ETF stocks. Skipping.")
            continue

        mask = depot_components["Position"] == etf_name
        etf_weight = depot_components.loc[mask, "Marktwert (%)"].values[0]
        etf_stocks.loc[etf_stocks["ETF"] == etf_name, 'relative Gewichtung (%)'] = \
            etf_stocks.loc[etf_stocks["ETF"] == etf_name, 'Gewichtung (%)'] * etf_weight / 100
        print(f"ETF '{etf_name}' has been successfully processed.")

    total_relative_weighting = etf_stocks['relative Gewichtung (%)'].sum()
    message = f"Relative Gewichtung has been successfully calculated and added. " \
              f"The ETF percentage share amounts to {round(total_relative_weighting, 2)}%."

    return etf_stocks, message
