"""Generator PDF — WeasyPrint nad Jinja2 template."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from schemas import Ankieta, OdpowiedzKlasyfikacji

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_jinja = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(wynik: OdpowiedzKlasyfikacji, ankieta: Ankieta | None = None) -> str:
    tpl = _jinja.get_template("report.html")
    return tpl.render(
        wynik=wynik,
        ankieta=ankieta,
        data_generacji=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        rola=ankieta.rola.value if ankieta else "—",
    )


def render_pdf(wynik: OdpowiedzKlasyfikacji, ankieta: Ankieta | None = None) -> bytes:
    from weasyprint import HTML
    html_str = render_html(wynik, ankieta)
    return HTML(string=html_str).write_pdf()
