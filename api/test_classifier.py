"""Testy klasyfikatora na konkretnych case'ach.

Kluczowy case: RefundAI z kazusu CW2 — powinno wyjść WYSOKIE RYZYKO,
Art. 6 ust. 2 + Zał. III (sektor usług publicznych — refundacja NFZ).
"""

import pytest

from classifier import classify
from schemas import (
    Ankieta, Autonomia, Kategoria, PraktykaZakazana, Rola, SektorZalIII, TypDanych,
)


# ---------- Helper: bazowa ankieta (łatwo modyfikowalna per case) ---------

def _bazowa(**overrides) -> Ankieta:
    defaults = dict(
        opis="System AI do zastosowań biznesowych.",
        cel_systemu="Automatyzacja procesu decyzyjnego",
        praktyki_zakazane=[PraktykaZakazana.ZADNE],
        sektor=SektorZalIII.INNE,
        uzytkownik_koncowy="klient biznesowy",
        dane_wejsciowe=[TypDanych.OGOLNE],
        autonomia=Autonomia.DORADCZY,
        zal_I_produkt=False,
        art_50_generacja_lub_interakcja=False,
        rola=Rola.DOSTAWCA,
    )
    defaults.update(overrides)
    return Ankieta(**defaults)


# ---------- T1 [a] Art. 5 — NIEDOPUSZCZALNY -------------------------------

def test_social_scoring_niedopuszczalny():
    ankieta = _bazowa(praktyki_zakazane=[PraktykaZakazana.SOCIAL_SCORING])
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.NIEDOPUSZCZALNY
    assert wynik.short_circuit is True
    assert "ai_act:art_5" in wynik.legal_basis
    assert wynik.powiazane_artykuly == []


def test_biometria_realtime_niedopuszczalny():
    ankieta = _bazowa(
        praktyki_zakazane=[PraktykaZakazana.BIOMETRIA_MASOWA_REALTIME],
        sektor=SektorZalIII.SCIGANIE,  # nawet w sektorze Zał. III, Art. 5 wyprzedza
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.NIEDOPUSZCZALNY


def test_zadne_praktyki_zakazane_nie_short_circuit():
    ankieta = _bazowa(
        praktyki_zakazane=[PraktykaZakazana.ZADNE],
        sektor=SektorZalIII.EDUKACJA,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE
    assert wynik.short_circuit is False


# ---------- T1 [b] Art. 6 ust. 1 — produkt CE -----------------------------

def test_produkt_CE_wysokie_ryzyko():
    ankieta = _bazowa(zal_I_produkt=True)
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE
    assert "ai_act:art_6" in wynik.legal_basis
    # art_9, art_10, art_14, art_27 powinny być w powiązanych
    assert "ai_act:art_10" in wynik.powiazane_artykuly
    assert "ai_act:art_14" in wynik.powiazane_artykuly


# ---------- T1 [c] Art. 6 ust. 2 + Zał. III — sektor ----------------------

def test_refundai_z_kazusu_wysokie_ryzyko():
    """RefundAI: NFZ → usługi publiczne (Zał. III pkt 5)."""
    ankieta = _bazowa(
        opis="System AI do automatycznej oceny wniosków o refundację leków NFZ.",
        cel_systemu="Przyznaj/odrzuć/przekieruj do lekarza",
        sektor=SektorZalIII.USLUGI_PUBLICZNE,
        dane_wejsciowe=[TypDanych.ZDROWOTNE, TypDanych.OGOLNE],
        autonomia=Autonomia.WSPARCIE,
        rola=Rola.OBIE,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE
    assert wynik.short_circuit is False
    assert "ai_act:art_6" in wynik.legal_basis
    assert "ai_act:anx_III" in wynik.legal_basis
    assert "ai_act:art_27" in wynik.powiazane_artykuly  # FRIA


def test_sektor_edukacja_wysokie():
    ankieta = _bazowa(sektor=SektorZalIII.EDUKACJA)
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE


def test_sektor_zatrudnienie_wysokie():
    ankieta = _bazowa(sektor=SektorZalIII.ZATRUDNIENIE)
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE


# ---------- T1 [d] Art. 50 — OGRANICZONE ----------------------------------

def test_chatbot_marketingowy_ograniczone():
    ankieta = _bazowa(
        opis="Chatbot marketingowy odpowiadający na pytania klientów.",
        cel_systemu="Pre-sales",
        sektor=SektorZalIII.INNE,
        art_50_generacja_lub_interakcja=True,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.OGRANICZONE
    assert "ai_act:art_50" in wynik.legal_basis


def test_generator_obrazow_ograniczone():
    ankieta = _bazowa(
        sektor=SektorZalIII.INNE,
        art_50_generacja_lub_interakcja=True,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.OGRANICZONE


# ---------- T1 [e] Fallback — MINIMALNE ------------------------------------

def test_filtr_spamu_minimalne():
    ankieta = _bazowa(
        opis="Filtr antyspamowy oparty na klasyfikacji tekstów.",
        cel_systemu="Bezpieczeństwo e-mail",
        sektor=SektorZalIII.INNE,
        art_50_generacja_lub_interakcja=False,
        zal_I_produkt=False,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.MINIMALNE
    assert wynik.legal_basis == []


# ---------- Kolejność reguł (precedence) ----------------------------------

def test_art_5_wyprzedza_wszystko():
    """Social scoring W sektorze edukacji + produkt CE — i tak NIEDOPUSZCZALNY."""
    ankieta = _bazowa(
        praktyki_zakazane=[PraktykaZakazana.SOCIAL_SCORING],
        sektor=SektorZalIII.EDUKACJA,
        zal_I_produkt=True,
        art_50_generacja_lub_interakcja=True,
    )
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.NIEDOPUSZCZALNY


def test_produkt_CE_wyprzedza_art_50():
    ankieta = _bazowa(zal_I_produkt=True, art_50_generacja_lub_interakcja=True)
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE


def test_zal_III_wyprzedza_art_50():
    ankieta = _bazowa(sektor=SektorZalIII.EDUKACJA, art_50_generacja_lub_interakcja=True)
    wynik = classify(ankieta)
    assert wynik.kategoria == Kategoria.WYSOKIE


# ---------- Audytowalność: każdy case ma historię reguł -------------------

def test_historia_regul_jest_wypelniona():
    ankieta = _bazowa(sektor=SektorZalIII.INNE)  # trafi do MINIMALNE
    wynik = classify(ankieta)
    # 4 sprawdzone reguły + fallback = 5 kroków
    assert len(wynik.reguly_zastosowane) >= 4
    nazwy = [k.nazwa for k in wynik.reguly_zastosowane]
    assert any("Art. 5" in n for n in nazwy)
    assert any("Art. 6" in n for n in nazwy)
    assert any("Art. 50" in n for n in nazwy)
