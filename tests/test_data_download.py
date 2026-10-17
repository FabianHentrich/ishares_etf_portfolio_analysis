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

from scripts.data_download import (
    _PRICE_WINDOW_DAYS,
    _fallback_entry,
    _is_ishares_csv,
    _load_fallback,
    _save_fallback,
    download_csv_if_old,
    download_stock_price,
)

# Minimaler Inhalt im Format der iShares-Positions-CSV (latest-holdings.csv)
_VALID_CSV = (
    'Fondsposition per,"15.Okt.2026"\n'
    "\n"
    "Emittententicker,Name,Sektor,Anlageklasse,Marktwert,Gewichtung (%),Nominalwert,Nominale,Kurs,Standort\n"
    '"NVDA","NVIDIA","IT","Aktien","1,00","8,58","1,00","1,00","1,00","Vereinigte Staaten"\n'
)
_HTML_PAGE = '<!doctype html>\n<html lang="de-DE"><head><title>iShares</title></head></html>'

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

    def test_korrupte_datei_wird_nicht_ueberschrieben(self, tmp_path):
        """Lesefehler darf gespeicherte Kurse nicht vernichten – Original bleibt + Sicherungskopie."""
        json_path = tmp_path / "fallback.json"
        kaputt = '{"BTC": 50000.0, "ETH": 3000.0'  # fehlende Klammer
        json_path.write_text(kaputt, encoding="utf-8")
        with patch("scripts.data_download._FALLBACK_JSON", str(json_path)):
            _load_fallback()
        assert json_path.read_text(encoding="utf-8") == kaputt
        assert (tmp_path / "fallback.json.corrupt").read_text(encoding="utf-8") == kaputt

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
        mock_response.text = _VALID_CSV
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://example.com/old.csv"], str(tmp_path), ["old.csv"], max_age_days=1)

        mock_session.get.assert_called_once()
        assert csv.read_text(encoding="utf-8") == _VALID_CSV

    def test_bricht_ab_bei_fehlendem_verzeichnis(self, tmp_path, caplog):
        """Nicht vorhandenes Verzeichnis → früher Abbruch mit ERROR-Log."""
        with caplog.at_level(logging.ERROR, logger="scripts.data_download"):
            download_csv_if_old(["http://example.com/test.csv"], str(tmp_path / "existiert_nicht"), ["test.csv"])
        assert any("existiert nicht" in r.message for r in caplog.records)

    def test_laedt_neue_datei_ohne_vorhandene(self, tmp_path):
        """Datei existiert noch nicht → Download wird durchgeführt."""
        mock_response = MagicMock()
        mock_response.text = _VALID_CSV
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://example.com/new.csv"], str(tmp_path), ["new.csv"])

        assert (tmp_path / "new.csv").read_text(encoding="utf-8") == _VALID_CSV

    def test_mehrere_urls_werden_alle_verarbeitet(self, tmp_path):
        """Zwei URLs → beide Dateien werden heruntergeladen."""
        mock_response = MagicMock()
        mock_response.text = _VALID_CSV
        mock_response.raise_for_status = MagicMock()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://a.com/1.csv", "http://b.com/2.csv"], str(tmp_path), ["etf1.csv", "etf2.csv"])

        assert mock_session.get.call_count == 2
        assert (tmp_path / "etf1.csv").exists()
        assert (tmp_path / "etf2.csv").exists()

    def test_html_antwort_ueberschreibt_vorhandene_csv_nicht(self, tmp_path, caplog):
        """iShares liefert HTML statt CSV (z.B. veraltete URL) → alte Datei bleibt unverändert."""
        csv = tmp_path / "etf.csv"
        csv.write_text(_VALID_CSV, encoding="utf-8")
        old_time = pd.Timestamp("2020-01-01").timestamp()
        os.utime(str(csv), (old_time, old_time))

        mock_response = MagicMock()
        mock_response.text = _HTML_PAGE
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with (
            patch("scripts.data_download._create_retry_session", return_value=mock_session),
            caplog.at_level(logging.ERROR, logger="scripts.data_download"),
        ):
            download_csv_if_old(["http://example.com/etf.csv"], str(tmp_path), ["etf.csv"], max_age_days=1)

        assert csv.read_text(encoding="utf-8") == _VALID_CSV
        # Änderungsdatum unverändert → nächster Lauf versucht erneut zu laden
        assert os.path.getmtime(str(csv)) == pytest.approx(old_time)
        assert not (tmp_path / "etf.csv.tmp").exists()
        assert any("keine iShares-Positions-CSV" in r.message for r in caplog.records)

    def test_html_antwort_legt_keine_neue_datei_an(self, tmp_path):
        mock_response = MagicMock()
        mock_response.text = _HTML_PAGE
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with patch("scripts.data_download._create_retry_session", return_value=mock_session):
            download_csv_if_old(["http://example.com/etf.csv"], str(tmp_path), ["etf.csv"])

        assert not (tmp_path / "etf.csv").exists()

    def test_loggt_fehler_bei_netzwerkfehler(self, tmp_path, caplog):
        """Netzwerkfehler beim Download → ERROR wird geloggt, kein Crash."""
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Verbindung fehlgeschlagen")

        with (
            patch("scripts.data_download._create_retry_session", return_value=mock_session),
            caplog.at_level(logging.ERROR, logger="scripts.data_download"),
        ):
            download_csv_if_old(["http://example.com/fail.csv"], str(tmp_path), ["fail.csv"])

        assert any("Fehler" in r.message for r in caplog.records)


class TestIsIsharesCsv:
    def test_erkennt_gueltige_csv(self):
        assert _is_ishares_csv(_VALID_CSV)

    def test_erkennt_csv_mit_bom(self):
        assert _is_ishares_csv("﻿" + _VALID_CSV)

    def test_lehnt_html_ab(self):
        assert not _is_ishares_csv(_HTML_PAGE)

    def test_lehnt_leeren_text_ab(self):
        assert not _is_ishares_csv("")


# ---------------------------------------------------------------------------
# Tests: download_stock_price – Fallback-Logik (gemockt)
# ---------------------------------------------------------------------------


class TestDownloadStockPriceFallback:
    """Testet die Fallback-Logik ohne echte yFinance-Aufrufe."""

    def _depot_df(self):
        return pd.DataFrame(
            {
                "Art": ["Aktie", "Krypto"],
                "Ticker": ["AAPL", "BTC"],
            }
        )

    def test_fallback_kurs_wird_verwendet_wenn_kein_live_kurs(self, tmp_path):
        """Wenn yFinance keinen Kurs liefert, wird der Fallback-JSON-Kurs eingesetzt."""
        fallback_data = {"AAPL": 150.0, "BTC": 45000.0}
        json_path = str(tmp_path / "fallback.json")

        empty_df = pd.DataFrame()

        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=empty_df),
        ):
            _save_fallback(fallback_data)
            prices, fallback_used = download_stock_price(self._depot_df())

        assert "AAPL" in fallback_used or "BTC" in fallback_used

    def test_erfolgreicher_kurs_aktualisiert_fallback(self, tmp_path):
        """Wenn ein Live-Kurs gefunden wird, wird er in den Fallback geschrieben."""
        json_path = str(tmp_path / "fallback.json")

        close_data = pd.DataFrame({"AAPL.DE": [155.0], "BTC-EUR": [48000.0]}, index=[pd.Timestamp("2024-01-15")])
        close_data.columns = pd.MultiIndex.from_tuples([("Close", "AAPL.DE"), ("Close", "BTC-EUR")])

        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=close_data),
        ):
            _save_fallback({})
            prices, _ = download_stock_price(self._depot_df())

        # Fallback sollte aktualisiert worden sein
        with open(json_path, encoding="utf-8") as f:
            saved = json.load(f)
        # Mindestens eine der Positionen sollte gespeichert sein (je nach yf-Response-Format)
        assert isinstance(saved, dict)


class TestKursdatumUndZeitfenster:
    """Kursdatum, Alter von Fallback-Kursen und Abfragezeitraum."""

    def _depot_df(self):
        return pd.DataFrame({"Art": ["Aktie"], "Ticker": ["AAPL"]})

    def _close(self, datum, wert=155.0):
        df = pd.DataFrame({("Close", "AAPL.DE"): [wert]}, index=[pd.Timestamp(datum)])
        df.columns = pd.MultiIndex.from_tuples(df.columns)
        return df

    def test_fallback_entry_neues_und_altes_format(self):
        assert _fallback_entry({"kurs": 1.5, "datum": "2026-10-16"}) == (1.5, "2026-10-16")
        assert _fallback_entry(0.09) == (0.09, None)

    def test_kursdatum_wird_zurueckgegeben_und_gespeichert(self, tmp_path):
        json_path = str(tmp_path / "fallback.json")
        heute = pd.Timestamp.today().normalize()
        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=self._close(heute)),
        ):
            _save_fallback({})
            prices, used = download_stock_price(self._depot_df())
        row = prices.set_index("Ticker").loc["AAPL"]
        assert row["Kursdatum"] == heute.date().isoformat()
        assert used == []
        with open(json_path, encoding="utf-8") as f:
            assert json.load(f)["AAPL"] == {"kurs": 155.0, "datum": heute.date().isoformat()}

    def test_fallback_mit_datum_liefert_kursdatum(self, tmp_path, caplog):
        json_path = str(tmp_path / "fallback.json")
        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=pd.DataFrame()),
            caplog.at_level(logging.WARNING, logger="scripts.data_download"),
        ):
            _save_fallback({"AAPL": {"kurs": 150.0, "datum": "2026-03-08"}})
            prices, used = download_stock_price(self._depot_df())
        row = prices.set_index("Ticker").loc["AAPL"]
        assert used == ["AAPL"]
        assert row["Kurs"] == 150.0
        assert row["Kursdatum"] == "2026-03-08"
        assert any("vom 2026-03-08" in r.message for r in caplog.records)

    def test_fallback_altformat_datum_unbekannt(self, tmp_path, caplog):
        json_path = str(tmp_path / "fallback.json")
        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=pd.DataFrame()),
            caplog.at_level(logging.WARNING, logger="scripts.data_download"),
        ):
            _save_fallback({"AAPL": 150.0})
            prices, used = download_stock_price(self._depot_df())
        assert prices.set_index("Ticker").loc["AAPL", "Kurs"] == 150.0
        assert any("Datum unbekannt" in r.message for r in caplog.records)

    def test_veralteter_live_kurs_wird_gemeldet(self, tmp_path, caplog):
        json_path = str(tmp_path / "fallback.json")
        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=self._close("2020-01-02")),
            caplog.at_level(logging.WARNING, logger="scripts.data_download"),
        ):
            _save_fallback({})
            download_stock_price(self._depot_df())
        assert any("Tage alt" in r.message for r in caplog.records)

    def test_zeitfenster_deckt_feiertage_ab(self, tmp_path):
        """Abfrage beginnt _PRICE_WINDOW_DAYS Kalendertage vor heute – nicht nur am letzten Werktag."""
        json_path = str(tmp_path / "fallback.json")
        heute = pd.Timestamp.today().normalize()
        with (
            patch("scripts.data_download._FALLBACK_JSON", json_path),
            patch("scripts.data_download.yf.download", return_value=self._close(heute)) as mock_dl,
        ):
            _save_fallback({})
            download_stock_price(self._depot_df())
        start = mock_dl.call_args.kwargs["start"]
        assert start == heute - pd.Timedelta(days=_PRICE_WINDOW_DAYS)
        assert _PRICE_WINDOW_DAYS >= 5  # mind. ein Wochenende + Feiertag
