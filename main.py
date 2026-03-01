import logging
import logging.handlers
import os
import sys
import timeit

import pandas as pd
from dotenv import load_dotenv

from scripts.data_download import download_csv_if_old, download_stock_price
from scripts.data_processing import calculate_relative_weighting, clean_etf_data
from scripts.file_handling import export_to_excel, read_etf_data
from scripts.plotting import (
    _eur,
    _pct,
    build_bar_chart,
    build_depot_table,
    build_heatmap,
    build_pie_chart,
    build_treemap,
    export_html_report,
)

# ---------------------------------------------------------------------------
# Logging konfigurieren
# ---------------------------------------------------------------------------
_LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s – %(message)s"

def _setup_logging():
    root = logging.getLogger()
    if root.handlers:          # Guard: nicht mehrfach konfigurieren (z.B. bei Re-Import)
        return
    root.setLevel(logging.DEBUG)

    # Console: INFO+
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(sh)

    # Haupt-Log: INFO+, max 5 MB, 3 Backups
    fh = logging.handlers.RotatingFileHandler(
        "portfolio_analysis.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(fh)

    # Error-Log: nur WARNING+ (separates File für schnelle Fehlerdiagnose)
    eh = logging.handlers.RotatingFileHandler(
        "portfolio_errors.log", maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    eh.setLevel(logging.WARNING)
    eh.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(eh)

    # Externe Logger auf WARNING kappen – yfinance loggt Delisting als ERROR (normales Verhalten)
    for name in ("yfinance", "peewee", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

_setup_logging()
logger = logging.getLogger(__name__)


def resolve_env_var(var):
    """Rekursives Auflösen von Umgebungsvariablen in Pfaden."""
    if var is None:
        return None
    previous, resolved = None, os.path.expandvars(var)
    while previous != resolved:
        previous, resolved = resolved, os.path.expandvars(resolved)
    return resolved


def main():
    start = timeit.default_timer()

    # ------------------------------------------------------------------
    # Umgebungsvariablen laden
    # ------------------------------------------------------------------
    load_dotenv()

    DOWNLOAD_PATH = resolve_env_var(os.getenv('DOWNLOAD_PATH'))
    SAVE_PATH     = resolve_env_var(os.getenv('SAVE_PATH'))
    INPUT_FILE    = resolve_env_var(os.getenv('INPUT_FILE'))
    OUTPUT_FILE   = resolve_env_var(os.getenv('OUTPUT_FILE'))

    CSV_URL               = [u.strip() for u in os.getenv('CSV_URL', '').split(',')]
    ETF_CSV_FILE          = [f.strip() for f in os.getenv('ETF_CSV_FILE', '').split(',')]
    STOCK_TICKER_SUFFIXES  = [s.strip() for s in os.getenv('STOCK_TICKER_SUFFIXES', '').split(',')]
    CRYPTO_TICKER_SUFFIXES = [s.strip() for s in os.getenv('CRYPTO_TICKER_SUFFIXES', '').split(',')]

    # Pflicht-Konfiguration validieren
    _missing = [k for k, v in {
        'DOWNLOAD_PATH': DOWNLOAD_PATH, 'SAVE_PATH': SAVE_PATH,
        'INPUT_FILE': INPUT_FILE, 'OUTPUT_FILE': OUTPUT_FILE,
    }.items() if not v]
    if _missing:
        logger.error(f"Fehlende Pflicht-Umgebungsvariablen in .env: {_missing}. Abbruch.")
        sys.exit(1)

    if not ETF_CSV_FILE or ETF_CSV_FILE == ['']:
        logger.error("ETF_CSV_FILE ist leer – keine ETF-Dateien konfiguriert. Abbruch.")
        sys.exit(1)

    # Verzeichnisse prüfen
    for label, path in [('DOWNLOAD_PATH', DOWNLOAD_PATH), ('SAVE_PATH', SAVE_PATH)]:
        if not os.path.isdir(path):
            logger.warning(f"{label} '{path}' existiert nicht – wird erstellt.")
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                logger.error(f"Konnte {label} '{path}' nicht erstellen: {e}. Abbruch.")
                sys.exit(1)

    logger.info(
        f"Konfiguration geladen:\n"
        f"  DOWNLOAD_PATH:         {DOWNLOAD_PATH}\n"
        f"  SAVE_PATH:             {SAVE_PATH}\n"
        f"  INPUT_FILE:            {INPUT_FILE}\n"
        f"  OUTPUT_FILE:           {OUTPUT_FILE}\n"
        f"  ETF_CSV_FILE:          {ETF_CSV_FILE}\n"
        f"  STOCK_TICKER_SUFFIXES: {STOCK_TICKER_SUFFIXES}\n"
        f"  CRYPTO_TICKER_SUFFIXES:{CRYPTO_TICKER_SUFFIXES}"
    )

    # ------------------------------------------------------------------
    # 1. CSV-Daten herunterladen
    # ------------------------------------------------------------------
    download_csv_if_old(CSV_URL, DOWNLOAD_PATH, ETF_CSV_FILE)

    # ------------------------------------------------------------------
    # 2. ETF-Daten einlesen & bereinigen
    # ------------------------------------------------------------------
    etf_data_list = [
        df for f in ETF_CSV_FILE
        if (df := read_etf_data(os.path.join(DOWNLOAD_PATH, f))) is not None
    ]

    if not etf_data_list:
        logger.error("Keine ETF-Daten verfügbar. Abbruch.")
        sys.exit(1)

    etf_data = clean_etf_data(pd.concat(etf_data_list, ignore_index=True))
    logger.info(f"ETF-Daten geladen und bereinigt: {len(etf_data)} verwertbare Positionen.")

    # ------------------------------------------------------------------
    # 3. Depot-Daten einlesen
    # ------------------------------------------------------------------
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Eingabedatei '{INPUT_FILE}' nicht gefunden. Abbruch.")
        sys.exit(1)

    depot = pd.read_excel(INPUT_FILE)
    logger.info(f"Depot geladen: {depot.shape[0]} Positionen.")

    _required_cols = {'Art', 'Position', 'Ticker', 'Anteile'}
    _missing_cols  = _required_cols - set(depot.columns)
    if _missing_cols:
        logger.error(f"Depot-Excel fehlt Pflicht-Spalten: {_missing_cols}. Abbruch.")
        sys.exit(1)

    if depot.empty:
        logger.error("Depot-Excel ist leer. Abbruch.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 4. Aktienkurse herunterladen & Merge
    # ------------------------------------------------------------------
    stock_prices, fallback_used = download_stock_price(depot, STOCK_TICKER_SUFFIXES, CRYPTO_TICKER_SUFFIXES)

    if stock_prices is None or stock_prices.empty:
        logger.error("Kursdownload fehlgeschlagen. Abbruch.")
        sys.exit(1)

    # Originalen Ticker (aus Excel, z.B. '2B7K.DE') sichern – Merge überschreibt Ticker-Spalte
    depot["Ticker_orig_excel"] = depot["Ticker"]

    # Ticker-Suffix bereinigen für den Merge
    depot["Ticker_clean"] = depot["Ticker"].str.replace(r'\..*$', '', regex=True)
    depot.loc[depot['Art'] == 'Krypto', 'Ticker_clean'] = \
        depot['Ticker'].str.replace(r'\-.*$', '', regex=True)

    stock_prices = stock_prices.drop_duplicates(subset='Ticker', keep='first')
    depot = depot.merge(
        stock_prices[['Ticker', 'Kurs']],
        left_on='Ticker_clean', right_on='Ticker',
        how='left', suffixes=('_orig', '')
    )
    # Merge-Hilfsspalten entfernen, originalen Ticker wiederherstellen
    depot.drop(columns=['Ticker_orig', 'Ticker_clean'], errors='ignore', inplace=True)
    depot['Ticker'] = depot['Ticker_orig_excel']
    depot.drop(columns=['Ticker_orig_excel'], inplace=True)

    depot["Kurs"]     = pd.to_numeric(depot["Kurs"],    errors='coerce')
    depot["Anteile"]  = pd.to_numeric(depot["Anteile"], errors='coerce')
    depot["Marktwert"] = depot["Anteile"] * depot["Kurs"]

    missing_kurs = depot[depot["Kurs"].isna()]
    if not missing_kurs.empty:
        logger.warning(
            f"Für {len(missing_kurs)} Position(en) kein Kurs – Gesamtwert UNVOLLSTÄNDIG:\n"
            + missing_kurs[["Ticker", "Position", "Art"]].to_string(index=False)
        )

    gesamtwert_vollstaendig = missing_kurs.empty
    depot["Marktwert (%)"] = depot["Marktwert"] / depot["Marktwert"].sum() * 100
    logger.debug(f"Depot nach Kursberechnung:\n{depot.to_string()}")
    n_missing = depot['Kurs'].isna().sum()
    logger.info(f"Depot berechnet: {len(depot)} Positionen, Gesamtwert {depot['Marktwert'].sum():,.2f} €" +
                (f", {n_missing} ohne Kurs" if n_missing else ""))

    # ------------------------------------------------------------------
    # 5. Relative Gewichtung berechnen
    # ------------------------------------------------------------------
    try:
        etf_data, message = calculate_relative_weighting(etf_data, depot)
        logger.info(message)
    except Exception as e:
        logger.error(f"Fehler bei der Gewichtungsberechnung: {e}")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 6. Assets zusammenführen
    # ------------------------------------------------------------------
    assets = (
        depot[depot["Art"].isin(["Aktie", "Krypto"])]
        [["Ticker", "Art", "Position", "Sektor", "Standort", "Marktwert (%)"]]
        .rename(columns={
            "Ticker":       "Emittententicker",
            "Position":     "Name",
            "Art":          "ETF",
            "Marktwert (%)": "relative Gewichtung (%)",
        })
        .copy()
    )
    depot_data = pd.concat([etf_data, assets], ignore_index=True, sort=False)

    # Chart-DataFrame: nur Zeilen mit echtem Sektor (kein '-', 'nan', Cash-Derivate)
    # 'Sonstige' bleibt drin – unbekannte Sektoren/Länder werden dort gebündelt
    _EXCL_SECTORS   = {'-', 'nan', 'Cash und/oder Derivate', 'Cash and/or Derivatives'}
    _EXCL_LOCATIONS = {'-', 'nan', 'Krypto', 'Cash', 'Cash (Euro)'}
    depot_data_chart = depot_data[
        depot_data['Sektor'].notna() &
        (~depot_data['Sektor'].astype(str).isin(_EXCL_SECTORS))
    ].copy()

    # Krypto & Cash: nur ergänzen wenn sie NICHT bereits über assets in depot_data_chart sind
    # (Krypto hat Sektor='Krypto' → übersteht den Sektor-Filter bereits, wäre sonst doppelt)
    bereits_enthalten = set(depot_data_chart['Name'].dropna().unique())
    extra_rows = []
    for art in ['Krypto', 'Cash']:
        positionen = depot[depot['Art'] == art]
        for _, row in positionen.iterrows():
            if (pd.notna(row.get('Marktwert (%)'))
                    and row['Marktwert (%)'] > 0
                    and row['Position'] not in bereits_enthalten):
                extra_rows.append({
                    'Name':                    row['Position'],
                    'ETF':                     art,
                    'Sektor':                  art,
                    'Standort':                art,
                    'Emittententicker':        row.get('Ticker', ''),
                    'relative Gewichtung (%)': row['Marktwert (%)'],
                })
    if extra_rows:
        depot_data_chart = pd.concat(
            [depot_data_chart, pd.DataFrame(extra_rows)],
            ignore_index=True, sort=False
        )

    # ------------------------------------------------------------------
    # 7. Auswertungen erstellen
    # ------------------------------------------------------------------
    def _agg(df, group_col, value_col, out_col):
        return (df.groupby(group_col)[value_col].sum().reset_index()
                .rename(columns={value_col: out_col})
                .sort_values(out_col, ascending=False))

    depot_data_sectors   = _agg(depot_data_chart, 'Sektor',   'relative Gewichtung (%)', 'Sektorgewichtung (%)')

    # depot_data_etfs: Cash explizit ergänzen – Cash ist weder in etf_data noch in assets
    depot_data_etfs = _agg(depot_data, 'ETF', 'relative Gewichtung (%)', 'ETF-Gewichtung (%)')
    cash_pct = depot.loc[depot['Art'] == 'Cash', 'Marktwert (%)'].sum()
    if cash_pct > 0:
        cash_row = pd.DataFrame([{'ETF': 'Cash', 'ETF-Gewichtung (%)': cash_pct}])
        depot_data_etfs = pd.concat([depot_data_etfs, cash_row], ignore_index=True).sort_values(
            'ETF-Gewichtung (%)', ascending=False
        )

    loc_df = depot_data_chart[
        depot_data_chart['Standort'].notna() &
        (~depot_data_chart['Standort'].astype(str).isin(_EXCL_LOCATIONS))
    ]
    depot_data_locations = _agg(loc_df, 'Standort', 'relative Gewichtung (%)', 'Ländergewichtung (%)')

    depot_data_stocks = (
        depot_data_chart.groupby('Name').agg(
            Emittententicker=('Emittententicker', 'first'),
            Gesamtgewichtung=('relative Gewichtung (%)', 'sum'),
            Sektor=('Sektor', 'first'),
            Standort=('Standort', 'first'),
        ).reset_index()
        .rename(columns={'Gesamtgewichtung': 'Gesamtgewichtung (%)'})
        .sort_values('Gesamtgewichtung (%)', ascending=False)
    )
    # Hinweis: Cash ist bereits über extra_rows in depot_data_chart und
    # damit automatisch im groupby-Ergebnis enthalten – kein separater Append nötig

    # ------------------------------------------------------------------
    # 8. Excel-Export
    # ------------------------------------------------------------------
    export_to_excel(OUTPUT_FILE, depot, depot_data, depot_data_stocks,
                    depot_data_etfs, depot_data_sectors, depot_data_locations)

    # ------------------------------------------------------------------
    # 9. HTML-Report erstellen
    # ------------------------------------------------------------------
    gesamtwert = depot["Marktwert"].sum()
    gesamtwert_label = _eur(gesamtwert) if gesamtwert_vollstaendig else f"{_eur(gesamtwert)} ⚠️ (unvollständig)"

    # HHI-Diversifikations-Score: Basis = depot_data_stocks (ETF-Durchblick)
    # → jede Einzelposition mit ihrem echten anteiligen Gewicht, nicht ETFs als Blackbox
    # Normalisierung auf 100 nötig da ETF-Durchblick die Summe > 100% macht
    # TODO: HHI-Berechnung überprüfen – aktuell auf depot_data_stocks (ETF-Durchblick,
    #       normalisiert auf 100%). Ergibt trotzdem ~3 statt erwartetem ~0.1-0.5.
    #       Mögliche Ursachen:
    #       1. depot_data_stocks enthält noch Duplikate (gleiche Position aus mehreren ETFs)
    #       2. Normalisierung fehlerhaft weil Summe der Gewichtungen weit von 100 abweicht
    #       3. Schwellenwerte müssen nochmals kalibriert werden
    #       Debugging: weights.describe() und weights.nlargest(10) loggen um Ausreißer zu finden
    weights   = depot_data_stocks['Gesamtgewichtung (%)'].dropna()
    weights   = weights[weights > 0]
    weights_n = weights / weights.sum() * 100   # auf 100% normalisieren
    hhi_score = (weights_n ** 2).sum() / 100
    n_positionen = len(depot_data_stocks)
    n_sektoren   = depot_data_chart['Sektor'].nunique()
    n_laender    = depot_data_chart[
        depot_data_chart['Standort'].notna() &
        (~depot_data_chart['Standort'].astype(str).isin(_EXCL_LOCATIONS))
    ]['Standort'].nunique()
    if hhi_score < 0.10:
        hhi_stufe = "Sehr gut diversifiziert"
    elif hhi_score < 0.50:
        hhi_stufe = "Gut diversifiziert"
    elif hhi_score < 1.50:
        hhi_stufe = "Mäßig diversifiziert"
    else:
        hhi_stufe = "Konzentriert"
    hhi_label = (
        f"{hhi_stufe}<br>"
        f"<small>HHI {hhi_score:.2f} · "
        f"{n_positionen} Positionen · "
        f"{n_sektoren} Sektoren · "
        f"{n_laender} Länder</small>"
    )

    # Anzahl je Assetklasse für Positionen-Card
    art_counts = depot["Art"].value_counts()

    # KPI-Cards – gruppiert: Depot | Assetklassen | Qualität
    depot_summary = {
        # --- Depot-Übersicht ---
        "Gesamtwert":       gesamtwert_label,
        "Positionen":       " / ".join(f"{art_counts.get(a, 0)} {a}s" for a in ["ETF", "Aktie", "Krypto"]) + f" + {art_counts.get('Cash', 0)} Cash",
        # --- Assetklassen-Anteile ---
        "ETF-Anteil":       _pct(depot.loc[depot['Art'] == 'ETF',    'Marktwert (%)'].sum()),
        "Aktien-Anteil":    _pct(depot.loc[depot['Art'] == 'Aktie',  'Marktwert (%)'].sum()),
        "Krypto-Anteil":    _pct(depot.loc[depot['Art'] == 'Krypto', 'Marktwert (%)'].sum()),
        "Cash-Anteil":      _pct(depot.loc[depot['Art'] == 'Cash',   'Marktwert (%)'].sum()),
        # --- Qualität ---
        "Diversifikation":  hhi_label,
    }
    if fallback_used:
        depot_summary["⚠️ Fallback-Kurse"] = (
            f"{', '.join(fallback_used)} – kein Live-Kurs, historischen Wert verwendet"
        )

    # Sektor-Heatmap: Gewichtung je Sektor × ETF/Quelle
    # Spalten = ETF-Name oder 'Aktie'/'Krypto', Zeilen = Sektor
    heatmap_df = depot_data_chart.copy()
    heatmap_df['Quelle'] = heatmap_df['ETF']
    sector_pivot = (
        heatmap_df.groupby(['Sektor', 'Quelle'])['relative Gewichtung (%)']
        .sum()
        .unstack(fill_value=0)
        .round(2)
    )
    # Sektoren absteigend nach Gesamtgewichtung sortieren
    sector_pivot = sector_pivot.loc[sector_pivot.sum(axis=1).sort_values(ascending=False).index]

    # Treemap Anlageart → Position (Depot-Ebene, kein ETF-Durchblick)
    treemap_art_df = depot[depot['Marktwert (%)'] > 0][['Art', 'Position', 'Marktwert (%)']].copy()

    # Warnung wenn Positionen ohne Marktwert im Depot sind – sie erscheinen nicht im Pie-Chart
    _no_value = depot[depot['Marktwert (%)'].isna() | (depot['Marktwert (%)'] <= 0)]
    if not _no_value.empty:
        logger.warning(
            f"{len(_no_value)} Position(en) ohne Marktwert – nicht im Übersichts-Chart:\n"
            + _no_value[['Ticker', 'Position', 'Art']].to_string(index=False)
        )

    report_sections = [
        {"title": "Depotübersicht",
         "html": build_depot_table(depot),
         "description": "Alle Positionen mit aktuellem Kurs, Marktwert und Depotanteil."},
        {"title": "Übersicht nach Depot",
         "fig": build_pie_chart(depot, 'Marktwert (%)', 'Position', 'Übersicht nach Depot'),
         "description": "Marktwertsanteil jeder Depotposition."},
        {"title": "Kapitalverteilung: Anlageart → Position",
         "fig": build_treemap(treemap_art_df, ['Art', 'Position'], 'Marktwert (%)',
                              'Kapitalverteilung: Anlageart → Position'),
         "description": "Kapitalverteilung auf Depot-Ebene nach Anlageart und Position – ersetzt den einfachen Anlageart-Pie."},
        {"title": "Top 20 Positionen – Balken",
         "fig": build_bar_chart(depot_data_stocks, 'Gesamtgewichtung (%)', 'Name', 'Top 20 Positionen', top_n=20),
         "description": "Die 20 größten Einzelpositionen nach Gesamtgewichtung (inkl. ETF-Durchblick)."},

        {"title": "Länder – Treemap",
         "fig": build_treemap(
             depot_data_chart[
                 depot_data_chart['Standort'].notna() &
                 (~depot_data_chart['Standort'].astype(str).isin(_EXCL_LOCATIONS)) &
                 (depot_data_chart['relative Gewichtung (%)'] > 0)
             ]
             .dropna(subset=['Standort', 'Name'])
             .groupby(['Standort', 'Name'], as_index=False)['relative Gewichtung (%)']
             .sum(),
             ['Standort', 'Name'], 'relative Gewichtung (%)', 'Ländergewichtung'),
         "description": "Geografische Gewichtung inkl. ETF-Durchblick – Fläche entspricht der Gewichtung, Unterebene zeigt Einzelpositionen."},
        {"title": "Sektor-Heatmap: ETF-Überschneidungen",
         "fig": build_heatmap(sector_pivot,
                              'Sektorgewichtung (%) je ETF / Assetklasse',
                              colorscale='Blues'),
         "description": (
             "Zeigt wie stark jeder Sektor in jedem ETF / jeder Assetklasse gewichtet ist (in %). "
             "Überschneidungen zeigen Klumpenrisiken."
         )},
    ]

    if {'Sektor', 'Name', 'relative Gewichtung (%)'}.issubset(depot_data_chart.columns):
        # Auf Name-Ebene aggregieren → identische Gewichtungen wie Top-20-Balken
        treemap_data = (
            depot_data_chart[depot_data_chart['relative Gewichtung (%)'] > 0]
            .dropna(subset=['Sektor', 'Name'])
            .groupby(['Sektor', 'Name'], as_index=False)['relative Gewichtung (%)']
            .sum()
        )
        report_sections.append({
            "title": "Treemap: Sektor → Position",
            "fig": build_treemap(treemap_data, ['Sektor', 'Name'], 'relative Gewichtung (%)',
                                 'Treemap: Sektor → Position'),
            "description": "Hierarchische Ansicht aller Positionen inkl. ETF-Durchblick – Fläche entspricht der Gewichtung.",
        })

    report_file = os.path.join(SAVE_PATH, "portfolio_report.html")
    export_html_report(report_sections, report_file, depot_summary=depot_summary)

    logger.info(f"Laufzeit: {timeit.default_timer() - start:.1f} Sekunden")
    logger.info(f"Report: {report_file}")


if __name__ == "__main__":
    main()
