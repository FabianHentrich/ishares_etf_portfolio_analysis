# tests/test_plotting.py
"""
Unit Tests für scripts/plotting.py

Getestet werden:
- _de: Deutsches Zahlenformat
- build_depot_table: HTML-Ausgabe, Spalten, Sortierung
- build_pie_chart / build_bar_chart / build_treemap / build_heatmap: Figure-Struktur
"""

import pandas as pd
import plotly.graph_objects as go

from scripts.plotting import (
    _de,
    build_bar_chart,
    build_depot_table,
    build_heatmap,
    build_pie_chart,
    build_treemap,
)

# ---------------------------------------------------------------------------
# Tests: _de (deutsches Zahlenformat)
# ---------------------------------------------------------------------------

class TestDeFormat:
    def test_tausenderpunkt(self):
        assert _de(1234.56) == "1.234,56"

    def test_dezimalkomma(self):
        result = _de(3.14)
        assert "," in result
        # Dezimaltrenner ist Komma, kein Punkt
        parts = result.split(",")
        assert len(parts) == 2
        assert parts[1] == "14"

    def test_mit_einheit(self):
        assert _de(5.5, 2, "%") == "5,50 %"
        assert _de(1234.0, 2, "€") == "1.234,00 €"

    def test_null_wert(self):
        assert _de(0.0) == "0,00"

    def test_negative_zahl(self):
        result = _de(-42.5)
        assert "-" in result
        assert "42" in result

    def test_nan_gibt_strich_zurueck(self):
        assert _de(float("nan")) == "–"

    def test_none_gibt_strich_zurueck(self):
        assert _de(None) == "–"

    def test_dezimalstellen(self):
        assert _de(1.0, 4) == "1,0000"
        assert _de(1.0, 0) == "1"

    def test_kleine_zahl_kein_tausenderpunkt(self):
        result = _de(0.034, 2, "%")
        assert result == "0,03 %"

    def test_grosse_zahl_mit_tausenderpunkten(self):
        result = _de(1234567.89)
        assert "1.234.567" in result

    def test_million(self):
        result = _de(1_000_000.0, 2)
        assert "1.000.000" in result


# ---------------------------------------------------------------------------
# Tests: build_depot_table
# ---------------------------------------------------------------------------

class TestBuildDepotTable:
    def _sample_depot(self):
        return pd.DataFrame({
            "Ticker":       ["AAPL", "BTC", "-"],
            "Art":          ["Aktie", "Krypto", "Cash"],
            "Position":     ["Apple Inc.", "Bitcoin", "Cash"],
            "Sektor":       ["Technologie", "Krypto", "Cash"],
            "Standort":     ["USA", "Krypto", "Cash"],
            "Anteile":      [10.0, 0.01, 1000.0],
            "Kurs":         [150.0, 45000.0, 1.0],
            "Marktwert":    [1500.0, 450.0, 1000.0],
            "Marktwert (%)": [50.83, 15.25, 33.92],
        })

    def test_gibt_html_zurueck(self):
        html = build_depot_table(self._sample_depot())
        assert isinstance(html, str)
        assert "<table" in html

    def test_enthaelt_alle_positionen(self):
        html = build_depot_table(self._sample_depot())
        assert "Apple Inc." in html
        assert "Bitcoin" in html
        assert "Cash" in html

    def test_enthaelt_suchfeld(self):
        html = build_depot_table(self._sample_depot())
        assert "table-search" in html

    def test_enthaelt_sortierbare_spalten(self):
        html = build_depot_table(self._sample_depot())
        assert "sortable" in html

    def test_deutsches_zahlenformat_in_tabelle(self):
        html = build_depot_table(self._sample_depot())
        # Deutsches Format: Punkt als Tausender, Komma als Dezimal
        assert "1.500,00" in html or "1.000,00" in html

    def test_nan_kurs_zeigt_strich(self):
        depot = self._sample_depot()
        depot.loc[0, "Kurs"] = float("nan")
        html = build_depot_table(depot)
        assert "–" in html

    def test_leeres_depot_gibt_tabelle_zurueck(self):
        empty = pd.DataFrame(columns=["Ticker", "Art", "Position", "Sektor",
                                       "Standort", "Anteile", "Kurs", "Marktwert", "Marktwert (%)"])
        html = build_depot_table(empty)
        assert "<table" in html

    def test_nur_cash_position(self):
        depot = pd.DataFrame({
            "Ticker":        ["-"],
            "Art":           ["Cash"],
            "Position":      ["Cash"],
            "Sektor":        ["Cash"],
            "Standort":      ["Cash (Euro)"],
            "Anteile":       [2500.0],
            "Kurs":          [1.0],
            "Marktwert":     [2500.0],
            "Marktwert (%)": [100.0],
        })
        html = build_depot_table(depot)
        assert "Cash" in html
        assert "2.500,00" in html


# ---------------------------------------------------------------------------
# Tests: build_pie_chart
# ---------------------------------------------------------------------------

class TestBuildPieChart:
    def _sample_df(self):
        return pd.DataFrame({
            "Art":           ["ETF", "Aktie", "Cash"],
            "Marktwert (%)": [60.0, 25.0, 15.0],
        })

    def test_gibt_figure_zurueck(self):
        fig = build_pie_chart(self._sample_df(), "Marktwert (%)", "Art", "Test")
        assert fig is not None

    def test_figure_hat_daten(self):
        fig = build_pie_chart(self._sample_df(), "Marktwert (%)", "Art", "Test")
        assert len(fig.data) > 0

    def test_ignoriert_null_werte(self):
        df = self._sample_df().copy()
        df.loc[3] = [None, 10.0]
        fig = build_pie_chart(df, "Marktwert (%)", "Art", "Test")
        assert fig is not None

    def test_ignoriert_null_gewichtungen(self):
        df = pd.DataFrame({"Art": ["ETF", "Aktie"], "Marktwert (%)": [0.0, 25.0]})
        fig = build_pie_chart(df, "Marktwert (%)", "Art", "Test")
        # Nur Aktie sollte im Chart sein
        assert len(fig.data[0]["values"]) == 1


# ---------------------------------------------------------------------------
# Tests: build_bar_chart
# ---------------------------------------------------------------------------

class TestBuildBarChart:
    def _sample_df(self):
        return pd.DataFrame({
            "Name":                ["Apple", "Microsoft", "Google", "Amazon"],
            "Gesamtgewichtung (%)": [5.5, 4.2, 3.8, 2.1],
        })

    def test_gibt_figure_zurueck(self):
        fig = build_bar_chart(self._sample_df(), "Gesamtgewichtung (%)", "Name", "Top Aktien")
        assert fig is not None

    def test_top_n_begrenzt_eintraege(self):
        df = pd.DataFrame({
            "Name": [f"Aktie {i}" for i in range(30)],
            "Wert": list(range(30)),
        })
        fig = build_bar_chart(df, "Wert", "Name", "Test", top_n=10)
        assert len(fig.data[0]["y"]) <= 10

    def test_nimmt_groesste_werte(self):
        fig = build_bar_chart(self._sample_df(), "Gesamtgewichtung (%)", "Name", "Test", top_n=2)
        labels = list(fig.data[0]["y"])
        assert "Apple" in labels
        assert "Microsoft" in labels
        assert "Amazon" not in labels

    def test_leerer_dataframe_kein_crash(self):
        df = pd.DataFrame({"Name": [], "Wert": []})
        # Soll keinen Fehler werfen
        fig = build_bar_chart(df, "Wert", "Name", "Test")
        assert fig is not None


# ---------------------------------------------------------------------------
# Tests: build_treemap
# ---------------------------------------------------------------------------

class TestBuildTreemap:
    def _sample_df(self):
        return pd.DataFrame({
            "Sektor":                ["Technologie", "Technologie", "Finanzen"],
            "Name":                  ["Apple", "Microsoft", "JPMorgan"],
            "relative Gewichtung (%)": [5.0, 4.0, 3.0],
        })

    def test_gibt_figure_zurueck(self):
        fig = build_treemap(self._sample_df(), ["Sektor", "Name"], "relative Gewichtung (%)", "Test")
        assert fig is not None

    def test_einstufige_hierarchie(self):
        df = pd.DataFrame({"Sektor": ["IT", "Finanzen"], "Wert": [60.0, 40.0]})
        fig = build_treemap(df, ["Sektor"], "Wert", "Test")
        assert fig is not None


# ---------------------------------------------------------------------------
# Tests: build_heatmap
# ---------------------------------------------------------------------------

class TestBuildHeatmap:
    def _sample_pivot(self):
        return pd.DataFrame(
            [[5.0, 2.0, 0.0],
             [1.0, 3.0, 4.0]],
            index=["Technologie", "Finanzen"],
            columns=["ETF A", "ETF B", "Aktie"],
        )

    def test_gibt_figure_zurueck(self):
        fig = build_heatmap(self._sample_pivot(), "Test Heatmap")
        assert fig is not None

    def test_figure_ist_heatmap_typ(self):
        fig = build_heatmap(self._sample_pivot(), "Test")
        assert isinstance(fig.data[0], go.Heatmap)

    def test_annotationen_sind_deutsches_format(self):
        fig = build_heatmap(self._sample_pivot(), "Test")
        texts = fig.data[0]["text"]
        # Wert 5.0 → "5,00 %" im deutschen Format
        flat = [t for row in texts for t in row if t]
        assert any("," in t for t in flat)

    def test_null_werte_haben_leere_annotation(self):
        fig = build_heatmap(self._sample_pivot(), "Test")
        texts = fig.data[0]["text"]
        # Position [0][2] = 0.0 → leerer String
        assert texts[0][2] == ""

    def test_dimensionen_korrekt(self):
        pivot = self._sample_pivot()
        fig = build_heatmap(pivot, "Test")
        assert fig.data[0]["z"].shape == (2, 3)
        assert fig.data[0]["z"].shape == (2, 3)

