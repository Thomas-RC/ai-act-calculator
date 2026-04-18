"""Loader korpusu prawnego.

Ładuje XHTML-e pobrane przez scripts/refresh_sources.py i udostępnia jednolity
interfejs get(ref) → Article, gdzie ref to np. "ai_act:art_5" lub "ai_act:anx_III".

Strategia ładowania:
  1. Próba raw/ (aktualna kopia). Jak brak — fallback/ (snapshot offline).
  2. Parser lxml.html wyciąga <div id="art_N"> / <div id="anx_X"> do słownika.
  3. Tekst plainowany (text_content() + normalizacja białych znaków).
  4. Proweniencja (meta.json) doczytywana obok.

Przeznaczenie: injected do FastAPI przy starcie, Gemini otrzymuje wyjątki tekstowe
per referencja z KORPUSU.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lxml import html as lxml_html


# --- konfiguracja mapowania plik -> przedrostek referencyjny --------------

@dataclass(frozen=True)
class ZrodloPrawne:
    celex: str
    prefix: str  # używany jako przedrostek w referencjach ("ai_act:art_5")
    filename_stem: str


ZRODLA: tuple[ZrodloPrawne, ...] = (
    ZrodloPrawne("32024R1689", "ai_act", "32024R1689"),
    ZrodloPrawne("12012P/TXT", "kpp", "12012P_TXT"),
    ZrodloPrawne("32016R0679", "rodo", "32016R0679"),
)


# --- model domenowy -------------------------------------------------------

@dataclass(frozen=True)
class Meta:
    celex: str
    akt: str
    jezyk: str
    eli: str | None
    zrodlo_url: str
    data_pobrania: str
    data_weryfikacji: str
    sha256: str
    rozmiar_bajtow: int

    @classmethod
    def z_pliku(cls, path: Path) -> "Meta":
        d = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            celex=d["celex"],
            akt=d["akt"],
            jezyk=d["jezyk"],
            eli=d.get("eli"),
            zrodlo_url=d["zrodlo_url"],
            data_pobrania=d["data_pobrania"],
            data_weryfikacji=d["data_weryfikacji"],
            sha256=d["sha256"],
            rozmiar_bajtow=d["rozmiar_bajtow"],
        )


@dataclass(frozen=True)
class Article:
    ref: str              # "ai_act:art_5"
    tytul: str            # "Artykuł 5"
    nazwa: str            # "Zakazane praktyki w zakresie AI"
    tekst: str            # plain text, normalised whitespace
    meta: Meta            # proweniencja źródła

    def as_prompt_block(self) -> str:
        """Format do wstrzyknięcia do promptu Gemini."""
        naglowek = f"[{self.ref}] {self.tytul}"
        if self.nazwa:
            naglowek += f" — {self.nazwa}"
        return f"{naglowek}\n{self.tekst}"


# --- parser ---------------------------------------------------------------

_ODSTEPY = re.compile(r"\s+")


def _plain_text(el) -> str:
    tekst = el.text_content()
    # Pojedyncze białe znaki, bez ciągów spacji/NBSP/tabów
    return _ODSTEPY.sub(" ", tekst).strip()


_ART_NUM = re.compile(r"^Artykuł\s+(\d+)")


def _ma_klase(el, nazwa_klasy: str) -> bool:
    return nazwa_klasy in (el.get("class") or "").split()


def _parse_format_modern(doc, prefix: str, meta: Meta) -> dict[str, Article]:
    """AI Act / RODO: <div id="art_N"> + klasy oj-*."""
    wynik: dict[str, Article] = {}

    for el in doc.xpath('//*[starts-with(@id, "art_") and not(contains(@id, "."))]'):
        numer = el.get("id").removeprefix("art_")
        ref = f"{prefix}:art_{numer}"
        tytul_el = el.xpath('.//*[contains(@class, "oj-ti-art")][1]')
        nazwa_el = el.xpath('.//*[contains(@class, "oj-sti-art")][1]')
        tytul = _plain_text(tytul_el[0]) if tytul_el else f"Artykuł {numer}"
        nazwa = _plain_text(nazwa_el[0]) if nazwa_el else ""
        tekst = _plain_text(el)
        wynik[ref] = Article(ref=ref, tytul=tytul, nazwa=nazwa, tekst=tekst, meta=meta)

    for el in doc.xpath('//*[starts-with(@id, "anx_") and not(contains(@id, "."))]'):
        numer = el.get("id").removeprefix("anx_")
        ref = f"{prefix}:anx_{numer}"
        tytul_el = el.xpath(
            './/*[contains(@class, "oj-doc-ti") or contains(@class, "oj-ti-annotation") or contains(@class, "oj-ti-grseq")][1]'
        )
        tytul = _plain_text(tytul_el[0]) if tytul_el else f"Załącznik {numer}"
        tekst = _plain_text(el)
        wynik[ref] = Article(ref=ref, tytul=tytul, nazwa="", tekst=tekst, meta=meta)

    return wynik


def _parse_format_legacy(doc, prefix: str, meta: Meta) -> dict[str, Article]:
    """Karta Praw Podstawowych UE (2012): płaskie <p class="ti-art">Artykuł N</p>
    + kolejne paragrafy (sti-art, normal) aż do następnego ti-art.
    """
    wynik: dict[str, Article] = {}
    ti_arts = doc.xpath('//p[contains(concat(" ", normalize-space(@class), " "), " ti-art ")]')

    for ti in ti_arts:
        tytul = _plain_text(ti)
        m = _ART_NUM.match(tytul)
        if not m:
            continue
        numer = m.group(1)
        ref = f"{prefix}:art_{numer}"

        nazwa = ""
        czesci: list[str] = [tytul]
        rodzenstwo = ti.getnext()
        while rodzenstwo is not None:
            # Stop na następnym ti-art
            if _ma_klase(rodzenstwo, "ti-art"):
                break
            # Stop na nowej sekcji (oznacza koniec grupy artykułów)
            cls = rodzenstwo.get("class") or ""
            if cls.startswith("ti-section") or cls == "doc-end":
                break

            if _ma_klase(rodzenstwo, "sti-art") and not nazwa:
                nazwa = _plain_text(rodzenstwo)

            tresc = _plain_text(rodzenstwo)
            if tresc:
                czesci.append(tresc)
            rodzenstwo = rodzenstwo.getnext()

        wynik[ref] = Article(
            ref=ref,
            tytul=tytul,
            nazwa=nazwa,
            tekst=" ".join(czesci),
            meta=meta,
        )

    return wynik


def _parse_html(content: bytes, prefix: str, meta: Meta) -> dict[str, Article]:
    """Dispatcher: próbuje najpierw nowego formatu, jak pusto — legacy."""
    doc = lxml_html.fromstring(content)
    wynik = _parse_format_modern(doc, prefix, meta)
    if not wynik:
        wynik = _parse_format_legacy(doc, prefix, meta)
    return wynik


# --- główna klasa korpusu -------------------------------------------------

class Corpus:
    """In-memory corpus of legal articles, keyed by reference like 'ai_act:art_5'."""

    def __init__(self) -> None:
        self._articles: dict[str, Article] = {}
        self._metas: dict[str, Meta] = {}  # celex -> meta
        self._source: str | None = None    # "raw" albo "fallback"

    @classmethod
    def load(cls, legal_sources_dir: Path | str) -> "Corpus":
        """Ładuje korpus z legal_sources/raw/ (preferowane) lub fallback/."""
        base = Path(legal_sources_dir)
        corp = cls()

        for source_name in ("raw", "fallback"):
            source_dir = base / source_name
            if not source_dir.exists():
                continue
            # Sprawdź, czy pliki są kompletne dla wszystkich zrodel
            if all((source_dir / f"{z.filename_stem}.html").exists()
                   and (source_dir / f"{z.filename_stem}.meta.json").exists()
                   for z in ZRODLA):
                corp._load_from(source_dir)
                corp._source = source_name
                return corp

        raise FileNotFoundError(
            f"Korpus prawny nie znaleziony w {base}/raw ani {base}/fallback — "
            "uruchom scripts/refresh_sources.py"
        )

    def _load_from(self, source_dir: Path) -> None:
        for z in ZRODLA:
            html_path = source_dir / f"{z.filename_stem}.html"
            meta_path = source_dir / f"{z.filename_stem}.meta.json"
            meta = Meta.z_pliku(meta_path)
            self._metas[z.celex] = meta
            articles = _parse_html(html_path.read_bytes(), z.prefix, meta)
            self._articles.update(articles)

    # --- API publiczne ---

    @property
    def source(self) -> str:
        """Z którego katalogu załadowany (raw/fallback)."""
        return self._source or "?"

    @property
    def metas(self) -> dict[str, Meta]:
        return dict(self._metas)

    def get(self, ref: str) -> Article:
        if ref not in self._articles:
            raise KeyError(f"Brak artykułu {ref!r} w korpusie")
        return self._articles[ref]

    def get_many(self, refs: Iterable[str]) -> list[Article]:
        return [self.get(r) for r in refs]

    def has(self, ref: str) -> bool:
        return ref in self._articles

    def refs(self) -> list[str]:
        return sorted(self._articles.keys())

    def build_prompt_corpus(self, refs: Iterable[str]) -> str:
        """Łączy podane artykuły w jeden blok tekstowy dla promptu Gemini."""
        bloki = [a.as_prompt_block() for a in self.get_many(refs)]
        return "\n\n---\n\n".join(bloki)
