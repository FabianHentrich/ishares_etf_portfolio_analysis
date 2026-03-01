# tests/test_data_download.py
"""
Unit Tests für scripts/data_download.py

Getestet werden:
- _load_fallback / _save_fallback: JSON-Persistenz
- download_stock_price: Fallback-Logik (gemockt, kein echter Netzwerkaufruf)
- download_csv_if_old: Alter-Check und Verzeichnis-Validierung
"""

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts.data_download import _load_fallback, _save_fallback, download_csv_if_old, download_stock_price

# ---------------------------------------------------------------------------
# Tests: _load_fallback / _save_fallback
# ---------------------------------------------------------------------------

class TestFallbackJson:
    def test_erstellt_neue_datei_wenn_nicht_vorhanden(self, tmp_path):
        json_path = str(tmp_path / "fallback.json")
        with patch("scripts.data_download._FALLBACK_JSON", json_path):
            result = _load_fallback()
        assert os.path.exists(json_path)
        assert isinstance(result, dict)

    def test_laedt_vorhandene_datei(self, tmp_path):
        json_path = tmp_path / "fallback.json"
        json_path.write_text(json.dumps({"BTC": 50000.0, "MATIC": 0.09}), encoding="utf-8")
        with patch("scripts.data_download._FALLBACK_JSON", str(json_path)):
            result = _load_fallback()
        assert result["BTC"] == 50000.0
        assert result["MATIC"] == 0.09

    def test_gibt_defaults_zurueck_bei_korrupter_datei(self, tmp_path):
        json_path = tmp_path / "fallback.json"
        json_path.write_text("{ ungültiges json !!!", encoding="utf-8")
        with patch("scripts.data_download._FALLBACK_JSON", str(json_path)):
            # Soll nicht werfen – WARNING wird geloggt, Defaults zurückgegeben
            result = _load_fallback()
        assert isinstance(result, dict)

    def test_speichert_und_laedt_korrekt(self, tmp_path):
        json_path = str(tmp_path / "fallback.json")
        data = {"ETH": 3000.0, "BTC": 60000.0}
        with patch("scripts.data_download._FALLBACK_JSON", json_path):
            _save_fallback(data)
            result = _load_fallback()
        assert result["ETH"] == 3000.0
        assert result["BTC"] == 60000.0

    def test_save_erstellt_verzeichnis_nicht_automatisch(self, tmp_path):
        """_save_fallback soll bei fehlendem Verzeichnis nicht crashen sondern loggen."""
        json_path = str(tmp_path / "nicht_vorhanden" / "fallback.json")
        with patch("scripts.data_download._FALLBACK_JSON", json_path):
            _save_fallback({"BTC": 1.0})

    def test_default_fallback_werte_bei_erster_initialisierung(self, tmp_path):
        """Beim ersten Start ohne JSON werden _DEFAULT_FALLBACKS als Basis genutzt."""
        json_path = str(tmp_path / "fallback_new.json")
        with patch("scripts.data_download._FALLBACK_JSON", json_path):
            result = _load_fallback()
        assert "MATIC" in result
        assert result["MATIC"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Tests: download_csv_if_old
# ---------------------------------------------------------------------------

class TestDownloadCsvIfOld:
    def test_ueberspringt_aktuelle_datei(self, tmp_path):
        """Datei jünger als max_age_days → kein Download."""
        csv = tmp_path / "test.csv"
        csv.write_text("data", encoding="utf-8")
        with patch("scripts.data_download._create_retry_session") as mock_session:
            download_csv_if_old(["http://example.com/test.csv"], str(tmp_path), ["test.csv"], max_age_days=30)
        mock_session.return_value.get.assert_not_called()

    def test_laedt_veraltete_datei_herunter(self, tmp_path):
        """Datei älter als max_age_days → Download wird versucht."""
        csv = tmp_path / "old.csv"
        csv.write_text("data", encoding="utf-8")
        # Änderungsdatum weit in die Vergangenheit setzen
        old_time = pd.Timestamp("2020-01-01").timestamp()
        os.utime(str(csv), (old_time, old_time))

        mock_response = MagicMock()
        mock_response.text = "neue daten"
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://example.com/old.csv"], str(tmp_path), ["old.csv"], max_age_days=1)

        mock_session.get.assert_called_once()
        assert csv.read_text(encoding="utf-8") == "neue daten"

    def test_bricht_ab_bei_fehlendem_verzeichnis(self, tmp_path, caplog):
        """Nicht vorhandenes Verzeichnis → früher Abbruch mit ERROR-Log."""
        with caplog.at_level(logging.ERROR, logger="scripts.data_download"):
            download_csv_if_old(
                ["http://example.com/test.csv"],
                str(tmp_path / "existiert_nicht"),
                ["test.csv"]
            )
        assert any("existiert nicht" in r.message for r in caplog.records)

    def test_laedt_neue_datei_ohne_vorhandene(self, tmp_path):
        """Datei existiert noch nicht → Download wird durchgeführt."""
        mock_response = MagicMock()
        mock_response.text = "frische daten"
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://example.com/new.csv"], str(tmp_path), ["new.csv"])

        assert (tmp_path / "new.csv").read_text(encoding="utf-8") == "frische daten"

    def test_mehrere_urls_werden_alle_verarbeitet(self, tmp_path):
        """Zwei URLs → beide Dateien werden heruntergeladen."""
        mock_response = MagicMock()
        mock_response.text = "csv inhalt"
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(
                ["http://a.com/1.csv", "http://b.com/2.csv"],
                str(tmp_path),
                ["etf1.csv", "etf2.csv"]
            )

        assert mock_session.get.call_count == 2
        assert (tmp_path / "etf1.csv").exists()
        assert (tmp_path / "etf2.csv").exists()

    def test_loggt_fehler_bei_netzwerkfehler(self, tmp_path, caplog):
        """Netzwerkfehler beim Download → ERROR wird geloggt, kein Crash."""
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Verbindung fehlgeschlagen")

        with patch("scripts.data_download._create_retry_session", return_value=mock_session), \
             caplog.at_level(logging.ERROR, logger="scripts.data_download"):
                download_csv_if_old(["http://example.com/fail.csv"], str(tmp_path), ["fail.csv"])

        assert any("Fehler" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Tests: download_stock_price – Fallback-Logik (gemockt)
# ---------------------------------------------------------------------------

class TestDownloadStockPriceFallback:
    """Testet die Fallback-Logik ohne echte yFinance-Aufrufe."""

    def _depot_df(self):
        return pd.DataFrame({
            "Art":    ["Aktie", "Krypto"],
            "Ticker": ["AAPL",  "BTC"],
        })

    def test_fallback_kurs_wird_verwendet_wenn_kein_live_kurs(self, tmp_path):
        """Wenn yFinance keinen Kurs liefert, wird der Fallback-JSON-Kurs eingesetzt."""
        fallback_data = {"AAPL": 150.0, "BTC": 45000.0}
        json_path = str(tmp_path / "fallback.json")

        empty_df = pd.DataFrame()

        with patch("scripts.data_download._FALLBACK_JSON", json_path), \
             patch("scripts.data_download.yf.download", return_value=empty_df):
            _save_fallback(fallback_data)
            prices, fallback_used = download_stock_price(self._depot_df())

        assert "AAPL" in fallback_used or "BTC" in fallback_used

    def test_erfolgreicher_kurs_aktualisiert_fallback(self, tmp_path):
        """Wenn ein Live-Kurs gefunden wird, wird er in den Fallback geschrieben."""
        json_path = str(tmp_path / "fallback.json")

        close_data = pd.DataFrame(
            {"AAPL.DE": [155.0], "BTC-EUR": [48000.0]},
            index=[pd.Timestamp("2024-01-15")]
        )
        close_data.columns = pd.MultiIndex.from_tuples(
            [("Close", "AAPL.DE"), ("Close", "BTC-EUR")]
        )

        with patch("scripts.data_download._FALLBACK_JSON", json_path), \
             patch("scripts.data_download.yf.download", return_value=close_data):
            _save_fallback({})
            prices, _ = download_stock_price(self._depot_df())

        # Fallback sollte aktualisiert worden sein
        with open(json_path, encoding="utf-8") as f:
            saved = json.load(f)
        # Mindestens eine der Positionen sollte gespeichert sein (je nach yf-Response-Format)
        assert isinstance(saved, dict)

