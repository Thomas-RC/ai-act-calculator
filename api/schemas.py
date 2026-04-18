"""Modele danych API: input ankiety, wynik klasyfikatora, wynik LLM, pełna odpowiedź.

Enum-y odpowiadają strukturze AI Act:
  - Art. 5 ust. 1: 8 zakazanych praktyk (lit. a–h).
  - Załącznik III: 8 obszarów wysokiego ryzyka (pkt 1–8).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# --- Enums ----------------------------------------------------------------

class Kategoria(str, Enum):
    NIEDOPUSZCZALNY = "NIEDOPUSZCZALNY"
    WYSOKIE = "WYSOKIE"
    OGRANICZONE = "OGRANICZONE"
    MINIMALNE = "MINIMALNE"


class PraktykaZakazana(str, Enum):
    """Art. 5 ust. 1 AI Act — zakazane praktyki."""
    MANIPULACJA_PODPROGOWA = "manipulacja_podprogowa"                # lit. a
    EXPLOITATION_WRAZLIWOSCI = "exploitation_wrazliwosci"            # lit. b
    SOCIAL_SCORING = "social_scoring"                                 # lit. c
    PREDYKCJA_PRZESTEPCZOSCI = "predykcja_przestepczosci"            # lit. d
    SCRAPING_TWARZY = "scraping_twarzy"                               # lit. e
    ROZPOZNAWANIE_EMOCJI_PRACA_EDUKACJA = "rozpoznawanie_emocji"     # lit. f
    KATEGORYZACJA_BIOMETRYCZNA_CHRONIONE = "kategoryzacja_biometryczna"  # lit. g
    BIOMETRIA_MASOWA_REALTIME = "biometria_realtime_publiczna"       # lit. h
    ZADNE = "zadne"


class SektorZalIII(str, Enum):
    """Załącznik III AI Act — 8 obszarów wysokiego ryzyka."""
    BIOMETRIA = "biometria"                        # pkt 1
    INFRASTRUKTURA_KRYTYCZNA = "infrastruktura"    # pkt 2
    EDUKACJA = "edukacja"                           # pkt 3
    ZATRUDNIENIE = "zatrudnienie"                   # pkt 4
    USLUGI_PUBLICZNE = "uslugi_publiczne"          # pkt 5 (świadczenia, zdrowie, kredyt)
    SCIGANIE = "sciganie"                           # pkt 6
    MIGRACJA = "migracja"                           # pkt 7
    WYMIAR_SPRAWIEDLIWOSCI = "wymiar_sprawiedliwosci"  # pkt 8
    INNE = "inne"


class TypDanych(str, Enum):
    OGOLNE = "ogolne"
    BIOMETRYCZNE = "biometryczne"
    ZDROWOTNE = "zdrowotne"
    BEHAWIORALNE = "behawioralne"
    LOKALIZACYJNE = "lokalizacyjne"


class Autonomia(str, Enum):
    DORADCZY = "doradczy"           # AI sugeruje, człowiek decyduje
    WSPARCIE = "wsparcie"           # AI ogranicza opcje, człowiek wybiera
    AUTOMATYCZNA = "automatyczna"   # AI decyduje, człowiek tylko monitoruje


class Rola(str, Enum):
    DOSTAWCA = "dostawca"
    DEPLOYER = "deployer"
    OBIE = "obie"


# --- Input: ankieta -------------------------------------------------------

class Ankieta(BaseModel):
    """10-pytaniowa ankieta opisująca system AI użytkownika."""

    opis: str = Field(min_length=10, max_length=2000,
                      description="Krótki opis systemu AI (1–3 zdania).")
    cel_systemu: str = Field(min_length=3, max_length=200,
                              description="Główny cel systemu.")
    praktyki_zakazane: list[PraktykaZakazana] = Field(
        default_factory=list,
        description="Które z 8 praktyk z Art. 5 ust. 1 system realizuje (jeśli żadna — [ZADNE] lub pusta)."
    )
    sektor: SektorZalIII = Field(
        description="Sektor wdrożenia. Decyduje o art. 6 ust. 2 (Zał. III).",
    )
    uzytkownik_koncowy: str = Field(min_length=3, max_length=200,
                                      description="Kto jest użytkownikiem końcowym (konsument, pracownik, obywatel, inny system AI).")
    dane_wejsciowe: list[TypDanych] = Field(
        default_factory=lambda: [TypDanych.OGOLNE],
        description="Typy danych wejściowych.",
    )
    autonomia: Autonomia
    zal_I_produkt: bool = Field(
        description="Czy system jest elementem produktu objętego unijnym prawem harmonizacyjnym (Zał. I — np. zabawki, wyroby medyczne, motoryzacja, maszyny) wymagającym oceny zgodności?"
    )
    art_50_generacja_lub_interakcja: bool = Field(
        description="Czy system generuje treści (tekst/obraz/audio) lub wchodzi w bezpośrednią interakcję z człowiekiem?"
    )
    rola: Rola


# --- Wynik klasyfikatora (przed LLM) -------------------------------------

class StepReguly(BaseModel):
    """Jeden krok kaskady reguł — który filtr wygrał i dlaczego."""
    nazwa: str
    opis: str


class WynikKlasyfikacji(BaseModel):
    kategoria: Kategoria
    legal_basis: list[str] = Field(
        description="Referencje do artykułów korpusu, np. ['ai_act:art_6', 'ai_act:anx_III']",
    )
    powiazane_artykuly: list[str] = Field(
        description="Dodatkowe artykuły doklejane do promptu Gemini (np. Art. 9, 10, 11, 13, 14 dla wysokiego ryzyka).",
    )
    reguly_zastosowane: list[StepReguly] = Field(
        description="Historia kaskady — każdy krok i jego wynik. Audytowalność.",
    )
    short_circuit: bool = Field(
        default=False,
        description="True gdy klasyfikator zdecydował samodzielnie bez potrzeby LLM (np. Art. 5).",
    )


# --- Wynik analizy LLM ----------------------------------------------------

class Obowiazek(BaseModel):
    tekst: str
    podstawa: str = Field(description="Referencja do korpusu, np. 'ai_act:art_10'.")


class WynikAnalizaLLM(BaseModel):
    uzasadnienie: str
    obowiazki_dostawcy: list[Obowiazek] = Field(default_factory=list)
    obowiazki_deployera: list[Obowiazek] = Field(default_factory=list)
    watpliwosci_interpretacyjne: list[str] = Field(default_factory=list)
    rekomendacje_nastepne_kroki: list[str] = Field(default_factory=list)


# --- Pełna odpowiedź API --------------------------------------------------

class MetaZrodla(BaseModel):
    """Proweniencja korpusu — trafia do stopki PDF."""
    celex: str
    akt: str
    eli: str | None = None
    data_pobrania: str
    data_weryfikacji: str
    sha256: str


class OdpowiedzKlasyfikacji(BaseModel):
    kategoria: Kategoria
    wynik_reguly: WynikKlasyfikacji
    wynik_llm: WynikAnalizaLLM | None = Field(
        default=None,
        description="None gdy short_circuit — np. Art. 5 nie idzie do LLM.",
    )
    korpus_meta: list[MetaZrodla] = Field(
        description="Proweniencja wszystkich załadowanych aktów prawnych.",
    )
    disclaimer: str = Field(
        default="Klasyfikacja ma charakter doradczy. Nie zastępuje porady prawnej ani pełnego audytu zgodności."
    )


class RaportRequest(BaseModel):
    """Dane wysyłane z frontendu do /api/report — odpowiedź z /api/classify + (opcjonalnie) ankieta."""
    odpowiedz: OdpowiedzKlasyfikacji
    ankieta: Ankieta | None = None
