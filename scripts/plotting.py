# plotting.py

import json
import logging
import webbrowser
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _de(val, decimals=2, unit=""):
    """Formatiert Zahlen im deutschen Format (Punkt = Tausender, Komma = Dezimal)."""
    if not isinstance(val, (int, float)) or pd.isna(val):
        return "–"
    formatted = f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted}{(' ' + unit) if unit else ''}"


def _eur(val):
    """Formatiert Euro-Beträge im deutschen Format: 1.234,56 €"""
    return _de(val, 2, "€")


def _pct(val, decimals=1):
    """Formatiert Prozentwerte – bei sehr kleinen Werten mehr Nachkommastellen."""
    if not isinstance(val, (int, float)) or pd.isna(val):
        return "–"
    if abs(val) < 0.1:
        return _de(val, 2, "%")
    return _de(val, decimals, "%")


# ---------------------------------------------------------------------------
# Figure-Builder – erstellen nur die Plotly-Figure, kein I/O
# ---------------------------------------------------------------------------


def build_depot_table(depot_df):
    """
    Erstellt eine sortierbare HTML-Tabelle der Depotpositionen.
    Erwartet Spalten: Ticker, Art, Position, Sektor, Standort, Anteile, Kurs, Marktwert, Marktwert (%)
    Gibt reines HTML zurück (kein Plotly-Figure-Objekt).
    """
    display_cols = {
        "Ticker": "Ticker",
        "Art": "Art",
        "Position": "Position",
        "Sektor": "Sektor",
        "Standort": "Standort",
        "Anteile": "Anteile",
        "Kurs": "Kurs (€)",
        "Marktwert": "Marktwert (€)",
        "Marktwert (%)": "Anteil (%)",
    }
    # Numerische Spalten – für korrekte Sortierung als Zahl behandeln
    numeric_cols = {"Anteile", "Kurs (€)", "Marktwert (€)", "Anteil (%)"}
    # Sensible Spalten – werden im Datenschutz-Modus ausgeblendet
    private_cols = {"Anteile", "Kurs (€)", "Marktwert (€)"}

    df = depot_df[[c for c in display_cols if c in depot_df.columns]].copy()
    df = df.rename(columns=display_cols)
    df = df.sort_values("Anteil (%)", ascending=False)

    # Roh-Zahlenwerte als data-sort-Attribut speichern, dann erst formatieren
    raw_values = {}
    for col in numeric_cols:
        if col in df.columns:
            raw_values[col] = df[col].tolist()

    # Formatierung der Anzeige – deutsches Zahlenformat
    for col in ["Kurs (€)", "Marktwert (€)"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: _de(x, 2) if pd.notna(x) else "–")
    if "Anteile" in df.columns:
        df["Anteile"] = df["Anteile"].apply(lambda x: _de(x, 4) if pd.notna(x) else "–")
    if "Anteil (%)" in df.columns:
        df["Anteil (%)"] = df["Anteil (%)"].apply(
            lambda x: (_de(x, 4, "%") if abs(x) < 0.1 else _de(x, 2, "%")) if pd.notna(x) else "–"
        )

    # Header mit Sortier-Pfeilen
    cols = list(df.columns)
    header_cells = ""
    for i, col in enumerate(cols):
        dtype = "num" if col in numeric_cols else "str"
        header_cells += (
            f'<th data-col="{i}" data-type="{dtype}" class="sortable">{col} <span class="sort-icon">↕</span></th>'
        )

    # Zeilen mit data-sort-Attributen für numerische Zellen – vektorisiert statt iterrows()
    cols = list(df.columns)
    td_parts = []
    for col in cols:
        is_priv  = col in private_cols
        priv_cls = ' class="private"' if is_priv else ''
        if col in numeric_cols and col in raw_values:
            raws = raw_values[col]
            vals = df[col].tolist()
            td_parts.append(
                [f'<td data-sort="{r if pd.notna(r) else -1e18}"{priv_cls}>{v}</td>'
                 for r, v in zip(raws, vals, strict=True)]
            )
        else:
            td_parts.append([f"<td{priv_cls}>{v}</td>" for v in df[col].tolist()])

    rows = ""
    for i in range(len(df)):
        cells = "".join(col_tds[i] for col_tds in td_parts)
        rows += f"<tr>{cells}</tr>"

    return f"""
    <div class="table-wrapper">
        <input class="table-search" type="text" placeholder="🔍 Tabelle filtern …" oninput="filterTable(this)" />
        <table class="depot-table" id="depot-table">
            <thead><tr>{header_cells}</tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def build_pie_chart(df, values, names, title):
    """Erstellt eine Pie-Chart-Figure.
    Zeigt den echten Depotwert in % als Beschriftung statt des relativen Chart-Anteils.
    """
    df = df.copy().dropna(subset=[values, names])
    df = df[df[values] > 0].reset_index(drop=True)

    fig = px.pie(df, values=values, names=names, title=title)
    fig.update_traces(
        customdata=df[values].apply(lambda v: _de(v, 2, "%")),
        texttemplate="%{label}<br>%{customdata}",
        textposition="inside",
        hovertemplate="<b>%{label}</b><br>Depotanteil: %{customdata}<extra></extra>",
    )
    fig.update_layout(
        showlegend=True, title_font_size=18, height=650, width=900, margin={"t": 60, "b": 20, "l": 20, "r": 20}
    )
    return fig


def build_bar_chart(df, x, y, title, top_n=20):
    """Erstellt eine horizontale Balken-Chart-Figure (Top-N).
    Passt den linken Margin dynamisch an die längste Y-Beschriftung an.
    """
    df_top = df.nlargest(top_n, x).copy()
    df_top["_label"] = df_top[x].apply(lambda v: _de(v, 2, "%"))

    max_label_len = df_top[y].astype(str).str.len().max() if not df_top.empty else 20
    left_margin = min(max(int(max_label_len * 7), 120), 400)

    fig = px.bar(df_top, x=x, y=y, orientation="h", title=title, text="_label", hover_data={x: ":.2f", "_label": False})
    fig.update_traces(
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Gewichtung: %{text}<extra></extra>",
    )
    fig.update_layout(
        yaxis={
            "categoryorder": "total ascending",
            "tickmode": "linear",
            "automargin": True,
            "tickfont": {"size": 12},
        },
        xaxis={"ticksuffix": " %"},
        margin={"l": left_margin, "r": 80, "t": 60, "b": 40},
        title_font_size=18,
        height=max(400, top_n * 28),
    )
    return fig


def build_treemap(df, path_cols, values, title):
    """Erstellt eine Treemap-Figure.

    Zeigt für jeden Knoten (Blatt und Eltern) den korrekten Depot-Anteil aus
    den Original-Daten – nicht Plotlys interne percentRoot/percentParent.
    """
    fig = px.treemap(df, path=path_cols, values=values, title=title, custom_data=[values])

    # Eltern-Knoten bekommen von px.treemap kein customdata – manuell befüllen.
    # fig.data[0].ids enthält alle Knoten-IDs (z.B. "Technologie", "Technologie/Apple").
    # fig.data[0].customdata hat für Eltern-Knoten NaN → mit Summe der Kinder ersetzen.
    trace = fig.data[0]
    ids = list(trace.ids)
    parents = list(trace.parents)
    customdata = list(trace.customdata)  # shape: (n, 1)

    # Summe je Eltern-Knoten aus Kinder-customdata aufbauen
    parent_sums: dict[str, float] = {}
    for i, _node_id in enumerate(parents):
        if _node_id == "":
            continue
        val = customdata[i][0] if customdata[i][0] == customdata[i][0] else 0.0
        parent_sums[_node_id] = parent_sums.get(_node_id, 0.0) + val

    # customdata der Eltern-Knoten setzen
    for i, node_id in enumerate(ids):
        if node_id in parent_sums and (
            customdata[i][0] != customdata[i][0]  # ist NaN
            or customdata[i][0] == 0.0
        ):
            customdata[i] = [parent_sums[node_id]]

    # Kategorie-Anteil: nur für Blatt-Knoten sinnvoll (Eltern-Knoten sind selbst Kategorien)
    # Blatt-Knoten = Knoten der NICHT in parent_sums vorkommt (hat keine Kinder)
    parent_val_map = {node_id: customdata[i][0] for i, node_id in enumerate(ids)}
    is_parent = set(parent_sums.keys())  # alle Knoten die mindestens ein Kind haben

    cd_cat = []
    for i, _node_id in enumerate(ids):
        pid = parents[i]
        node_val = customdata[i][0] if customdata[i][0] == customdata[i][0] else 0.0
        parent_val = parent_val_map.get(pid, 0.0) if pid else 0.0

        if _node_id not in is_parent and parent_val > 0:
            # Blatt-Knoten: Kategorie-Anteil berechnen, als formatierter String
            pct_str = f"{node_val / parent_val * 100:.2f} %"
        else:
            # Eltern/Root: kein Kategorie-Anteil anzeigen
            pct_str = "–"

        cd_cat.append([customdata[i][0], pct_str])

    trace.customdata = cd_cat

    fig.update_traces(
        texttemplate="%{label}<br>%{customdata[0]:.2f} %",
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Anteil Depot: %{customdata[0]:.2f} %<br>"
            "Anteil Kategorie: %{customdata[1]}"
            "<extra></extra>"
        ),
    )
    fig.update_layout(title_font_size=18, height=700, margin={"t": 60, "b": 10, "l": 10, "r": 10})
    return fig


def build_heatmap(pivot_df, title, colorscale="Blues"):
    """Erstellt eine annotierte Heatmap aus einem pivot-DataFrame.
    Zeigt z.B. Sektorgewichtung je ETF/Quelle.
    Zeilen = Sektoren, Spalten = ETF/Assetklasse.
    """
    z = pivot_df.values
    x = pivot_df.columns.tolist()
    y = pivot_df.index.tolist()

    # Annotationstext: deutsches Format mit %-Zeichen, leer bei 0
    text = [[(_de(v, 2, "%") if v > 0 else "") for v in row] for row in z]

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=x,
            y=y,
            text=text,
            texttemplate="%{text}",
            colorscale=colorscale,
            hoverongaps=False,
            hovertemplate="<b>%{y}</b> · %{x}<br>Gewichtung: %{text}<extra></extra>",
            showscale=True,
        )
    )
    fig.update_layout(
        title={"text": title, "font": {"size": 18}},
        xaxis={"tickangle": -30, "automargin": True},
        yaxis={"automargin": True},
        height=max(400, len(y) * 40 + 120),
        margin={"t": 80, "b": 60, "l": 160, "r": 40},
    )
    return fig


# ---------------------------------------------------------------------------
# HTML-Report-Export
# ---------------------------------------------------------------------------


def export_html_report(sections, output_file, depot_summary=None):
    """
    Erstellt einen vollständigen, selbst-enthaltenden HTML-Report mit allen Charts.

    :param sections: Liste von Dicts mit Schlüsseln:
                     - 'title': Abschnittstitel (str)
                     - 'fig':   Plotly-Figure
                     - 'description': optionaler Erläuterungstext (str)
    :param output_file: Pfad zur Ausgabe-HTML-Datei (str)
    :param depot_summary: optionaler dict mit Kennzahlen für den Kopfbereich,
                          z. B. {'Gesamtwert (€)': 12345.67, 'Positionen': 15}
    """
    now = datetime.now().strftime("%d.%m.%Y %H:%M Uhr")

    # Navigationsmenü-Einträge
    nav_items = "".join(f'<li><a href="#section-{i}">{s["title"]}</a></li>' for i, s in enumerate(sections))

    # Kennzahlen-Karten im Header – in drei Gruppen aufgeteilt
    summary_html = ""
    if depot_summary:
        # Gruppen: Depot-Übersicht | Assetklassen | Qualität & Warnungen
        group_keys = {
            "depot": ["Gesamtwert", "Positionen"],
            "assets": ["ETF-Anteil", "Aktien-Anteil", "Krypto-Anteil", "Cash-Anteil"],
            "quality": ["Diversifikation", "Top-5-Konzentration"],
        }
        # Alle Keys die keiner Gruppe zugeordnet sind (z.B. Fallback-Warnung) → extra
        assigned = {k for keys in group_keys.values() for k in keys}
        extra_keys = [k for k in depot_summary if k not in assigned]

        # Schlüssel deren Wert im Datenschutz-Modus ausgeblendet wird
        _private_keys = {"Gesamtwert"}

        def _card(k, v):
            is_warning = "⚠️" in str(k) or "⚠️" in str(v)
            cls      = "kpi-card kpi-warning" if is_warning else "kpi-card"
            val_cls  = "kpi-value private" if k in _private_keys else "kpi-value"
            return f'<div class="{cls}"><div class="{val_cls}">{v}</div><div class="kpi-label">{k}</div></div>'

        groups_html = ""
        for _gname, keys in group_keys.items():
            cards = "".join(_card(k, depot_summary[k]) for k in keys if k in depot_summary)
            if cards:
                groups_html += f'<div class="kpi-group">{cards}</div>'

        if extra_keys:
            cards = "".join(_card(k, depot_summary[k]) for k in extra_keys)
            groups_html += f'<div class="kpi-group kpi-group-wide">{cards}</div>'

        summary_html = f'<div class="kpi-row">{groups_html}</div>'

    sections_html = ""
    plotlyjs_tag = ""
    chart_payloads = []  # [(div_id, fig_json)]

    # Plotly.js einmalig inline einbetten (kein CDN, keine file://-Probleme)
    _plotlyjs_path = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    if _plotlyjs_path.exists():
        plotlyjs_tag = f"<script>{_plotlyjs_path.read_text(encoding='utf-8')}</script>"
        logger.debug(f"Plotly.js lokal eingebettet: {_plotlyjs_path}")
    else:
        plotlyjs_tag = '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
        logger.warning(
            f"Lokale plotly.min.js nicht gefunden ({_plotlyjs_path}) – "
            f"CDN-Fallback wird verwendet. Report benötigt Internetverbindung!"
        )

    for i, section in enumerate(sections):
        desc_html = f'<p class="section-desc">{section["description"]}</p>' if section.get("description") else ""

        if "fig" in section and section["fig"] is not None:
            div_id = f"plotly-chart-{i}"
            chart_payloads.append((div_id, section["fig"].to_json()))
            content_html = (
                f'<div id="{div_id}" class="plotly-lazy"><div class="chart-placeholder">⏳ Wird geladen…</div></div>'
            )

        elif "html" in section:
            content_html = section["html"]
        else:
            content_html = "<p><em>Kein Inhalt verfügbar.</em></p>"

        sections_html += (
            f'<section id="section-{i}" class="chart-section">'
            f"<h2>{section['title']}</h2>{desc_html}"
            f'<div class="chart-container">{content_html}</div>'
            f"</section>\n"
        )

    # Chart-JSON als type=application/json – Browser parst kein JS, blockiert keinen Paint
    chart_data_tags = "\n    ".join(
        f'<script type="application/json" id="data-{did}">{fjson}</script>' for did, fjson in chart_payloads
    )
    chart_div_ids = json.dumps([did for did, _ in chart_payloads])

    html = f"""<!DOCTYPE html>
<html lang="de" style="background:#f4f6f9;color:#333;">
<head>
    <meta name="color-scheme" content="light">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio-Analyse – {now}</title>
    <style>
        :root {{ color-scheme: light; }}
        html, body {{ background: #f4f6f9; color: #333; }}
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f6f9; color: #333; }}

        nav {{ position: fixed; top: 0; left: 0; width: 230px; height: 100vh; background: #1a2340; color: #cdd3e0; overflow-y: auto; padding: 24px 0; z-index: 100; }}
        nav h3 {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px; color: #7a84a0; padding: 0 20px 10px; }}
        nav ul {{ list-style: none; }}
        nav ul li a {{ display: block; padding: 9px 20px; color: #cdd3e0; text-decoration: none; font-size: 0.88rem; border-left: 3px solid transparent; transition: all 0.15s; }}
        nav ul li a:hover {{ background: #243058; border-left-color: #4e8cff; color: #fff; }}

        /* ---- Datenschutz-Schalter ---- */
        .privacy-toggle {{ display: flex; align-items: center; gap: 10px; padding: 10px 20px 18px; border-bottom: 1px solid #243058; margin-bottom: 10px; }}
        .privacy-toggle span {{ font-size: 0.8rem; color: #7a84a0; user-select: none; }}
        .toggle-switch {{ position: relative; width: 36px; height: 20px; flex-shrink: 0; cursor: pointer; }}
        .toggle-switch input {{ opacity: 0; width: 0; height: 0; }}
        .toggle-track {{ position: absolute; inset: 0; background: #3a4560; border-radius: 20px; transition: background 0.2s; }}
        .toggle-track::after {{ content: ''; position: absolute; left: 3px; top: 3px; width: 14px; height: 14px; background: #fff; border-radius: 50%; transition: transform 0.2s; }}
        .toggle-switch input:checked + .toggle-track {{ background: #4e8cff; }}
        .toggle-switch input:checked + .toggle-track::after {{ transform: translateX(16px); }}

        /* ---- Privat-Modus: sensible Werte ausblenden ---- */
        body.privacy-on .private {{
            color: transparent !important;
            text-shadow: 0 0 8px rgba(0,0,0,0.35);
            user-select: none;
            transition: color 0.2s, text-shadow 0.2s;
        }}
        body:not(.privacy-on) .private {{
            transition: color 0.2s, text-shadow 0.2s;
        }}

        main {{ margin-left: 230px; padding: 36px 40px; max-width: 1400px; }}
        header {{ margin-bottom: 32px; }}
        header h1 {{ font-size: 1.9rem; font-weight: 700; color: #1a2340; }}
        header p.subtitle {{ color: #666; margin-top: 4px; font-size: 0.95rem; }}
        .kpi-row {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 24px 0 32px; align-items: flex-start; }}
        .kpi-group {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 12px 16px;
                      background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.06);
                      align-items: stretch; }}
        .kpi-group + .kpi-group {{ border-left: 3px solid #e8ecf0; }}
        .kpi-group-wide {{ flex: 1 1 100%; }}
        .kpi-card {{ border-radius: 8px; padding: 10px 18px; min-width: 130px; background: #f4f6f9; }}
        .kpi-value {{ font-size: 1.25rem; font-weight: 700; color: #1a2340; line-height: 1.3; }}
        .kpi-value small {{ font-size: 0.75rem; font-weight: 400; color: #666; display: block; margin-top: 2px; }}
        .kpi-label {{ font-size: 0.75rem; color: #888; margin-top: 3px; text-transform: uppercase; letter-spacing: 0.04em; }}
        .kpi-warning {{ border: 2px solid #e55; background: #fff5f5; }}
        .kpi-warning .kpi-value {{ color: #c0392b; font-size: 1rem; word-break: break-word; }}
        .kpi-warning .kpi-label {{ color: #c0392b; }}
        .chart-section {{ background: #fff; border-radius: 12px; padding: 28px 32px; margin-bottom: 32px; box-shadow: 0 2px 10px rgba(0,0,0,.07); }}
        .chart-section h2 {{ font-size: 1.2rem; font-weight: 600; color: #1a2340; margin-bottom: 6px; }}
        .section-desc {{ color: #666; font-size: 0.9rem; margin-bottom: 16px; }}
        .chart-container {{ width: 100%; }}
        .plotly-lazy {{ min-height: 420px; }}
        .chart-placeholder {{
            min-height: 420px; display: flex; align-items: center; justify-content: center;
            color: #bbb; font-size: 0.95rem; background: #f9fafc; border-radius: 8px;
            border: 1px dashed #dde3ec;
        }}
        .table-wrapper {{ overflow-x: auto; }}
        .table-search {{ width: 100%; padding: 8px 12px; margin-bottom: 12px; border: 1px solid #dde3ec; border-radius: 6px; font-size: 0.9rem; outline: none; }}
        .table-search:focus {{ border-color: #4e8cff; box-shadow: 0 0 0 3px rgba(78,140,255,.15); }}
        .depot-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        .depot-table thead tr {{ background: #1a2340; color: #fff; }}
        .depot-table th {{ padding: 10px 14px; text-align: left; font-weight: 600; white-space: nowrap; }}
        .depot-table th.sortable {{ cursor: pointer; user-select: none; }}
        .depot-table th.sortable:hover {{ background: #243058; }}
        .depot-table th.sort-asc .sort-icon::after {{ content: ' ▲'; }}
        .depot-table th.sort-desc .sort-icon::after {{ content: ' ▼'; }}
        .sort-icon {{ font-size: 0.75rem; opacity: 0.6; }}
        .depot-table tbody tr:nth-child(even) {{ background: #f7f9fc; }}
        .depot-table tbody tr:hover {{ background: #eef2ff; }}
        .depot-table td {{ padding: 8px 14px; border-bottom: 1px solid #e8ecf0; white-space: nowrap; }}
        footer {{ color: #aaa; font-size: 0.8rem; padding: 24px 0 8px; text-align: center; }}
    </style>
</head>
<body>
    <nav>
        <!-- Datenschutz-Schalter -->
        <div class="privacy-toggle">
            <label class="toggle-switch" title="Vermögenswerte ausblenden">
                <input type="checkbox" id="privacy-cb" onchange="setPrivacy(this.checked)">
                <div class="toggle-track"></div>
            </label>
            <span>🔒 Privat</span>
        </div>
        <h3>Navigation</h3>
        <ul>{nav_items}</ul>
    </nav>
    <main>
        <header>
            <h1>📊 Portfolio-Analyse</h1>
            <p class="subtitle">Erstellt am {now}</p>
        </header>
        {summary_html}
        {sections_html}
        <footer>Automatisch generiert · {now}</footer>
    </main>

    <!-- Chart-JSON: type=application/json → kein JS-Parsing beim Seitenload, blockiert keinen Paint -->
    {chart_data_tags}

    <!-- Plotly.js inline (kein CDN, keine Netzwerkabhängigkeit) -->
    {plotlyjs_tag}

    <script>
    // ---- Datenschutz-Modus ----
    function setPrivacy(on) {{
        document.body.classList.toggle('privacy-on', on);
        localStorage.setItem('portfolio_privacy', on ? '1' : '0');
        document.getElementById('privacy-cb').checked = on;
    }}
    // Zustand beim Laden wiederherstellen
    document.addEventListener('DOMContentLoaded', function() {{
        const saved = localStorage.getItem('portfolio_privacy');
        if (saved === '1') setPrivacy(true);
    }});

    const _divIds   = {chart_div_ids};
    const _rendered = new Set();

    function _renderChart(entry) {{
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const id = el.id;
        if (_rendered.has(id)) return;
        _rendered.add(id);
        _observer.unobserve(el);
        const dataEl = document.getElementById('data-' + id);
        if (!dataEl) return;
        const spec = JSON.parse(dataEl.textContent);
        el.innerHTML = '';
        Plotly.newPlot(el, spec.data, spec.layout,
            {{displayModeBar: true, scrollZoom: false, responsive: true}});
    }}

    const _observer = new IntersectionObserver(
        entries => entries.forEach(_renderChart),
        {{rootMargin: '9999px'}}
    );

    document.addEventListener('DOMContentLoaded', function() {{
        _divIds.forEach(id => {{
            const el = document.getElementById(id);
            if (el) _observer.observe(el);
        }});
    }});

    // ---- Tabellensortierung ----
    let _sortCol = -1, _sortAsc = true;
    document.addEventListener('click', function(e) {{
        const th = e.target.closest('th.sortable');
        if (!th) return;
        const table = th.closest('table');
        const colIdx = parseInt(th.dataset.col);
        const isNum  = th.dataset.type === 'num';
        if (_sortCol === colIdx) {{ _sortAsc = !_sortAsc; }} else {{ _sortCol = colIdx; _sortAsc = true; }}
        table.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc','sort-desc'));
        th.classList.add(_sortAsc ? 'sort-asc' : 'sort-desc');
        const tbody = table.querySelector('tbody');
        const rows  = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {{
            const ca = a.querySelectorAll('td')[colIdx];
            const cb = b.querySelectorAll('td')[colIdx];
            if (!ca || !cb) return 0;
            let va = isNum ? parseFloat(ca.dataset.sort ?? ca.textContent) : ca.textContent.trim().toLowerCase();
            let vb = isNum ? parseFloat(cb.dataset.sort ?? cb.textContent) : cb.textContent.trim().toLowerCase();
            if (isNum) {{ va = isNaN(va) ? -Infinity : va; vb = isNaN(vb) ? -Infinity : vb; }}
            return _sortAsc ? (va > vb ? 1 : va < vb ? -1 : 0) : (va < vb ? 1 : va > vb ? -1 : 0);
        }});
        rows.forEach(r => tbody.appendChild(r));
    }});

    // ---- Tabellenfilter ----
    function filterTable(input) {{
        const q = input.value.toLowerCase();
        const table = input.closest('.table-wrapper').querySelector('table');
        table.querySelectorAll('tbody tr').forEach(row => {{
            row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
        }});
    }}
    </script>
</body>
</html>"""

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"HTML-Report gespeichert: {output_file}")
        webbrowser.open(Path(output_file).resolve().as_uri())
        logger.info("HTML-Report im Browser geöffnet.")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben des HTML-Reports: {e}")
        raise
