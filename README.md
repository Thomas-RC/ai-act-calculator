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

1. Docker + docker-compose.
2. Plik service account key z GCP dla projektu z włączonym Vertex AI, zapisany jako:
   ```
   secrets/vertex-wfirma-dev-ea19981c2c30.json
   ```
3. Skopiuj `.env.example` do `.env` i ewentualnie popraw wartości.

### Start

```bash
docker compose up --build
```

- Frontend: <http://localhost:8080>
- API (docs): <http://localhost:8000/docs>

### Pierwsze odświeżenie korpusu prawnego

Inicjalnie pobierz XML-e z EUR-Lex i zapisz do `legal_sources/fallback/`:

```bash
docker compose run --rm api python scripts/refresh_sources.py
```

Potem w runtime API sam aktualizuje (jak jest sieć) lub używa fallbacku.

---

## Struktura repo

```
ai-act-calculator/
├── secrets/              # service account JSON (NIE commitowany)
├── legal_sources/        # korpus prawny
│   ├── raw/              # świeży XML (runtime, nie commitowany)
│   └── fallback/         # snapshot offline (commitowany)
├── scripts/
│   └── refresh_sources.py
├── api/                  # FastAPI + Vertex AI + logika klasyfikacji
└── web/                  # nginx + HTML + Tailwind + Alpine
```

---

## Uwaga prawna

Klasyfikacja ma charakter **doradczy**. Nie zastępuje porady prawnej ani pełnego audytu zgodności z AI Act. Źródła prawne pobierane bezpośrednio z EUR-Lex (CELEX + data pobrania + sha256 w stopce każdego raportu).
