import timeit
import pandas as pd
import os
from dotenv import load_dotenv
from scripts.data_download import download_csv_if_old, download_stock_price
from scripts.data_processing import clean_etf_data, calculate_relative_weighting
from scripts.file_handling import read_etf_data, export_to_excel
from scripts.plotting import plot_pie_chart

start = timeit.default_timer()

# load environment variables
load_dotenv()

FOLDER_PATH = os.getenv('FOLDER_PATH')
DOWNLOAD_PATH = os.getenv('DOWNLOAD_PATH')
SAVE_PATH = os.getenv('SAVE_PATH')
INPUT_FILE = os.getenv('INPUT_FILE')
OUTPUT_FILE = os.getenv('OUTPUT_FILE')

# Retrieve and split CSV URLs and ETF CSV files, then strip whitespace
CSV_URL = [CSV_URL.strip() for CSV_URL in os.getenv('CSV_URL', '').split(',')]
ETF_CSV_FILE = [ETF_CSV_FILE.strip() for ETF_CSV_FILE in os.getenv('ETF_CSV_FILE', '').split(',')]

# Retrieve and split stock ticker suffixes, then strip whitespace
STOCK_TICKER_SUFFIXES = [suffix.strip() for suffix in os.getenv('STOCK_TICKER_SUFFIXES', '').split(',')]

# Retrieve and split crypto ticker suffixes, then strip whitespace
CRYPTO_TICKER_SUFFIXES = [suffix.strip() for suffix in os.getenv('CRYPTO_TICKER_SUFFIXES', '').split(',')]

print(f"load_dotenv() successful.\n"
      f"FOLDER_PATH: {FOLDER_PATH}, \n"
      f"DOWNLOAD_PATH: {DOWNLOAD_PATH}, \n"
      f"SAVE_PATH: {SAVE_PATH}, \n"
      f"INPUT_FILE: {INPUT_FILE}, \n"
      f"OUTPUT_FILE: {OUTPUT_FILE}, \n"
      f"CSV_URL: {CSV_URL}, \n"
      f"ETF_CSV_FILE: {ETF_CSV_FILE}, \n"
      f"STOCK_TICKER_SUFFIXES: {STOCK_TICKER_SUFFIXES}, \n"
      f"CRYPTO_TICKER_SUFFIXES: {CRYPTO_TICKER_SUFFIXES}")

# 1. Download CSV data
download_csv_if_old(CSV_URL, DOWNLOAD_PATH, ETF_CSV_FILE)

# 2. Read ETF data
etf_data_files = [os.path.join(DOWNLOAD_PATH, file) for file in ETF_CSV_FILE]
etf_data_list = []

for file in etf_data_files:
    df = read_etf_data(file)
    if df is not None:
        etf_data_list.append(df)

if etf_data_list:
    etf_data = pd.concat(etf_data_list, ignore_index=True)
else:
    print("No ETF data available. Exiting.")
    exit()  # Use exit() instead of return

# Debugging: Check ETF Data
print("ETF Data Columns:", etf_data.columns.tolist())
print(etf_data.head())

# 3. Read depot data
if not os.path.exists(INPUT_FILE):
    print(f"Input file '{INPUT_FILE}' does not exist. Exiting.")
    exit()  # Use exit() instead of return

depot = pd.read_excel(INPUT_FILE)

# Remove suffix from 'Ticker' column for stocks and ETFs
depot.loc[depot['Art'].isin(['Aktie', 'ETF']), 'Ticker'] = depot['Ticker'].str.replace(r'\..*$', '', regex=True)

# Remove suffix from 'Ticker' column for cryptos
depot.loc[depot['Art'] == 'Krypto', 'Ticker'] = depot['Ticker'].str.replace(r'\-.*$', '', regex=True)

print("Depot DataFrame Columns After Processing:", depot.columns.tolist())
print(depot.head())

# 4. Download stock prices
stock_prices = download_stock_price(depot, STOCK_TICKER_SUFFIXES, CRYPTO_TICKER_SUFFIXES)

if stock_prices is not None:
    # Merge stock prices with depot
    depot = depot.merge(stock_prices[['Ticker', 'Kurs']], on='Ticker', how='left')
    print("Depot DataFrame Columns After Joining:", depot.columns.tolist())

    # Rename columns to match your requirements
    depot.columns = ["Ticker", "Art", "Position", "Sektor", "Standort", "Anteile", "Kurs"]
    print(depot.head())

    # Convert columns to numeric, forcing non-numeric to NaN
    depot["Kurs"] = pd.to_numeric(depot["Kurs"], errors='coerce')
    depot["Anteile"] = pd.to_numeric(depot["Anteile"], errors='coerce')

    # Calculate 'Marktwert' and 'Marktwert (%)'
    depot["Marktwert"] = depot["Anteile"] * depot["Kurs"]
    depot["Marktwert (%)"] = depot["Marktwert"] / depot["Marktwert"].sum() * 100

    # Debugging: Check depot after calculations
    print("Depot DataFrame Columns After Calculations:", depot.columns.tolist())
    print(depot.head())

else:
    print("Stock prices download failed. Exiting.")
    exit()  # Use exit() instead of return

# 5. Clean ETF data
etf_data = clean_etf_data(etf_data)
print("Cleaned ETF Data:")
print(etf_data.head())

# 6. Calculate relative weighting
try:
    etf_data, message = calculate_relative_weighting(etf_data, depot)
    print(message)
except KeyError as e:
    print(f"Error in calculating relative weighting: {e}")
    exit()  # Use exit() instead of return
except Exception as e:
    print(f"Unexpected error: {e}")
    exit()  # Use exit() instead of return

# 7. Prepare assets and concatenate with ETF data
assets = depot[depot["Art"].isin(["Aktie", "Cash", "Krypto"])]
assets = assets.loc[:, ["Ticker", "Art", "Position", "Sektor", "Standort", "Marktwert (%)"]]
assets = assets.rename(columns={"Ticker": "Emittententicker", "Position": "Name", "Art": "ETF",
                                "Marktwert (%)": "relative Gewichtung (%)"})
depot_data = pd.concat([etf_data, assets], ignore_index=True, sort=False)

# 8. Generate summaries
depot_data_sectors = depot_data.groupby(['Sektor'])['relative Gewichtung (%)'].sum().reset_index()
depot_data_sectors.rename(columns={'relative Gewichtung (%)': 'Sektorgewichtung (%)'}, inplace=True)
depot_data_sectors.sort_values(by='Sektorgewichtung (%)', ascending=False, inplace=True)

depot_data_locations = depot_data.groupby(['Standort'])['relative Gewichtung (%)'].sum().reset_index()
depot_data_locations.rename(columns={'relative Gewichtung (%)': 'Ländergewichtung (%)'}, inplace=True)
depot_data_locations.sort_values(by='Ländergewichtung (%)', ascending=False, inplace=True)

depot_data_etfs = depot_data.groupby(['ETF'])['relative Gewichtung (%)'].sum().reset_index()
depot_data_etfs.rename(columns={'relative Gewichtung (%)': 'ETF-Gewichtung (%)'}, inplace=True)
depot_data_etfs.sort_values(by='ETF-Gewichtung (%)', ascending=False, inplace=True)

depot_data_stocks = depot_data.groupby(['Name']).agg({
    "Emittententicker": 'first',
    'relative Gewichtung (%)': 'sum',
    'Sektor': 'first',
    'Standort': 'first'
}).reset_index()
depot_data_stocks.rename(columns={'relative Gewichtung (%)': 'Gesamtgewichtung (%)'}, inplace=True)
depot_data_stocks.sort_values(by='Gesamtgewichtung (%)', ascending=False, inplace=True)

# 9. Export results to Excel
export_to_excel(
    OUTPUT_FILE,
    depot,
    depot_data,
    depot_data_stocks,
    depot_data_etfs,
    depot_data_sectors,
    depot_data_locations
)

# 10. Generate charts
stocks_100 = depot_data_stocks.iloc[0:99, :]
others = 100 - stocks_100["Gesamtgewichtung (%)"].sum()
others_df = pd.DataFrame({"Name": ["Sonstige"], "Gesamtgewichtung (%)": [others]})
stocks_100 = pd.concat([stocks_100, others_df])

plot_pie_chart(stocks_100, 'Gesamtgewichtung (%)', 'Name', 'Top 100 Aktien',
               f"{SAVE_PATH}/1. Übersicht nach Positionen.pdf")
plot_pie_chart(depot, 'Marktwert (%)', 'Position', 'Übersicht nach Depot',
               f"{SAVE_PATH}/2. Übersicht nach Depot.pdf")
plot_pie_chart(depot, 'Marktwert (%)', 'Art', 'Übersicht nach Anlageart',
               f"{SAVE_PATH}/3. Übersicht nach Anlageart.pdf")
plot_pie_chart(depot_data_sectors, 'Sektorgewichtung (%)', 'Sektor', 'Übersicht nach Sektoren',
               f"{SAVE_PATH}/4. Übersicht nach Sektoren.pdf")
plot_pie_chart(depot_data_locations, 'Ländergewichtung (%)', 'Standort', 'Übersicht nach Standorten',
               f"{SAVE_PATH}/5. Übersicht nach Ländern.pdf")

stop = timeit.default_timer()
print("Laufzeit:", stop - start, "Sekunden")
