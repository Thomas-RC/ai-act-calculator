"""Deterministyczny klasyfikator ryzyka AI Act.

Decyzja o kategorii podejmowana jest WYŁĄCZNIE przez reguły w tym pliku,
nigdy przez LLM. Kaskada reguł (pierwsza pasująca wygrywa):

  T1 [a] Art. 5 AI Act — zakazane praktyki      → NIEDOPUSZCZALNY (short-circuit)
  T1 [b] Art. 6 ust. 1 AIA + Załącznik I (CE)   → WYSOKIE RYZYKO
  T1 [c] Art. 6 ust. 2 AIA + Załącznik III      → WYSOKIE RYZYKO
  T1 [d] Art. 50 AIA (transparentność)          → OGRANICZONE
  T1 [e] fallback                                → MINIMALNE

Każda reguła zwraca:
  - kategorię (Kategoria enum),
  - listę legal_basis (ref-ów do artykułów korpusu),
  - dodatkowe „powiązane" artykuły wrzucane do promptu LLM jako kontekst obowiązków.
"""

from __future__ import annotations

from schemas import (
    Ankieta,
    Kategoria,
    PraktykaZakazana,
    SektorZalIII,
    StepReguly,
    WynikKlasyfikacji,
)


# Mapowanie: praktyka zakazana → punkt Art. 5 ust. 1 lit. X
ART5_MAPA: dict[PraktykaZakazana, str] = {
    PraktykaZakazana.MANIPULACJA_PODPROGOWA:            "ai_act:art_5",  # lit. a
    PraktykaZakazana.EXPLOITATION_WRAZLIWOSCI:          "ai_act:art_5",  # lit. b
    PraktykaZakazana.SOCIAL_SCORING:                    "ai_act:art_5",  # lit. c
    PraktykaZakazana.PREDYKCJA_PRZESTEPCZOSCI:          "ai_act:art_5",  # lit. d
    PraktykaZakazana.SCRAPING_TWARZY:                   "ai_act:art_5",  # lit. e
    PraktykaZakazana.ROZPOZNAWANIE_EMOCJI_PRACA_EDUKACJA: "ai_act:art_5",  # lit. f
    PraktykaZakazana.KATEGORYZACJA_BIOMETRYCZNA_CHRONIONE: "ai_act:art_5",  # lit. g
    PraktykaZakazana.BIOMETRIA_MASOWA_REALTIME:         "ai_act:art_5",  # lit. h
}

# Mapowanie: sektor → punkt Załącznika III (refencja w korpusie to całe anx_III)
SEKTOR_DO_PUNKTU_ZAL_III: dict[SektorZalIII, int] = {
    SektorZalIII.BIOMETRIA: 1,
    SektorZalIII.INFRASTRUKTURA_KRYTYCZNA: 2,
    SektorZalIII.EDUKACJA: 3,
    SektorZalIII.ZATRUDNIENIE: 4,
    SektorZalIII.USLUGI_PUBLICZNE: 5,
    SektorZalIII.SCIGANIE: 6,
    SektorZalIII.MIGRACJA: 7,
    SektorZalIII.WYMIAR_SPRAWIEDLIWOSCI: 8,
}

# Artykuły które ZAWSZE idą do promptu LLM dla kategorii WYSOKIE RYZYKO
# (rozdział III sekcja 2 AI Act — wymogi dla systemów wysokiego ryzyka)
ART_POWIAZANE_WYSOKIE = [
    "ai_act:art_9",   # system zarządzania ryzykiem
    "ai_act:art_10",  # dane i zarządzanie danymi
    "ai_act:art_11",  # dokumentacja techniczna
    "ai_act:art_13",  # przejrzystość wobec deployera
    "ai_act:art_14",  # nadzór ludzki
    "ai_act:art_15",  # dokładność, solidność, cyberbezpieczeństwo
    "ai_act:art_27",  # FRIA (Fundamental Rights Impact Assessment)
]

ART_POWIAZANE_OGRANICZONE = [
    "ai_act:art_50",  # transparentność wobec osób fizycznych
]


def _ma_zakazana_praktyke(ankieta: Ankieta) -> list[PraktykaZakazana]:
    return [p for p in ankieta.praktyki_zakazane if p != PraktykaZakazana.ZADNE]


def classify(ankieta: Ankieta) -> WynikKlasyfikacji:
    """Główna funkcja — zwraca WynikKlasyfikacji z kategorią i legal_basis."""
    kroki: list[StepReguly] = []

    # [a] Art. 5 — zakazane praktyki (short-circuit)
    zakazane = _ma_zakazana_praktyke(ankieta)
    if zakazane:
        kroki.append(StepReguly(
            nazwa="Art. 5 AI Act — zakazane praktyki",
            opis=f"System realizuje praktyki zakazane: {', '.join(p.value for p in zakazane)}",
        ))
        return WynikKlasyfikacji(
            kategoria=Kategoria.NIEDOPUSZCZALNY,
            legal_basis=["ai_act:art_5"],
            powiazane_artykuly=[],
            reguly_zastosowane=kroki,
            short_circuit=True,
        )
    kroki.append(StepReguly(
        nazwa="Art. 5 AI Act",
        opis="Brak zakazanych praktyk.",
    ))

    # [b] Art. 6 ust. 1 + Załącznik I (produkt z CE)
    if ankieta.zal_I_produkt:
        kroki.append(StepReguly(
            nazwa="Art. 6 ust. 1 + Załącznik I AI Act",
            opis="System jest komponentem produktu objętego unijnym prawem harmonizacyjnym.",
        ))
        return WynikKlasyfikacji(
            kategoria=Kategoria.WYSOKIE,
            legal_basis=["ai_act:art_6"],
            powiazane_artykuly=ART_POWIAZANE_WYSOKIE,
            reguly_zastosowane=kroki,
            short_circuit=False,
        )
    kroki.append(StepReguly(
        nazwa="Art. 6 ust. 1 + Załącznik I",
        opis="System nie jest produktem z oceną zgodności.",
    ))

    # [c] Art. 6 ust. 2 + Załącznik III (sektor wysokiego ryzyka)
    if ankieta.sektor != SektorZalIII.INNE:
        punkt = SEKTOR_DO_PUNKTU_ZAL_III.get(ankieta.sektor)
        kroki.append(StepReguly(
            nazwa="Art. 6 ust. 2 + Załącznik III AI Act",
            opis=f"Sektor '{ankieta.sektor.value}' ≡ Zał. III pkt {punkt}.",
        ))
        return WynikKlasyfikacji(
            kategoria=Kategoria.WYSOKIE,
            legal_basis=["ai_act:art_6", "ai_act:anx_III"],
            powiazane_artykuly=ART_POWIAZANE_WYSOKIE,
            reguly_zastosowane=kroki,
            short_circuit=False,
        )
    kroki.append(StepReguly(
        nazwa="Art. 6 ust. 2 + Załącznik III",
        opis="Sektor nie mieści się w Załączniku III.",
    ))

    # [d] Art. 50 — transparentność
    if ankieta.art_50_generacja_lub_interakcja:
        kroki.append(StepReguly(
            nazwa="Art. 50 AI Act — transparentność",
            opis="System wchodzi w interakcję z człowiekiem lub generuje treści.",
        ))
        return WynikKlasyfikacji(
            kategoria=Kategoria.OGRANICZONE,
            legal_basis=["ai_act:art_50"],
            powiazane_artykuly=ART_POWIAZANE_OGRANICZONE,
            reguly_zastosowane=kroki,
            short_circuit=False,
        )
    kroki.append(StepReguly(
        nazwa="Art. 50 AI Act",
        opis="Brak obowiązku transparentności z Art. 50.",
    ))

    # [e] fallback — minimalne ryzyko
    kroki.append(StepReguly(
        nazwa="Fallback — minimalne ryzyko",
        opis="Żadna reguła kaskady nie zastosowana.",
    ))
    return WynikKlasyfikacji(
        kategoria=Kategoria.MINIMALNE,
        legal_basis=[],
        powiazane_artykuly=[],
        reguly_zastosowane=kroki,
        short_circuit=False,
    )
