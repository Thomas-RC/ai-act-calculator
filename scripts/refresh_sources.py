"""Pobiera teksty prawne z EUR-Lex (HTML, PL) dla kalkulatora ryzyka AI Act.

UWAGA o formacie:
  EUR-Lex udostępnia endpoint /legal-content/PL/TXT/XML/, który zwraca NOTICE
  (metadane Cellar), a NIE tekst FORMEX. Właściwy tekst po polsku jest tylko
  w /legal-content/PL/TXT/HTML/ — strukturalny XHTML z `<div id="art_5">…`,
  `<div id="anx_III">…` itd. To jest parsowalne lxml-em i wystarczające do
  ekstrakcji per artykuł.

Zapisuje:
  - legal_sources/raw/{CELEX}.html           pełny XHTML z EUR-Lex
  - legal_sources/raw/{CELEX}.meta.json      proweniencja (sha256, daty, URL)

Po udanym pobraniu synchronizuje do legal_sources/fallback/ (commitowany snapshot).

Uruchomienie:
    python scripts/refresh_sources.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "legal_sources" / "raw"
FALLBACK_DIR = ROOT / "legal_sources" / "fallback"

EURLEX_URL_TMPL = "https://eur-lex.europa.eu/legal-content/PL/TXT/HTML/?uri=CELEX:{celex}"
ELI_URL = {
    "32024R1689": "http://data.europa.eu/eli/reg/2024/1689/oj",
    "32016R0679": "http://data.europa.eu/eli/reg/2016/679/oj",
}


@dataclass(frozen=True)
class Akt:
    celex: str
    tytul: str
    filename: str  # bez rozszerzenia; używany dla .xml i .meta.json


AKTY = [
    Akt("32024R1689", "Rozporządzenie (UE) 2024/1689 (AI Act)", "32024R1689"),
    Akt("12012P/TXT", "Karta Praw Podstawowych Unii Europejskiej", "12012P_TXT"),
    Akt("32016R0679", "Rozporządzenie (UE) 2016/679 (RODO)", "32016R0679"),
]


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def pobierz_html(celex: str, timeout: int = 60) -> bytes:
    url = EURLEX_URL_TMPL.format(celex=celex)
    req = Request(url, headers={"User-Agent": "ai-act-calculator/refresh_sources (edu project)"})
    with urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise RuntimeError(f"EUR-Lex {celex}: HTTP {resp.status}")
        return resp.read()


def zapisz_akt(akt: Akt) -> dict:
    print(f"[{akt.celex}] pobieram: {akt.tytul}")
    tresc = pobierz_html(akt.celex)
    sha = hashlib.sha256(tresc).hexdigest()

    html_path = RAW_DIR / f"{akt.filename}.html"
    meta_path = RAW_DIR / f"{akt.filename}.meta.json"

    # Jeśli plik już istnieje i ma ten sam hash → tylko update data_weryfikacji
    poprzednie_pobranie = now_iso()
    if meta_path.exists():
        try:
            prev = json.loads(meta_path.read_text(encoding="utf-8"))
            if prev.get("sha256") == sha:
                poprzednie_pobranie = prev.get("data_pobrania", poprzednie_pobranie)
                print(f"[{akt.celex}] bez zmian (sha się zgadza)")
            else:
                print(f"[{akt.celex}] ZMIANA treści wykryta — nowy sha: {sha[:12]}…")
        except Exception:
            pass

    html_path.write_bytes(tresc)
    meta = {
        "celex": akt.celex,
        "akt": akt.tytul,
        "jezyk": "pl",
        "format": "xhtml",
        "eli": ELI_URL.get(akt.celex),
        "zrodlo_url": EURLEX_URL_TMPL.format(celex=akt.celex),
        "data_pobrania": poprzednie_pobranie,
        "data_weryfikacji": now_iso(),
        "sha256": sha,
        "rozmiar_bajtow": len(tresc),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{akt.celex}] zapisano: {html_path.name} ({len(tresc):_} B, sha {sha[:12]}…)")
    return meta


def synchronizuj_fallback() -> None:
    """Kopiuje raw/ → fallback/ (zastępuje istniejące, usuwa osierocone)."""
    if FALLBACK_DIR.exists():
        for p in FALLBACK_DIR.iterdir():
            if p.name != ".gitkeep":
                p.unlink()
    else:
        FALLBACK_DIR.mkdir(parents=True)

    for p in RAW_DIR.iterdir():
        if p.name == ".gitkeep":
            continue
        shutil.copy2(p, FALLBACK_DIR / p.name)
    print(f"[fallback] zsynchronizowano {len(list(FALLBACK_DIR.glob('*')))} plików")


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

    bledy: list[str] = []
    for akt in AKTY:
        try:
            zapisz_akt(akt)
        except (URLError, RuntimeError, OSError) as e:
            bledy.append(f"{akt.celex}: {e}")
            print(f"[{akt.celex}] BŁĄD: {e}", file=sys.stderr)

    if bledy:
        print(f"\n❌ Niepowodzenia: {len(bledy)}", file=sys.stderr)
        for b in bledy:
            print(f"  - {b}", file=sys.stderr)
        return 1

    synchronizuj_fallback()
    print("\n✅ Gotowe — korpus prawny pobrany i zsynchronizowany.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
