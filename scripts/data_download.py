# data_download.py

import os
import requests
from datetime import datetime
import yfinance as yf
import pandas as pd
from pandas.tseries.offsets import BDay


def download_csv_if_old(urls, folder_path, filenames, max_age_days=30):
    """
    Download CSV files if they are older than max_age_days
    :param urls: list of URLs to download CSV files
    :param folder_path: folder path to save the CSV files
    :param filenames: list of filenames to save the CSV files. should be same length and order as urls
    :param max_age_days: maximum age of existent CSV file in days. Default is 30 days
    :return: saved CSV files in the folder_path
    """
    for url, filename in zip(urls, filenames):
        csv_file_path = os.path.join(folder_path, filename)
        if os.path.exists(csv_file_path):
            modification_time = os.path.getmtime(csv_file_path)
            last_modified_date = datetime.fromtimestamp(modification_time)
            if (datetime.now() - last_modified_date).days < max_age_days:
                print(f"CSV file '{filename}' exists and is not older than {max_age_days} days. Skipping download.")
                continue
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(csv_file_path, 'w', encoding='utf-8') as f:
                f.write(response.text)
            print(f"CSV file '{filename}' has been successfully downloaded.")
        except Exception as e:
            print(f"Failed to download the CSV file '{filename}': {e}")


def download_stock_price(df, stock_ticker_suffixes=[".DE"], crypto_ticker_suffixes=["-EUR"]):
    """
    Download stock prices from Yahoo Finance API for the last working day and store in a DataFrame
    :param df: DataFrame with 'Ticker' column containing stock and crypto tickers
    :param stock_ticker_suffixes: suffixes to add to stock tickers for Yahoo Finance API (e.g., ".DE" for Xetra stocks).
    Default is [".DE"]. For other exchanges, add the suffixes to the list.
    :param crypto_ticker_suffixes: suffixes to add to crypto tickers for Yahoo Finance API (e.g., "-EUR" for Euro
    prices). Default is ["-EUR"]. For other currencies, add the suffixes to the list.
    :return: Returns a DataFrame with 'Ticker' and 'Kurs' columns containing the stock prices.
    """
    # Set default values if the lists are empty or None
    if not stock_ticker_suffixes:
        stock_ticker_suffixes = [".DE"]
    if not crypto_ticker_suffixes:
        crypto_ticker_suffixes = ["-EUR"]

    today = pd.Timestamp.today()
    last_working_day = today - pd.offsets.BDay(1)
    print(f"Last Working Day: {last_working_day}")

    # Process stock and ETF tickers
    stock_tickers = df[df["Art"].isin(['Aktie', 'ETF'])]["Ticker"].str.replace(r'\..*$', '', regex=True).tolist()
    print(f"Stock Tickers: {stock_tickers}")

    # Process crypto tickers
    crypto_tickers = df[df["Art"] == "Krypto"]["Ticker"].str.replace(r'\-.*$', '', regex=True).tolist()
    print(f"Crypto Tickers: {crypto_tickers}")

    print(f"Stock Ticker Suffixes: {stock_ticker_suffixes}")
    print(f"Crypto Ticker Suffixes: {crypto_ticker_suffixes}")

    # list to store tickers and their prices
    price_list = []

    # Download stock prices and store in prices DataFrame
    for ticker in stock_tickers:
        price_found = False
        for suffix in stock_ticker_suffixes:
            modified_ticker = ticker + suffix
            print(f"Trying Stock Ticker: {modified_ticker}")

            try:
                stock_prices = yf.download(modified_ticker, start=last_working_day, end=today, progress=False)
                if not stock_prices.empty and 'Close' in stock_prices.columns:
                    stock_price = stock_prices["Close"].iloc[0]
                    if pd.notna(stock_price.values[0]):
                        price_list.append({'Ticker': ticker, 'Kurs': stock_price.values[0]})  # Append as dict
                        price_found = True
                        break  # Exit the suffix loop if a valid price is found
            except Exception as e:
                print(f"Failed to download stock price for '{modified_ticker}': {e}")

        if not price_found:
            print(f"No valid stock price found for ticker '{ticker}' with any suffix.")
            # Append as dict with None for price
            price_list.append({'Ticker': ticker, 'Kurs': [None]})

    # Download crypto prices and store in prices DataFrame
    for ticker in crypto_tickers:
        price_found = False
        for suffix in crypto_ticker_suffixes:
            modified_ticker = ticker + suffix
            print(f"Trying Crypto Ticker: {modified_ticker}")

            try:
                crypto_prices = yf.download(modified_ticker, start=last_working_day, end=today, progress=False)
                if not crypto_prices.empty and 'Close' in crypto_prices.columns:
                    crypto_price = crypto_prices["Close"].iloc[0]
                    if pd.notna(crypto_price.values[0]):
                        price_list.append({'Ticker': ticker, 'Kurs': crypto_price.values[0]})  # Append as dict
                        price_found = True
                        break  # Exit the suffix loop if a valid price is found
            except Exception as e:
                print(f"Failed to download crypto price for '{modified_ticker}': {e}")

        if not price_found:
            print(f"No valid crypto price found for ticker '{ticker}' with any suffix.")
            # Append as dict with None for price
            price_list.append({'Ticker': ticker, 'Kurs': [None]})

    # Output result
    cash = pd.DataFrame({'Ticker': ['-'], 'Kurs': [1]})
    # Convert list to DataFrame **only once** (much faster than multiple concats)
    prices = pd.DataFrame(price_list)
    # Concatenate with cash
    prices = pd.concat([prices, cash], ignore_index=True)
    print(prices)
    return prices
