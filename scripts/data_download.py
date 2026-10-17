# data_download.py

import json
import logging
import os
import shutil

import pandas as pd
import requests
import yfinance as yf
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Pfad zur Fallback-JSON-Datei (liegt im Projekt-Root)
_FALLBACK_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "price_fallback.json")

# Standard-Fallback-Werte – werden beim ersten Start als Basis verwendet
_DEFAULT_FALLBACKS = {
    "MATIC": 0.10,
}

# Kurse der letzten N Kalendertage abfragen – deckt Wochenenden und Börsenfeiertage
# (z.B. Weihnachten/Ostern) ab; verwendet wird jeweils der jüngste Schlusskurs
_PRICE_WINDOW_DAYS = 7
# Ab diesem Alter (Tage) wird ein Kurs im Log als veraltet gemeldet
_STALE_DAYS = 7


def _fallback_entry(value):
    """Liest einen Fallback-Eintrag → (kurs, datum).

    Neues Format: {"kurs": 1.23, "datum": "2026-10-16"}; Altformat (nur Zahl) → datum None.
    """
    if isinstance(value, dict):
        return value.get("kurs"), value.get("datum")
    return value, None


def _age_days(datum):
    """Alter eines ISO-Datums in Tagen (None bei unbekanntem Datum)."""
    if not datum:
        return None
    return (pd.Timestamp.today().normalize() - pd.Timestamp(datum).normalize()).days


def _load_fallback() -> dict:
    """Lädt die Fallback-Kurse aus der JSON-Datei. Erstellt sie bei Bedarf."""
    if os.path.exists(_FALLBACK_JSON):
        try:
            with open(_FALLBACK_JSON, encoding="utf-8") as f:
                data = json.load(f)
            logger.debug(f"Fallback-JSON geladen: {_FALLBACK_JSON}")
            return data
        except Exception as e:
            # Datei NICHT überschreiben – sonst gehen alle gespeicherten Kurse verloren.
            # Defensive Kopie sichern, damit ein späteres _save_fallback() sie nicht vernichtet.
            backup = _FALLBACK_JSON + ".corrupt"
            try:
                shutil.copy2(_FALLBACK_JSON, backup)
            except Exception:
                backup = None
            logger.warning(
                f"Fallback-JSON konnte nicht gelesen werden: {e} – Defaults werden verwendet"
                + (f", Original gesichert unter '{backup}'." if backup else ".")
            )
            return dict(_DEFAULT_FALLBACKS)
    # Datei noch nicht vorhanden → mit Defaults initialisieren
    _save_fallback(_DEFAULT_FALLBACKS)
    return dict(_DEFAULT_FALLBACKS)


def _save_fallback(fallback: dict) -> None:
    """Speichert die aktuellen Fallback-Kurse in die JSON-Datei."""
    try:
        with open(_FALLBACK_JSON, "w", encoding="utf-8") as f:
            json.dump(fallback, f, indent=2, ensure_ascii=False)
        logger.debug(f"Fallback-JSON gespeichert: {_FALLBACK_JSON}")
    except Exception as e:
        logger.warning(f"Fallback-JSON konnte nicht gespeichert werden: {e}")


def _create_retry_session(retries=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504)):
    """Erstellt eine requests-Session mit automatischem Retry bei Netzwerkfehlern."""
    session = requests.Session()
    retry = Retry(total=retries, backoff_factor=backoff_factor, status_forcelist=status_forcelist)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def _is_ishares_csv(text: str) -> bool:
    """Prüft, ob der Text eine iShares-Positions-CSV ist (und keine HTML-Seite o.ä.)."""
    head = text.lstrip("﻿")[:2000]
    return head.startswith("Fondsposition") and "Emittententicker" in head


def download_csv_if_old(urls, folder_path, filenames, max_age_days=30):
    """
    Download CSV files if they are older than max_age_days
    :param urls: list of URLs to download CSV files
    :param folder_path: folder path to save the CSV files
    :param filenames: list of filenames to save the CSV files. should be same length and order as urls
    :param max_age_days: maximum age of existent CSV file in days. Default is 30 days
    :return: saved CSV files in the folder_path
    """
    session = _create_retry_session()
    if not os.path.isdir(folder_path):
        logger.error(f"Download-Verzeichnis '{folder_path}' existiert nicht – CSV-Download übersprungen.")
        return
    if len(urls) != len(filenames):
        logger.error(
            f"CSV_URL ({len(urls)} Einträge) und ETF_CSV_FILE ({len(filenames)} Einträge) "
            f"haben unterschiedlich viele Einträge – CSV-Download übersprungen. "
            f"Bitte .env prüfen: Reihenfolge und Anzahl müssen übereinstimmen."
        )
        return
    for url, filename in zip(urls, filenames, strict=False):  # Längenprüfung erfolgt explizit oben
        csv_file_path = os.path.join(folder_path, filename)
        if os.path.exists(csv_file_path):
            modification_time = os.path.getmtime(csv_file_path)
            last_modified_date = pd.Timestamp.fromtimestamp(modification_time)
            if (pd.Timestamp.now() - last_modified_date).days < max_age_days:
                logger.info(f"CSV-Datei '{filename}' ist aktuell (< {max_age_days} Tage). Download übersprungen.")
                continue
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            if not _is_ishares_csv(response.text):
                logger.error(
                    f"Download von '{filename}' liefert keine iShares-Positions-CSV (evtl. HTML-Seite) – "
                    f"vorhandene Datei bleibt erhalten. Bitte CSV_URL in .env prüfen "
                    f"(aktuelles Format: .../produkte/<id>/<name>/latest-holdings.csv)."
                )
                continue
            # Erst in Temp-Datei schreiben, dann atomar ersetzen – kein halb geschriebenes CSV
            tmp_path = csv_file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(response.text)
            os.replace(tmp_path, csv_file_path)
            logger.info(f"CSV-Datei '{filename}' erfolgreich heruntergeladen.")
        except Exception as e:
            logger.error(f"Fehler beim Download von '{filename}': {e}")


def download_stock_price(df, stock_ticker_suffixes=None, crypto_ticker_suffixes=None):
    """
    Download stock prices from Yahoo Finance API and store the latest close within the last
    _PRICE_WINDOW_DAYS calendar days in a DataFrame (covers weekends and exchange holidays).
    :param df: DataFrame with 'Ticker' column containing stock and crypto tickers
    :param stock_ticker_suffixes: suffixes to add to stock tickers for Yahoo Finance API (e.g., ".DE" for Xetra).
    Default is [".DE"]. For other exchanges add additional suffixes to the list.
    :param crypto_ticker_suffixes: suffixes to add to crypto tickers for Yahoo Finance API (e.g., "-EUR").
    Default is ["-EUR"]. For other currencies add additional suffixes to the list.
    :return: Tuple (DataFrame with 'Ticker', 'Kurs' and 'Kursdatum' (ISO date or None) columns,
             list of tickers for which a stored fallback price was used).
    """
    # Mutable default argument guard
    if stock_ticker_suffixes is None:
        stock_ticker_suffixes = [".DE"]
    if crypto_ticker_suffixes is None:
        crypto_ticker_suffixes = ["-EUR"]

    today = pd.Timestamp.today()
    start = today.normalize() - pd.Timedelta(days=_PRICE_WINDOW_DAYS)
    logger.info(f"Kurszeitraum: {start.date()} bis {today.date()} (jüngster Schlusskurs wird verwendet)")

    # Process stock and ETF tickers – strip any existing suffix first
    stock_tickers = df[df["Art"].isin(["Aktie", "ETF"])]["Ticker"].str.replace(r"\..*$", "", regex=True).tolist()
    crypto_tickers = df[df["Art"] == "Krypto"]["Ticker"].str.replace(r"\-.*$", "", regex=True).tolist()
    logger.debug(f"Aktien/ETF-Ticker: {stock_tickers}")
    logger.debug(f"Krypto-Ticker: {crypto_tickers}")

    price_list = []

    def _fetch_prices(tickers, suffixes, asset_type):
        """Versucht Batch-Download; fällt bei Bedarf auf Einzel-Download zurück."""
        # Batch-Download: alle Suffix-Kombinationen auf einmal versuchen
        for suffix in suffixes:
            # Nur Ticker herunterladen, für die noch kein Kurs vorliegt
            already_found = {entry["Ticker"] for entry in price_list}
            remaining = [t for t in tickers if t not in already_found]
            if not remaining:
                break
            modified_tickers = [t + suffix for t in remaining]
            logger.debug(f"Batch-Download für {asset_type} mit Suffix '{suffix}': {modified_tickers}")
            try:
                batch = yf.download(modified_tickers, start=start, end=today, progress=False, auto_adjust=True)
                if batch.empty:
                    continue

                close = batch["Close"] if "Close" in batch.columns else batch
                # Normalisiere zu DataFrame, falls nur ein Ticker zurückkommt
                if isinstance(close, pd.Series):
                    close = close.to_frame(name=modified_tickers[0])

                for orig_ticker, mod_ticker in zip(remaining, modified_tickers, strict=True):
                    if mod_ticker in close.columns:
                        val = close[mod_ticker].dropna()
                        if not val.empty:
                            datum = pd.Timestamp(val.index[-1]).date().isoformat()
                            price_list.append({"Ticker": orig_ticker, "Kurs": float(val.iloc[-1]), "Kursdatum": datum})
                            logger.debug(
                                f"Kurs gefunden: {orig_ticker} = {float(val.iloc[-1]):.4f} vom {datum} (via {mod_ticker})"
                            )
            except Exception as e:
                logger.warning(f"Batch-Download fehlgeschlagen ({suffix}): {e}")

        # Für Ticker, für die noch kein Kurs gefunden wurde → Einzel-Fallback
        found = {entry["Ticker"] for entry in price_list}
        missing = [t for t in tickers if t not in found]
        for ticker in missing:
            price_found = False
            for suffix in suffixes:
                modified_ticker = ticker + suffix
                logger.debug(f"Einzel-Fallback: {modified_ticker}")
                try:
                    data = yf.download(modified_ticker, start=start, end=today, progress=False, auto_adjust=True)
                    if not data.empty and "Close" in data.columns:
                        val = data["Close"].dropna()
                        if not val.empty:
                            kurs = float(val.iloc[-1].item()) if hasattr(val.iloc[-1], "item") else float(val.iloc[-1])
                            datum = pd.Timestamp(val.index[-1]).date().isoformat()
                            price_list.append({"Ticker": ticker, "Kurs": kurs, "Kursdatum": datum})
                            logger.info(f"Kurs gefunden (Fallback): {ticker} = {kurs:.4f} vom {datum}")
                            price_found = True
                            break
                except Exception as e:
                    logger.warning(f"Fehler beim Download von '{modified_ticker}': {e}")
            if not price_found:
                logger.warning(f"Kein Kurs gefunden für '{ticker}' – wird als NaN gesetzt.")
                price_list.append({"Ticker": ticker, "Kurs": None, "Kursdatum": None})

    if stock_tickers:
        _fetch_prices(stock_tickers, stock_ticker_suffixes, "Aktie/ETF")
    if crypto_tickers:
        _fetch_prices(crypto_tickers, crypto_ticker_suffixes, "Krypto")

    # ------------------------------------------------------------------
    # Fallback-JSON: erfolgreich geladene Kurse speichern;
    # fehlende Kurse (None) aus dem Fallback ersetzen
    # ------------------------------------------------------------------
    fallback = _load_fallback()
    fallback_updated = False
    fallback_used = []  # Ticker, für die der Fallback-Kurs eingesetzt wurde

    for entry in price_list:
        ticker = entry["Ticker"]
        kurs = entry["Kurs"]
        if kurs is not None:
            # Aktuellen Kurs samt Datum in den Fallback schreiben
            neu = {"kurs": kurs, "datum": entry["Kursdatum"]}
            if fallback.get(ticker) != neu:
                fallback[ticker] = neu
                fallback_updated = True
            alter = _age_days(entry["Kursdatum"])
            if alter is not None and alter > _STALE_DAYS:
                logger.warning(
                    f"Kurs für '{ticker}' ist vom {entry['Kursdatum']} ({alter} Tage alt) – Ticker inaktiv/delistet?"
                )
        else:
            # Kurs fehlt → Fallback verwenden falls vorhanden
            if ticker in fallback:
                fb_kurs, fb_datum = _fallback_entry(fallback[ticker])
                entry["Kurs"], entry["Kursdatum"] = fb_kurs, fb_datum
                fallback_used.append(ticker)
                alter = _age_days(fb_datum)
                stand = f"vom {fb_datum}, {alter} Tage alt" if alter is not None else "Datum unbekannt"
                logger.warning(
                    f"Kein Live-Kurs für '{ticker}' – Fallback-Kurs aus JSON verwendet: {fb_kurs:.4f} ({stand})"
                )
            else:
                logger.warning(f"Kein Live-Kurs und kein Fallback für '{ticker}' – bleibt NaN.")

    if fallback_updated:
        _save_fallback(fallback)
        logger.info(f"Fallback-JSON aktualisiert: {_FALLBACK_JSON}")

    # Cash-Eintrag
    cash = pd.DataFrame({"Ticker": ["-"], "Kurs": [1.0], "Kursdatum": [None]})
    prices = pd.DataFrame(price_list)
    prices = pd.concat([prices, cash], ignore_index=True)
    logger.debug(f"Preisliste:\n{prices.to_string()}")
    # Kompakte INFO-Zusammenfassung
    found_count = prices["Kurs"].notna().sum()
    logger.info(f"Kurse geladen: {found_count}/{len(prices)} Positionen. Fallbacks: {fallback_used or 'keine'}")
    return prices, fallback_used
