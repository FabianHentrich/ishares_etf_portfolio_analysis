# data_download.py

import os
import requests
from datetime import datetime
import yfinance as yf
import pandas as pd
from pandas.tseries.offsets import BDay


def download_csv_if_old(urls, folder_path, filenames, max_age_days=30):
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
    today = pd.Timestamp.today()
    last_working_day = today - pd.offsets.BDay(1)

    # Process stock and ETF tickers
    stock_tickers = df[df["Art"].isin(['Aktie', 'ETF'])]["Ticker"].str.replace(r'\..*$', '', regex=True).tolist()
    print(f"Stock Tickers: {stock_tickers}")

    # Process crypto tickers
    crypto_tickers = df[df["Art"] == "Krypto"]["Ticker"].str.replace(r'\-.*$', '', regex=True).tolist()
    print(f"Crypto Tickers: {crypto_tickers}")

    # DataFrame to store tickers and their prices
    prices = pd.DataFrame(columns=['ticker', 'Kurs'])

    # Download stock prices and store in prices DataFrame
    for ticker in stock_tickers:
        price_found = False
        for suffix in stock_ticker_suffixes:
            modified_ticker = ticker + suffix
            print(f"Trying Stock Ticker: {modified_ticker}")

            try:
                stock_prices = yf.download(modified_ticker, start=last_working_day, end=today, progress=False)
                if not stock_prices.empty and 'Adj Close' in stock_prices.columns:
                    stock_price = stock_prices["Adj Close"].iloc[0]
                    if not pd.isna(stock_price):
                        # Use pd.concat to add the new row to prices DataFrame
                        prices = pd.concat([prices, pd.DataFrame({'Ticker': [ticker], 'Kurs': [stock_price]})], ignore_index=True)
                        price_found = True
                        break  # Exit the suffix loop if a valid price is found
            except Exception as e:
                print(f"Failed to download stock price for '{modified_ticker}': {e}")

        if not price_found:
            print(f"No valid stock price found for ticker '{ticker}' with any suffix.")
            # Use pd.concat to add the ticker with None for price
            prices = pd.concat([prices, pd.DataFrame({'Ticker': [ticker], 'Kurs': [None]})], ignore_index=True)

    # Download crypto prices and store in prices DataFrame
    for ticker in crypto_tickers:
        price_found = False
        for suffix in crypto_ticker_suffixes:
            modified_ticker = ticker + suffix
            print(f"Trying Crypto Ticker: {modified_ticker}")

            try:
                crypto_prices = yf.download(modified_ticker, start=last_working_day, end=today, progress=False)
                if not crypto_prices.empty and 'Adj Close' in crypto_prices.columns:
                    crypto_price = crypto_prices["Adj Close"].iloc[0]
                    if not pd.isna(crypto_price):
                        # Use pd.concat to add the new row to prices DataFrame
                        prices = pd.concat([prices, pd.DataFrame({'Ticker': [ticker], 'Kurs': [crypto_price]})], ignore_index=True)
                        price_found = True
                        break  # Exit the suffix loop if a valid price is found
            except Exception as e:
                print(f"Failed to download crypto price for '{modified_ticker}': {e}")

        if not price_found:
            print(f"No valid crypto price found for ticker '{ticker}' with any suffix.")
            # Use pd.concat to add the ticker with None for price
            prices = pd.concat([prices, pd.DataFrame({'Ticker': [ticker], 'Kurs': [None]})], ignore_index=True)

    # Output result
    cash = pd.DataFrame({'Ticker': ['-'], 'Kurs': [1]})
    prices = pd.concat([prices, cash], ignore_index=True)
    print(prices)
    return prices