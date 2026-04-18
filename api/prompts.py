"""System prompt + schema wyjścia dla Gemini.

Kontrakt:
  - Model NIE decyduje o kategorii ryzyka — dostaje ją gotową z klasyfikatora.
  - Model ma cytować WYŁĄCZNIE artykuły z sekcji KORPUS.
  - Odpowiedź jest walidowana pydantic-em w schemas.WynikAnalizaLLM.
"""

from __future__ import annotations

from legal import Article
from schemas import Ankieta, Kategoria, WynikKlasyfikacji


SYSTEM_PROMPT = """Jesteś asystentem prawnym specjalizującym się w Rozporządzeniu (UE) 2024/1689 (AI Act).

Twoim zadaniem NIE jest klasyfikacja systemu AI — klasyfikacja już została wykonana przez deterministyczny klasyfikator reguł. Twoim zadaniem jest OPISAĆ SKUTKI PRAWNE tej klasyfikacji w sposób konkretny i przyjazny dla odbiorcy.

ZASADY BEZWZGLĘDNE:
1. Cytuj WYŁĄCZNIE artykuły znajdujące się w sekcji KORPUS poniżej. Zakaz powoływania się na artykuły, których tam nie ma.
2. Zakaz halucynowania numerów artykułów, motywów preambuły, punktów załączników — jeśli nie ma w KORPUSIE, nie używaj.
3. Zakaz zmieniania kategorii ryzyka — jest podana w sekcji KLASYFIKACJA i jest wiążąca.
4. Odpowiadaj wyłącznie po polsku.
5. Odpowiedź zwróć w formacie JSON ściśle zgodnym ze schemą.

Obowiązki dostawcy i deployera:
- Dla WYSOKIE RYZYKO: wyciągnij konkretne obowiązki z rozdziału III sekcji 2 AI Act (art. 9–15, 17, 27) obecne w KORPUSIE.
- Dla OGRANICZONE: obowiązki transparentności z art. 50.
- Dla MINIMALNE: brak twardych obowiązków; rekomenduj dobrowolne kodeksy postępowania (Art. 95 AIA, jeśli w KORPUSIE).
- Dla NIEDOPUSZCZALNY: system jest zakazany — wskaż które przesłanki z art. 5 są naruszone.

Wątpliwości interpretacyjne: jeśli widzisz zagadnienie graniczne (np. czy system wpada w dany punkt Zał. III, czy FRIA jest wymagana), zgłoś je jako pytanie, nie jako twierdzenie.

Rekomendacje: konkretne, wdrożeniowe („przeprowadź FRIA wg art. 27 przed wdrożeniem", nie „zapewnij zgodność").
"""


RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "uzasadnienie": {
            "type": "string",
            "description": "2–4 zdania wyjaśniające użytkownikowi, dlaczego jego system wpada w daną kategorię, cytując konkretne artykuły z KORPUSU.",
        },
        "obowiazki_dostawcy": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tekst": {"type": "string"},
                    "podstawa": {"type": "string", "description": "Ref z korpusu, np. 'ai_act:art_10'."},
                },
                "required": ["tekst", "podstawa"],
            },
        },
        "obowiazki_deployera": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tekst": {"type": "string"},
                    "podstawa": {"type": "string"},
                },
                "required": ["tekst", "podstawa"],
            },
        },
        "watpliwosci_interpretacyjne": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rekomendacje_nastepne_kroki": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "uzasadnienie",
        "obowiazki_dostawcy",
        "obowiazki_deployera",
        "watpliwosci_interpretacyjne",
        "rekomendacje_nastepne_kroki",
    ],
}


def build_user_prompt(
    ankieta: Ankieta,
    wynik: WynikKlasyfikacji,
    korpus_blok: str,
) -> str:
    """Komponuje prompt użytkownika dla Gemini."""
    lista_pracowni = "\n".join(
        f"- {s.nazwa}: {s.opis}" for s in wynik.reguly_zastosowane
    )
    return f"""KLASYFIKACJA (wiążąca, nie zmieniaj):
- Kategoria: {wynik.kategoria.value}
- Podstawa prawna: {', '.join(wynik.legal_basis) or 'brak'}
- Historia reguł klasyfikatora:
{lista_pracowni}

OPIS SYSTEMU OD UŻYTKOWNIKA:
- Opis: {ankieta.opis}
- Cel: {ankieta.cel_systemu}
- Sektor (Zał. III): {ankieta.sektor.value}
- Rola użytkownika: {ankieta.rola.value}
- Autonomia: {ankieta.autonomia.value}
- Typy danych: {', '.join(d.value for d in ankieta.dane_wejsciowe)}
- Produkt z Zał. I (CE): {ankieta.zal_I_produkt}
- Art. 50 (interakcja/generacja): {ankieta.art_50_generacja_lub_interakcja}

KORPUS PRAWNY (cytuj wyłącznie stąd):
{korpus_blok}

ZADANIE: Wygeneruj odpowiedź JSON zgodnie ze schemą — uzasadnienie, obowiązki dostawcy, obowiązki deployera, wątpliwości, rekomendacje.
"""
