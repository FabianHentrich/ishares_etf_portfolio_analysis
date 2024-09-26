# **iShares ETF Analysis for Stocks, Sectors and Countries**

This code is used to download iShares ETF data from the BlackRock website and analyze the data to provide a summary of the stocks, sectors, and countries that the ETF is invested in and add that to the other portfolio components.

## **portfolio.xlsx - how does it look like?**

Check the example file in the repository. The file should be saved in "INPUTFILE". 
The file should have the following columns:

- **Ticker**: Check Ticker via Yahoo Finance. You don't need to add the suffix. (e.g., Microsoft's ticker is MSFT, but for Germany Xetra it is MSF)
- **Art**: Class of security (e.g., Stock aka "Aktie", ETF, Crypto aka "Krypto")
- **Position**: Name of security (e.g., Microsoft, iShares MSCI World UCITS ETF, Bitcoin). The name should match the names in the ETF CSV files (so use the iShares framing).
- **Sektor**: Sector of the security (e.g., Technology, Financials, Consumer Discretionary). Should match the sector in the ETF CSV files (so use the iShares framing).
- **Standort**: Country of the security (e.g., United States, Germany, China). Should match the country in the ETF CSV files (so use the iShares framing).
- **Anteile**: Number of shares of the security

Cash should be added as a security with the following information:

- **Ticker**: -
- **Art**: Cash
- **Position**: Cash
- **Sektor**: Cash und/oder Derivate
- **Standort**: Cash (Euro)
- **Anteile**: Amount of cash in the portfolio

## **How does the .env file work?**

```dotenv
FOLDER_PATH="path to the folder where the files should be stored"
DOWNLOAD_PATH="${FOLDER_PATH}\\downloadfiles"
SAVE_PATH="${FOLDER_PATH}\\outputfiles"
INPUT_FILE="${FOLDER_PATH}\\portfolio.xlsx"
OUTPUT_FILE="${SAVE_PATH}\\stockoverview.xlsx"
CSV_URL="download urls 1, download urls 2, download urls 3"
ETF_CSV_FILE="name of the csv file1, name of the csv file2, name of the csv file3"
STOCK_TICKER_SUFFIXES="stock ticker suffix1, stock ticker suffix2, stock ticker suffix3"
CRYPTO_TICKER_SUFFIXES="crypto ticker suffix1, crypto ticker suffix2, crypto ticker suffix3"
```
ETF_CSV_FILE and CSV_URL have to be in the same order