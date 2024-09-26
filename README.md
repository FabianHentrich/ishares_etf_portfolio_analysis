# **iShares ETF Analysis for Stocks, Sectors and Countries**

This code is used to download iShares ETF data from the BlackRock website and analyze the data to provide a summary of the stocks, sectors, and countries that the ETF is invested in and add that to the other portfolio components.

## **`portfolio.xlsx` - how does it look like?**

Check the example file in the repository. The file should be saved in ´"INPUTFILE"´. 
The file should have the following columns:

- `Ticker`: Check Ticker via Yahoo Finance. You don't need to add the suffix. (e.g., Microsoft's ticker is MSFT, but for Germany Xetra it is MSF)
- `Art`: Class of security (e.g., Stock aka "Aktie", ETF, Crypto aka "Krypto")
- `Position`: Name of security (e.g., Microsoft, iShares MSCI World UCITS ETF, Bitcoin). The name should match the names in the ETF CSV files (so use the iShares framing).
- `Sektor`: Sector of the security (e.g., Technology, Financials, Consumer Discretionary). Should match the sector in the ETF CSV files (so use the iShares framing).
- `Standort`: Country of the security (e.g., United States, Germany, China). Should match the country in the ETF CSV files (so use the iShares framing).
- `Anteile`: Number of shares of the security

```markdown
| Ticker | Art   | Position                                    | Sektor                  | Standort     | Anteile |
|--------|-------|---------------------------------------------|-------------------------|--------------|---------|
| -      | Cash  | Cash                                        | Cash und/oder Derivate  | Cash (Euro)  | 1000    |
| 2B7K   | ETF   | iShares MSCI World SRI ETF                  | -                       | -            | 1000    |
| QDVW   | ETF   | iShares MSCI World Quality Dividend ESG ETF | -                       | -            | 500     |
| BTC    | Krypto| Bitcoin                                     | Krypto                  | Krypto       | 1       |
| AAPL   | Aktie | Appel Inc.                                  | Technologie             | USA          | 100     |
```
`Cash` should be added as a security with the ticker `-`. `Anteile` should be the amount of cash in the portfolio.

## **Globale variables: Import folder paths, URLs, Names for CSV files and ticker suffixe**
For easier handling, the global variables are stored in a `.env` file. The file should be saved in the same folder as the script.

### **How to set up the `.env` file?**

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
- `ETF_CSV_FILE` and `CSV_URL` have to be in the same order. Separate the URLs and the file names with a comma. Add as many URLs and file names as you need.
- `STOCK_TICKER_SUFFIXES` and `CRYPTO_TICKER_SUFFIXES` are optional. Default is `.DE` for Xetra and `-EUR` for crypto in Euro**. If you want to add more suffixes, separate them with a comma.

## **How to run the script?**

1. Set up the `.env` file.
2. Create the folder structure as specified in the `.env` file (especially the folders `outputfiles` and `downloadfiles`).
3. Save the `portfolio.xlsx` file in the folder specified in the `.env` file.
4. Run the script. 
5. The charts will be saved in the folder specified in the `.env` file and open automatically in your browser.
6. Check the `stockoverview.xlsx` file in the folder specified in the `.env` file. 
7. Done!
8. If you want to run the script again you are overwriting the `stockoverview.xlsx` file and the charts.
9. The ETF CSV files will only be downloaded if they are not already in the download folder or are older than 30 day (Interval can be changed via`download_csv_if_old(...,...,max_age_days= ?)` in `main.py`).