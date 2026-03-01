# tests/test_file_handling.py
"""
Unit Tests für scripts/file_handling.py

Getestet werden:
- read_etf_data: Erfolgreicher Lesevorgang, fehlende Datei, Skip-Rows, ETF-Name
- export_to_excel: Alle Sheets werden geschrieben, fehlende Datei, leere DataFrames
"""

import logging
import os

import pandas as pd

from scripts.file_handling import export_to_excel, read_etf_data

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_csv(tmp_path, content, filename="test_etf.csv"):
    """Schreibt eine CSV-Datei in tmp_path und gibt den Pfad zurück."""
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def _sample_dfs():
    """Gibt sechs minimale DataFrames für export_to_excel zurück."""
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    return df, df.copy(), df.copy(), df.copy(), df.copy(), df.copy()


# ---------------------------------------------------------------------------
# Tests: read_etf_data
# ---------------------------------------------------------------------------

class TestReadEtfData:
    def test_liest_gueltige_csv(self, tmp_path):
        """Zwei Header-Zeilen (skip_rows=2) + Daten korrekt lesen."""
        content = "Zeile 1\nZeile 2\nName,Sektor,Gewichtung (%)\nApple,IT,5.0\nMicrosoft,IT,3.0\n"
        path = _make_csv(tmp_path, content)
        result = read_etf_data(path, skip_rows=2)
        assert result is not None
        assert len(result) == 2
        assert "Name" in result.columns

    def test_etf_name_entspricht_dateiname_ohne_extension(self, tmp_path):
        content = "skip\nskip\nName,Sektor\nApple,IT\n"
        path = _make_csv(tmp_path, content, filename="iShares MSCI World.csv")
        result = read_etf_data(path, skip_rows=2)
        assert result is not None
        assert (result["ETF"] == "iShares MSCI World").all()

    def test_gibt_none_zurueck_wenn_datei_fehlt(self, tmp_path):
        result = read_etf_data(str(tmp_path / "nicht_vorhanden.csv"))
        assert result is None

    def test_loggt_fehler_bei_fehlender_datei(self, tmp_path, caplog):
        with caplog.at_level(logging.ERROR, logger="scripts.file_handling"):
            read_etf_data(str(tmp_path / "fehlt.csv"))
        assert any("nicht gefunden" in r.message for r in caplog.records)

    def test_gibt_none_bei_ungueltigem_encoding(self, tmp_path):
        """Datei mit ungültigen UTF-8-Bytes → None statt Exception."""
        path = tmp_path / "broken.csv"
        # \xff\xfe sind in UTF-8 ungültig und können nicht als latin-1 fehlinterpretiert werden
        path.write_bytes(b"skip\nskip\nName\n\xff\xfe\n")
        result = read_etf_data(str(path), skip_rows=2, encoding="utf-8")
        assert result is None

    def test_kein_skiprows(self, tmp_path):
        """skip_rows=0 → alle Zeilen werden gelesen."""
        content = "Name,Sektor\nApple,IT\n"
        path = _make_csv(tmp_path, content)
        result = read_etf_data(path, skip_rows=0)
        assert result is not None
        assert len(result) == 1

    def test_semikolon_delimiter(self, tmp_path):
        """Semikolon als Trennzeichen."""
        content = "skip\nskip\nName;Sektor\nApple;IT\n"
        path = _make_csv(tmp_path, content)
        result = read_etf_data(path, skip_rows=2, delimiter=";")
        assert result is not None
        assert "Sektor" in result.columns

    def test_leere_csv_nach_skiprows(self, tmp_path):
        """CSV mit nur Header-Zeilen → leeres DataFrame, kein Crash."""
        content = "skip\nskip\nName,Sektor\n"
        path = _make_csv(tmp_path, content)
        result = read_etf_data(path, skip_rows=2)
        assert result is not None
        assert result.empty


# ---------------------------------------------------------------------------
# Tests: export_to_excel
# ---------------------------------------------------------------------------

class TestExportToExcel:
    def test_erstellt_excel_datei(self, tmp_path):
        """Export soll eine gültige Excel-Datei erzeugen."""
        output = str(tmp_path / "test_output.xlsx")
        depot, data, stocks, etfs, sectors, locs = _sample_dfs()
        export_to_excel(output, depot, data, stocks, etfs, sectors, locs)
        assert os.path.exists(output)

    def test_alle_sheets_vorhanden(self, tmp_path):
        output = str(tmp_path / "test_output.xlsx")
        depot, data, stocks, etfs, sectors, locs = _sample_dfs()
        export_to_excel(output, depot, data, stocks, etfs, sectors, locs)
        xl = pd.ExcelFile(output)
        expected = {"Depotwerte", "Datengrundlage", "Aktien", "ETFs", "Sektoren", "Länder"}
        assert expected == set(xl.sheet_names)

    def test_sheet_inhalte_korrekt(self, tmp_path):
        output = str(tmp_path / "test_output.xlsx")
        depot = pd.DataFrame({"Position": ["Apple", "Bitcoin"], "Marktwert": [1000.0, 500.0]})
        _, data, stocks, etfs, sectors, locs = _sample_dfs()
        export_to_excel(output, depot, data, stocks, etfs, sectors, locs)
        result = pd.read_excel(output, sheet_name="Depotwerte")
        assert list(result["Position"]) == ["Apple", "Bitcoin"]

    def test_leere_dataframes_kein_crash(self, tmp_path):
        """Alle leeren DataFrames → Export soll trotzdem funktionieren."""
        output = str(tmp_path / "empty.xlsx")
        empty = pd.DataFrame()
        export_to_excel(output, empty, empty, empty, empty, empty, empty)
        assert os.path.exists(output)

    def test_loggt_fehler_bei_nicht_schreibbarem_pfad(self, caplog):
        """Nicht schreibbarer Pfad → ERROR geloggt, kein unkontrollierter Absturz."""
        depot, data, stocks, etfs, sectors, locs = _sample_dfs()
        with caplog.at_level(logging.ERROR, logger="scripts.file_handling"):
            export_to_excel(
                "/nicht/existierender/pfad/output.xlsx",
                depot, data, stocks, etfs, sectors, locs
            )
        assert any("Fehler" in r.message for r in caplog.records)

    def test_loggt_erfolg(self, tmp_path, caplog):
        """Erfolgreicher Export → INFO-Log mit Dateinamen."""
        output = str(tmp_path / "log_test.xlsx")
        depot, data, stocks, etfs, sectors, locs = _sample_dfs()
        with caplog.at_level(logging.INFO, logger="scripts.file_handling"):
            export_to_excel(output, depot, data, stocks, etfs, sectors, locs)
        assert any("erfolgreich" in r.message for r in caplog.records)

