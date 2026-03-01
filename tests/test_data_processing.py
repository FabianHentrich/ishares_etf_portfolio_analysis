# tests/test_data_processing.py
"""
Unit Tests für scripts/data_processing.py

Getestet werden:
- _normalize_str: Unicode-Bereinigung und Encoding-Artefakte
- clean_etf_data: Filterung, Mapping, Sonstige-Fallback
- calculate_relative_weighting: Gewichtungsberechnung, Edge Cases
"""

import numpy as np
import pandas as pd
import pytest

from scripts.data_processing import (
    LOCATION_MAPPING,
    SECTOR_MAPPING,
    _normalize_str,
    calculate_relative_weighting,
    clean_etf_data,
)

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_etf_df(**overrides):
    """Erstellt ein minimales gültiges ETF-DataFrame für Tests."""
    data = {
        "ETF":          ["Test ETF", "Test ETF"],
        "Name":         ["Apple Inc.", "Microsoft Corp."],
        "Gewichtung (%)": [5.0, 3.0],
        "Sektor":       ["Information Technology", "Information Technology"],
        "Standort":     ["United States", "United States"],
        "Anlageklasse": ["Aktien", "Aktien"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def _make_depot_df(**overrides):
    """Erstellt ein minimales gültiges Depot-DataFrame für Tests."""
    data = {
        "Art":          ["ETF", "Aktie", "Cash"],
        "Position":     ["Test ETF", "Apple Inc.", "Cash"],
        "Ticker":       ["TST", "AAPL", "-"],
        "Anteile":      [100.0, 10.0, 1000.0],
        "Marktwert (%)": [50.0, 30.0, 20.0],
    }
    data.update(overrides)
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Tests: _normalize_str
# ---------------------------------------------------------------------------

class TestNormalizeStr:
    def test_entfernt_non_breaking_space(self):
        # \xa0 wird entfernt (kein Leerzeichen, kein Zeicheninhalt)
        result = _normalize_str("Hallo\xa0Welt")
        assert "\xa0" not in result

    def test_entfernt_zero_width_space(self):
        result = _normalize_str("Test\u200bWert")
        assert "\u200b" not in result

    def test_nfc_normalisierung(self):
        nfd = "a\u0301"  # NFD: 'a' + combining acute accent
        assert _normalize_str(nfd) == "á"

    def test_gibt_nichtstring_unveraendert_zurueck(self):
        assert _normalize_str(42) == 42
        assert _normalize_str(None) is None
        assert _normalize_str(3.14) == 3.14

    def test_leerer_string_bleibt_leer(self):
        assert _normalize_str("") == ""

    def test_whitespace_wird_getrimmt(self):
        assert _normalize_str("  Hallo  ") == "Hallo"

    def test_normaler_string_unveraendert(self):
        assert _normalize_str("Apple Inc.") == "Apple Inc."


class TestCleanEtfData:
    def test_nullzeilen_name_werden_entfernt(self):
        df = _make_etf_df(
            Name=["Apple", None],
            **{"Gewichtung (%)": [5.0, 3.0]}
        )
        result = clean_etf_data(df)
        assert result["Name"].notna().all()
        assert len(result) == 1

    def test_nullzeilen_gewichtung_werden_entfernt(self):
        df = _make_etf_df(**{"Gewichtung (%)": [5.0, None]})
        result = clean_etf_data(df)
        assert result["Gewichtung (%)"].notna().all()

    def test_nullgewichtung_wird_entfernt(self):
        df = _make_etf_df(**{"Gewichtung (%)": [0.0, 3.0]})
        result = clean_etf_data(df)
        assert (result["Gewichtung (%)"] > 0).all()

    def test_sektor_mapping_englisch_zu_deutsch(self):
        df = _make_etf_df(Sektor=["Information Technology", "Health Care"])
        result = clean_etf_data(df)
        assert set(result["Sektor"].unique()) <= {"Technologie", "Gesundheit"}

    def test_sektor_mapping_encoding_variante(self):
        df = _make_etf_df(
            Sektor=["Zyklische Konsumgter", "Zyklische Konsumgter"],
            **{"Gewichtung (%)": [2.0, 1.0]}
        )
        result = clean_etf_data(df)
        assert "Zyklischer Konsum" in result["Sektor"].values

    def test_alle_deutschen_sektornamen_bleiben_unveraendert(self):
        """Deutsche Sektornamen die bereits korrekt sind sollen nicht verändert werden."""
        bekannte = ["Technologie", "Finanzen", "Gesundheit", "Industrie",
                    "Immobilien", "Energie", "Rohstoffe", "Versorger"]
        rows = len(bekannte)
        df = pd.DataFrame({
            "ETF":            ["Test ETF"] * rows,
            "Name":           [f"Firma {i}" for i in range(rows)],
            "Gewichtung (%)": [1.0] * rows,
            "Sektor":         bekannte,
            "Standort":       ["United States"] * rows,
            "Anlageklasse":   ["Aktien"] * rows,
        })
        result = clean_etf_data(df)
        for sektor in bekannte:
            assert sektor in result["Sektor"].values, f"Sektor '{sektor}' fehlt nach clean_etf_data"

    def test_standort_mapping_usa(self):
        df = _make_etf_df(Standort=["United States", "United States"])
        result = clean_etf_data(df)
        assert (result["Standort"] == "USA").all()

    def test_standort_mapping_grossbritannien_encoding(self):
        df = _make_etf_df(Standort=["Grobritannien", "United States"])
        result = clean_etf_data(df)
        assert "Großbritannien" in result["Standort"].values

    def test_cash_derivate_werden_nach_anlageklasse_gefiltert(self):
        df = _make_etf_df(
            Sektor=["Cash und/oder Derivate", "Information Technology"],
            Anlageklasse=["Cash", "Aktien"],
        )
        result = clean_etf_data(df)
        assert "Cash und/oder Derivate" not in result["Sektor"].values

    def test_ohne_anlageklasse_spalte_kein_crash(self):
        """clean_etf_data soll auch ohne Anlageklasse-Spalte laufen."""
        df = _make_etf_df()
        df = df.drop(columns=["Anlageklasse"])
        result = clean_etf_data(df)
        assert not result.empty

    def test_unbekannte_sektoren_werden_sonstige(self):
        unresolved_keys = set(SECTOR_MAPPING.keys()) - set(SECTOR_MAPPING.values())
        if not unresolved_keys:
            pytest.skip("Kein unresolved Key im SECTOR_MAPPING vorhanden")
        key = next(iter(unresolved_keys))
        df = _make_etf_df(Sektor=[key, "Information Technology"])
        result = clean_etf_data(df)
        assert key not in result["Sektor"].values

    def test_gewichtung_komma_als_dezimaltrenner(self):
        df = _make_etf_df(**{"Gewichtung (%)": ["5,25", "3,10"]})
        result = clean_etf_data(df)
        assert result["Gewichtung (%)"].dtype in [np.float64, float]
        assert abs(result["Gewichtung (%)"].iloc[0] - 5.25) < 0.001

    def test_gewichtung_nan_string_wird_entfernt(self):
        """'nan' als String in Gewichtung soll nicht zu echten Daten führen."""
        df = _make_etf_df(**{"Gewichtung (%)": ["nan", "3,10"]})
        result = clean_etf_data(df)
        assert len(result) == 1

    def test_leeres_dataframe_gibt_leeres_dataframe_zurueck(self):
        df = pd.DataFrame(columns=["ETF", "Name", "Gewichtung (%)", "Sektor", "Standort", "Anlageklasse"])
        result = clean_etf_data(df)
        assert result.empty

    def test_etf_name_wird_aus_pfad_extrahiert(self):
        df = _make_etf_df()
        df["ETF"] = "/pfad/zu/iShares Test ETF.csv"
        result = clean_etf_data(df)
        assert (result["ETF"] == "iShares Test ETF").all()

    def test_mehrere_etf_quellen_werden_korrekt_verarbeitet(self):
        """concat aus zwei ETF-DataFrames → beide ETF-Namen bleiben erhalten."""
        df1 = _make_etf_df()
        df1["ETF"] = "ETF A"
        df2 = _make_etf_df()
        df2["ETF"] = "ETF B"
        combined = pd.concat([df1, df2], ignore_index=True)
        result = clean_etf_data(combined)
        assert set(result["ETF"].unique()) == {"ETF A", "ETF B"}


# ---------------------------------------------------------------------------
# Tests: calculate_relative_weighting
# ---------------------------------------------------------------------------

class TestCalculateRelativeWeighting:
    def test_grundlegende_gewichtungsberechnung(self):
        """ETF mit 50% Depotgewicht: Position mit 10% ETF-Gewichtung → 5% relativ."""
        etf_df = pd.DataFrame({
            "ETF":           ["Test ETF", "Test ETF"],
            "Name":          ["Apple", "Microsoft"],
            "Gewichtung (%)": [10.0, 6.0],
        })
        depot_df = pd.DataFrame({
            "Art":           ["ETF"],
            "Position":      ["Test ETF"],
            "Marktwert (%)": [50.0],
        })
        result, msg = calculate_relative_weighting(etf_df, depot_df)
        assert abs(result.loc[result["Name"] == "Apple", "relative Gewichtung (%)"].values[0] - 5.0) < 0.001
        assert abs(result.loc[result["Name"] == "Microsoft", "relative Gewichtung (%)"].values[0] - 3.0) < 0.001

    def test_ergebnis_message_enthaelt_etf_anteil(self):
        etf_df = pd.DataFrame({
            "ETF": ["Test ETF"], "Name": ["Apple"], "Gewichtung (%)": [100.0]
        })
        depot_df = pd.DataFrame({
            "Art": ["ETF"], "Position": ["Test ETF"], "Marktwert (%)": [40.0]
        })
        _, msg = calculate_relative_weighting(etf_df, depot_df)
        assert "40" in msg

    def test_etf_nicht_in_csv_wird_uebersprungen(self):
        """ETF im Depot aber nicht in ETF-CSV → kein Fehler, nur WARNING."""
        etf_df = pd.DataFrame({
            "ETF": ["Anderer ETF"], "Name": ["Apple"], "Gewichtung (%)": [10.0]
        })
        depot_df = pd.DataFrame({
            "Art": ["ETF"], "Position": ["Test ETF"], "Marktwert (%)": [50.0]
        })
        # Soll nicht werfen
        result, msg = calculate_relative_weighting(etf_df, depot_df)
        assert result is not None

    def test_fehlende_marktwert_spalte_wirft_fehler(self):
        etf_df = pd.DataFrame({"ETF": ["A"], "Name": ["B"], "Gewichtung (%)": [1.0]})
        depot_df = pd.DataFrame({"Art": ["ETF"], "Position": ["A"]})  # kein Marktwert (%)
        with pytest.raises(KeyError):
            calculate_relative_weighting(etf_df, depot_df)

    def test_leeres_etf_dataframe_wirft_fehler(self):
        etf_df = pd.DataFrame(columns=["ETF", "Name", "Gewichtung (%)"])
        depot_df = _make_depot_df()
        with pytest.raises(ValueError, match="etf_stocks"):
            calculate_relative_weighting(etf_df, depot_df)

    def test_leeres_depot_dataframe_wirft_fehler(self):
        etf_df = _make_etf_df()
        depot_df = pd.DataFrame(columns=["Art", "Position", "Marktwert (%)"])
        with pytest.raises(ValueError, match="depot_components"):
            calculate_relative_weighting(etf_df, depot_df)

    def test_etf_gewicht_null_ergibt_null_gewichtung(self):
        """ETF mit Marktwert 0% → alle Positionen bekommen relative Gewichtung 0."""
        etf_df = pd.DataFrame({
            "ETF": ["Test ETF"], "Name": ["Apple"], "Gewichtung (%)": [10.0]
        })
        depot_df = pd.DataFrame({
            "Art": ["ETF"], "Position": ["Test ETF"], "Marktwert (%)": [0.0]
        })
        result, _ = calculate_relative_weighting(etf_df, depot_df)
        assert result["relative Gewichtung (%)"].sum() == 0.0

    def test_mehrere_etfs_werden_unabhaengig_berechnet(self):
        """Zwei ETFs mit verschiedenen Depotgewichten werden korrekt getrennt berechnet."""
        etf_df = pd.DataFrame({
            "ETF":            ["ETF A", "ETF A", "ETF B"],
            "Name":           ["Apple", "Microsoft", "Google"],
            "Gewichtung (%)": [20.0, 10.0, 50.0],
        })
        depot_df = pd.DataFrame({
            "Art":           ["ETF", "ETF"],
            "Position":      ["ETF A", "ETF B"],
            "Marktwert (%)": [40.0, 20.0],
        })
        result, _ = calculate_relative_weighting(etf_df, depot_df)
        apple_weight = result.loc[result["Name"] == "Apple", "relative Gewichtung (%)"].values[0]
        google_weight = result.loc[result["Name"] == "Google", "relative Gewichtung (%)"].values[0]
        assert abs(apple_weight - 8.0) < 0.001    # 20% * 40% = 8%
        assert abs(google_weight - 10.0) < 0.001  # 50% * 20% = 10%


# ---------------------------------------------------------------------------
# Tests: SECTOR_MAPPING & LOCATION_MAPPING Konsistenz
# ---------------------------------------------------------------------------

class TestMappingKonsistenz:
    def test_sector_mapping_hat_keine_leeren_werte(self):
        for k, v in SECTOR_MAPPING.items():
            assert v, f"SECTOR_MAPPING['{k}'] ist leer"

    def test_location_mapping_hat_keine_leeren_werte(self):
        for k, v in LOCATION_MAPPING.items():
            assert v, f"LOCATION_MAPPING['{k}'] ist leer"

    def test_sector_mapping_werte_sind_strings(self):
        for k, v in SECTOR_MAPPING.items():
            assert isinstance(v, str), f"SECTOR_MAPPING['{k}'] = {v!r} ist kein String"

    def test_location_mapping_werte_sind_strings(self):
        for k, v in LOCATION_MAPPING.items():
            assert isinstance(v, str), f"LOCATION_MAPPING['{k}'] = {v!r} ist kein String"

    def test_keine_leerzeichen_in_mapping_werten(self):
        for _k, v in {**SECTOR_MAPPING, **LOCATION_MAPPING}.items():
            assert v == v.strip(), f"Führende/nachfolgende Leerzeichen in Mapping-Wert '{v}'"

