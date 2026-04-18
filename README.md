# Kalkulator ryzyka AI Act

Narzędzie klasyfikujące systemy AI pod kątem wymogów Rozporządzenia (UE) 2024/1689 (AI Act).
Na podstawie 10-pytaniowej ankiety zwraca kategorię ryzyka + listę obowiązków dostawcy/deployera + raport PDF.

**Projekt zaliczeniowy — Etyka w AI (WSB, 2025/2026).** Autor: Tomasz Rosik.

---

## Stos technologiczny

- **Backend:** Python + FastAPI
- **LLM:** Google Vertex AI — Gemini 2.5 Pro (`europe-west9`, EOG-only)
- **Frontend:** HTML + TailwindCSS + AlpineJS, serwowany przez nginx
- **PDF:** WeasyPrint
- **Korpus prawny:** FORMEX XML z EUR-Lex (AI Act, KPP UE, RODO)
- **Runtime:** docker-compose (2 serwisy: `api`, `web`)

Architektura i user flow: patrz [.doc/Plan_MVP_Kalkulator_AI_Act.md](.doc/Plan_MVP_Kalkulator_AI_Act.md).

---

## Uruchomienie

### Wymagania wstępne

1. **Docker Desktop** (albo Docker Engine + docker-compose v2).
2. **Service account JSON** z GCP — projekt z włączonym Vertex AI i uprawnieniem `roles/aiplatform.user`. Plik zapisany jako:
   ```
   secrets/vertex-wfirma-dev-ea19981c2c30.json
   ```
   (nie commitowany — patrz `.gitignore`).
3. (Opcjonalnie) `.env` z własnymi wartościami (domyślne są OK — patrz `.env.example`).

### Start

```bash
docker compose up --build
```

- **Frontend:** <http://localhost:8080> — tu się klika
- **API docs (Swagger):** <http://localhost:8000/docs>
- **Health:** <http://localhost:8000/api/health>

Pierwsze uruchomienie buduje obrazy — potem `docker compose up` startuje w ~5s.

### Odświeżenie korpusu prawnego

Korpus (AI Act, KPP UE, RODO z EUR-Lex) jest już w repo w `legal_sources/fallback/`.
Aby pobrać aktualną wersję:

```bash
docker compose run --rm api python /scripts/refresh_sources.py
```

Skrypt pobiera XHTML z EUR-Lex, liczy sha256, zapisuje do `legal_sources/raw/`, i synchronizuje `fallback/ ← raw/`. Commituj `fallback/` po zmianie.

### Testy

```bash
docker compose run --rm api python -m pytest -v
```

30 testów: 6 config (walidacja EOG), 10 legal (parser XHTML, treść artykułów), 14 classifier (wszystkie ścieżki Art. 5/6/50 + precedence + RefundAI z kazusu CW2).

---

## Struktura repo

```
ai-act-calculator/
├── docker-compose.yml
├── .env.example
├── secrets/              # service account JSON (NIE commitowany)
├── legal_sources/        # korpus prawny (XHTML z EUR-Lex)
│   ├── raw/              # świeży download (runtime, nie commitowany)
│   └── fallback/         # snapshot offline (commitowany)
├── scripts/
│   └── refresh_sources.py
├── api/                  # FastAPI + Vertex AI + logika
│   ├── Dockerfile
│   ├── main.py           # endpointy: /api/classify, /api/report, /api/health, /api/meta
│   ├── classifier.py     # deterministyczne reguły kaskadowe
│   ├── legal.py          # loader XHTML (lxml) + słownik artykułów
│   ├── vertex_client.py  # klient Gemini (europe-west9, JSON mode)
│   ├── prompts.py        # system prompt z groundingiem na korpusie
│   ├── report.py         # WeasyPrint → PDF
│   ├── schemas.py        # Pydantic models
│   ├── config.py         # settings + walidacja EOG
│   ├── templates/        # Jinja2 template PDF-a
│   └── test_*.py         # 30 testów (pytest)
└── web/                  # nginx + HTML + Tailwind + Alpine
    ├── Dockerfile
    ├── nginx.conf        # statyka + proxy /api/ → api:8000
    ├── index.html        # SPA, 4 widoki: form / loading / error / result
    └── assets/
        ├── app.js        # AlpineJS — cały state
        └── style.css
```

## Jak to działa — krok po kroku

1. **Start kontenera `api`:** loader `legal.py` parsuje `legal_sources/` (raw lub fallback), buduje słownik ~279 artykułów (AI Act 126, RODO 99, KPP UE 54).
2. **User otwiera frontend:** Alpine pobiera `/api/meta` → wyświetla datę korpusu w nagłówku + badge „EOG-only".
3. **User wypełnia ankietę (10 pytań w 4 sekcjach)** → klika „Klasyfikuj system".
4. **Backend** (`POST /api/classify`):
   - `classifier.py` — kaskada reguł Art. 5 → Zał. I → Zał. III → Art. 50 → fallback. Wynik: kategoria + `legal_basis`.
   - Jeśli NIEDOPUSZCZALNY → **short-circuit** (bez LLM).
   - W przeciwnym razie: `legal.py` wyciąga teksty właściwych artykułów → Gemini 2.5 Flash (europe-west9) z promptem + KORPUSEM → structured JSON (uzasadnienie, obowiązki dostawcy/deployera, wątpliwości, rekomendacje).
5. **User widzi wynik** — duży kolorowy badge kategorii, historia reguł, checklisty obowiązków, wątpliwości, rekomendacje, proweniencja źródeł.
6. **User klika „Pobierz PDF"** → `POST /api/report` → WeasyPrint renderuje raport ze stopką zawierającą CELEX + sha256 + datę pobrania korpusu.

---

## Uwaga prawna

Klasyfikacja ma charakter **doradczy**. Nie zastępuje porady prawnej ani pełnego audytu zgodności z AI Act. Źródła prawne pobierane bezpośrednio z EUR-Lex (CELEX + data pobrania + sha256 w stopce każdego raportu).
