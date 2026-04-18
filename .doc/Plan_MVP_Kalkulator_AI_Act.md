# Plan MVP — Kalkulator ryzyka AI Act

**Autor:** Tomasz Rosik
**Data:** 2026-04-18
**Projekt zaliczeniowy:** Praca Projektowa (60% oceny)
**Temat:** Temat 1 — Kalkulator ryzyka AI Act

---

## 1. Cel narzędzia

Narzędzie webowe, które na podstawie krótkiej ankiety klasyfikuje system AI użytkownika do jednej z czterech kategorii ryzyka wg AI Act (Rozporządzenie 2024/1689) i generuje spersonalizowany raport z listą obowiązków prawnych oraz wątpliwościami interpretacyjnymi.

**Użytkownik docelowy:** dostawca lub deployer systemu AI — startup, dział IT, compliance officer.

**Problem etyczny:** firmy wdrażają AI nie wiedząc, czy ich system jest „wysokiego ryzyka" i jakie obowiązki z tego wynikają. Skutek: albo over-compliance (paraliż wdrożenia), albo under-compliance (ryzyko kar do 35 mln EUR / 7% obrotu).

---

## 2. Architektura — docker-compose, 2 serwisy

```
ai-act-calculator/
├── docker-compose.yml
├── .env                      # VERTEX_PROJECT_ID, VERTEX_LOCATION, MODEL_NAME
├── .gitignore                # secrets/, .env, __pycache__, *.pdf
├── secrets/
│   └── vertex-wfirma-dev-ea19981c2c30.json   # service account (NIE commitować)
├── legal_sources/            # korpus prawny — źródło autorytatywne (FORMEX XML z EUR-Lex)
│   ├── README.md             # co jest skąd, jak odświeżyć
│   ├── raw/                  # pełne pliki FORMEX XML pobrane z EUR-Lex, NIEMODYFIKOWANE
│   │   ├── 32024R1689.xml    # AI Act 2024/1689 (PL)
│   │   ├── 32024R1689.meta.json  # {celex, eli, url, data_pobrania, data_weryfikacji, sha256}
│   │   ├── 12012P_TXT.xml    # Karta Praw Podstawowych UE
│   │   ├── 12012P_TXT.meta.json
│   │   ├── 32016R0679.xml    # RODO 2016/679
│   │   └── 32016R0679.meta.json
│   └── fallback/             # kopia raw/ z momentu buildu — używana offline
│       └── (identyczne pliki)
├── scripts/
│   └── refresh_sources.py    # pobiera XML z EUR-Lex → raw/ + aktualizuje meta.json
├── api/                      # backend: FastAPI + logika + Vertex AI
│   ├── Dockerfile
│   ├── requirements.txt      # fastapi, uvicorn, google-cloud-aiplatform, vertexai, weasyprint, pydantic
│   ├── main.py               # endpoints: POST /classify, POST /report
│   ├── classifier.py         # deterministyczne reguły → kategoria ryzyka
│   ├── vertex_client.py      # Gemini przez vertexai SDK
│   ├── prompts.py            # system prompt + schemat JSON odpowiedzi (grounding z legal.py)
│   ├── legal.py              # startup refresh + parsowanie FORMEX XML + dostęp per-artykuł
│   ├── report.py             # WeasyPrint → PDF (reużywam template z kazusu)
│   ├── templates/
│   │   └── report.html       # szablon raportu
│   └── schemas.py            # pydantic: Questionnaire, ClassificationResult, ReportRequest
└── web/                      # frontend: statyczne HTML + Tailwind + Alpine
    ├── Dockerfile            # nginx:alpine
    ├── nginx.conf            # serwuje /, proxy_pass /api/* → api:8000
    ├── index.html            # szablon bazowy (layout, nagłówek)
    ├── assets/
    │   ├── app.js            # logika AlpineJS: store, fetch do API, renderowanie wyniku
    │   └── style.css         # (opcjonalnie) custom warstwa nad Tailwind
    └── partials/
        ├── questionnaire.html # krok 1: formularz ankiety
        └── result.html        # krok 2: karta z wynikiem + przycisk PDF
```

### Serwisy w `docker-compose.yml`

| Serwis | Port | Rola |
|---|---|---|
| `api`  | 8000 | FastAPI — logika klasyfikacji + Vertex AI + generator PDF |
| `web`  | 8080 | nginx — statyczny HTML/Tailwind/Alpine + proxy `/api/*` do backendu |

**Wolumeny:** `./secrets:/secrets:ro` do kontenera `api`.
**Zmienne środowiskowe (api):** `GOOGLE_APPLICATION_CREDENTIALS=/secrets/vertex-wfirma-dev-ea19981c2c30.json`, `VERTEX_PROJECT_ID`, `VERTEX_LOCATION=europe-west9`, `MODEL_NAME=gemini-2.5-pro`.
**Komunikacja:** przeglądarka → `nginx` (`/api/*` → `http://api:8000`). Dzięki proxy po stronie nginx nie potrzeba CORS ani hardcodowanego URL backendu w HTML.

### Residencja danych — EOG-only (wymóg projektu)

| Komponent | Lokalizacja | Uzasadnienie |
|---|---|---|
| Vertex AI (Gemini) | `europe-west9` (Paris, FR) | Region w granicach EOG; zgodność z RODO + AI Act art. 10 ust. 5 + minimalizacja transferów międzynarodowych. |
| Cache / logi aplikacji | lokalnie w kontenerze (bez zewnętrznych usług) | Dane wejściowe użytkownika (opisy systemów AI mogą zawierać informacje poufne) nie opuszczają infrastruktury uruchamiającej prototyp. |
| PDF-y wygenerowane | ulotne, w pamięci procesu | Brak persystencji; plik wraca w odpowiedzi HTTP i ginie po zamknięciu sesji. |
| Service account key | lokalnie w `./secrets/` (read-only mount) | Nie commitowane, nie wysyłane poza maszynę użytkownika. |

**Wymóg techniczny:** w konfiguracji Vertex wymuszamy `location="europe-west9"` (nie multi-region `eu` — ten może wpaść na endpointy spoza EOG). Weryfikacja w runtime: `api/main.py` przy starcie loguje i odrzuca nie-EOG location.

---

## 3. Przepływ: input → logika → output

### 3.1 Input (ankieta ~10 pytań MVP)

| # | Pytanie | Typ |
|---|---|---|
| 1 | Krótki opis systemu AI (1–3 zdania) | tekst |
| 2 | Główny cel systemu | select |
| 3 | Czy system używa manipulacji podświadomej, scoringu społecznego, biometrii masowej? (Art. 5) | yes/no + szczegóły |
| 4 | Sektor wdrożenia (Zał. III) — edukacja / zatrudnienie / usługi publiczne / ściganie / ... | select |
| 5 | Typ użytkownika końcowego | select (konsument / pracownik / obywatel / inny system) |
| 6 | Dane wejściowe (ogólne / biometryczne / zdrowotne / behawioralne) | multi-select |
| 7 | Stopień autonomii (doradczy / częściowa decyzja / pełna decyzja automatyczna) | select |
| 8 | Czy system jest elementem produktu podlegającego ocenie zgodności (Zał. I)? | yes/no |
| 9 | Czy system generuje treści (tekst/obraz/audio) wchodzi w interakcję z człowiekiem? (Art. 50) | yes/no |
| 10 | Rola użytkownika: dostawca / deployer / obie | select |

### 3.2 Logika — **hybryda reguły + LLM**

1. **Klasyfikator deterministyczny (`classifier.py`):** reguły decyzyjne w kolejności:
   - jeśli spełnia Art. 5 → **NIEDOPUSZCZALNY**
   - jeśli Zał. I + ocena zgodności → **WYSOKIE RYZYKO** (Art. 6 ust. 1)
   - jeśli sektor z Zał. III → **WYSOKIE RYZYKO** (Art. 6 ust. 2)
   - jeśli Art. 50 (interakcja/generacja) i nie wyżej → **OGRANICZONE**
   - w przeciwnym razie → **MINIMALNE**
2. **Generator uzasadnienia (`vertex_client.py` → Gemini):** dostaje klasyfikację + odpowiedzi użytkownika, zwraca **structured JSON**:
   ```json
   {
     "uzasadnienie": "...",
     "podstawa_prawna": ["art. 6 ust. 2 AIA", "Zał. III pkt 5"],
     "obowiazki_dostawcy": ["..."],
     "obowiazki_deployera": ["..."],
     "watpliwosci_interpretacyjne": ["..."],
     "rekomendacje_nastepne_kroki": ["..."]
   }
   ```
3. **Generator PDF (`report.py`):** WeasyPrint składa raport w stylistyce zbliżonej do wzorca Harvard (reużywam CSS z kazusu CW2).

### 3.3 Output — widok w przeglądarce (Tailwind + Alpine)

Jednostronicowa aplikacja, dwa stany (Alpine `x-data`: `step='form' | 'result'`):

**Nagłówek wyniku:** duży badge kategorii z kolorem semantycznym Tailwind:
- NIEDOPUSZCZALNY → `bg-red-600` + ikona zakazu
- WYSOKIE RYZYKO → `bg-orange-500` + ikona ostrzeżenia
- OGRANICZONE → `bg-yellow-400` + ikona info
- MINIMALNE → `bg-green-500` + ikona check

**Karty wyniku (grid `md:grid-cols-2`):**
- Podstawa prawna (art. + Załącznik III), lista z cytatami
- Obowiązki dostawcy — checklist z ikonami (`lucide` via CDN)
- Obowiązki deployera — checklist
- Wątpliwości interpretacyjne — żółty callout w stylu „note"
- Rekomendowane następne kroki — oś pionowa (timeline)

**Akcje:** przycisk **„Pobierz raport PDF"** (gradient primary), przycisk **„Rozpocznij od nowa"** (ghost).

**Design tokeny Tailwind:** paleta `slate` + accent `indigo`/`emerald`, typografia `font-sans` (Inter via Google Fonts), zaokrąglenia `rounded-2xl`, cienie `shadow-md`, spacing luźny (`p-6`, `gap-4`).

### 3.4 Pełny user flow — krok po kroku

**Uwaga o statusie prawnym:** sprawdzanie statusu prawnego systemu AI to **core** narzędzia — nie pojedynczy krok ukryty w backendzie, ale trzyetapowa weryfikacja (T1 → T2 → T3 poniżej) realizowana przez klasyfikator + loader korpusu + LLM. Każdy etap wprost cytuje źródło prawne (CELEX + artykuł + data pobrania korpusu).

```
┌────────────────────────────────────────────────────────────────────────┐
│  KROK 0 (bootstrap przy starcie kontenera `api`)                      │
│  ────────────────────────────────────────────                         │
│  legal.py wczytuje legal_sources/*.md → słownik artykułów             │
│  Waliduje nagłówek proweniencji (CELEX, ELI, data_pobrania)           │
│  Jeśli korpus starszy niż N dni → log WARN „korpus nieaktualny"      │
│  API nie wstaje bez poprawnego korpusu (fail-fast)                   │
└────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────┐
│  EKRAN 1: LANDING                                                     │
│  ────────────────────────────────────────────                         │
│  Tytuł: "Kalkulator ryzyka AI Act"                                    │
│  Lead: "Odpowiedz na 10 pytań, otrzymasz klasyfikację                 │
│         ryzyka Twojego systemu AI + listę obowiązków prawnych         │
│         i raport PDF."                                                │
│  Badge EOG-only · "Dane nie opuszczają EOG (Vertex AI Paryż)"         │
│  [ Rozpocznij → ]                                                     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ klik „Rozpocznij"
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  EKRAN 2: ANKIETA (4 sekcje, progress bar góra)                       │
│  ────────────────────────────────────────────                         │
│  SEKCJA A — IDENTYFIKACJA SYSTEMU (pyt. 1–2)                         │
│    1. Krótki opis systemu AI (1–3 zdania) [textarea]                 │
│    2. Główny cel systemu [select: decyzje adm. / HR / med. /         │
│       marketing / bezpieczeństwo / edukacja / inne]                  │
│                                                                      │
│  SEKCJA B — FILTR ART. 5 (pyt. 3) — "czerwone flagi"                │
│    3. Czy system wykorzystuje którekolwiek z poniższych?             │
│       ☐ manipulacja podświadoma / exploitation wrażliwości            │
│       ☐ social scoring przez władzę publiczną                         │
│       ☐ biometria masowa w przestrzeni publicznej                    │
│       ☐ rozpoznawanie emocji w pracy/edukacji                         │
│       ☐ predykcja przestępczości na bazie cech osobowych             │
│       ☐ żadne z powyższych                                            │
│                                                                      │
│  SEKCJA C — ZAKRES I KONTEKST (pyt. 4–7)                            │
│    4. Sektor wdrożenia [select: edukacja / zatrudnienie /            │
│       migracja / ściganie / wymiar spraw. / zdrowie / finanse /      │
│       usługi publiczne / bezpieczeństwo krytyczne / inne]            │
│    5. Typ użytkownika końcowego [select]                             │
│    6. Dane wejściowe [multi-select: ogólne / biometryczne /          │
│       zdrowotne / behawioralne / lokalizacyjne]                      │
│    7. Stopień autonomii decyzji [radio: doradczy / wsparcie /        │
│       automatyczna]                                                  │
│                                                                      │
│  SEKCJA D — ELEMENTY DODATKOWE (pyt. 8–10)                          │
│    8. Czy system jest elementem produktu z Zał. I (CE)? [y/n]        │
│    9. Czy system generuje treści / wchodzi w interakcję               │
│       z człowiekiem? [y/n]                                            │
│   10. Rola użytkownika [radio: dostawca / deployer / obie]           │
│                                                                      │
│  [ ← Wstecz ]                         [ Podsumowanie → ]             │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ klik „Podsumowanie"
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  EKRAN 3: PODSUMOWANIE ODPOWIEDZI (preview)                           │
│  ────────────────────────────────────────────                         │
│  Lista 10 odpowiedzi z możliwością edycji (ikona ołówka)             │
│  Info: "Kliknij «Klasyfikuj», aby wysłać odpowiedzi do Gemini        │
│         w regionie europe-west9. Dane nie są zapisywane."            │
│  [ ← Edytuj ]             [ Klasyfikuj system → ]                    │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ klik „Klasyfikuj"
                               ▼  POST /api/classify  {odpowiedzi...}
┌────────────────────────────────────────────────────────────────────────┐
│  BACKEND — SPRAWDZANIE STATUSU PRAWNEGO (spinner na froncie)          │
│  ════════════════════════════════════════════════════════              │
│                                                                      │
│  ▼ T1. WERYFIKACJA DETERMINISTYCZNA (classifier.py)                   │
│     reguły kaskadowe, każda cytuje konkretny artykuł:                 │
│                                                                      │
│     [a] filtr Art. 5 AIA — 8 zakazanych praktyk                      │
│         dopasowanie odpowiedzi 3 do listy lit. a–h                   │
│         MATCH → status = NIEDOPUSZCZALNY + art. 5 lit. X             │
│                (STOP — nie wołamy LLM, nie przetwarzamy dalej)        │
│                                                                      │
│     [b] filtr Art. 6 ust. 1 AIA + Załącznik I (CE)                    │
│         odp. 8 = TAK ∧ produkt z Zał. I?                              │
│         MATCH → status = WYSOKIE RYZYKO (ścieżka produktowa)          │
│                                                                      │
│     [c] filtr Art. 6 ust. 2 AIA + Załącznik III (sektory)             │
│         mapowanie odp. 4 (sektor) → punkty Zał. III (1–8)             │
│         MATCH → status = WYSOKIE RYZYKO (ścieżka sektorowa)           │
│                                                                      │
│     [d] filtr Art. 50 AIA (transparentność)                           │
│         odp. 9 = TAK i nie wyżej klasyfikowane?                       │
│         MATCH → status = OGRANICZONE                                  │
│                                                                      │
│     [e] fallback → MINIMALNE                                          │
│                                                                      │
│     output T1: { category, legal_basis: ["ai_act:art_6_ust_2",       │
│                  "ai_act:zal_III_pkt_5_lit_a"], ... }                │
│                                                                      │
│  ▼ T2. POBRANIE WŁAŚCIWYCH TEKSTÓW PRAWNYCH (legal.py)                │
│     dla każdego `legal_basis` z T1 wyciąga pełny tekst                │
│     artykułu z `legal_sources/ai_act_pl.md` + metadane                │
│     (CELEX 32024R1689, ELI, data_pobrania)                            │
│     dodaje artykuły powiązane przez reguły obowiązków:                │
│       WYSOKIE → dodaj Art. 9, 10, 11, 13, 14, 15, 27                 │
│       OGRANICZONE → dodaj Art. 50 ust. 1–4                            │
│     wynik: paczka {basis + powiązane} jako grounding dla T3           │
│                                                                      │
│  ▼ T3. GENERACJA OPISU SKUTKÓW PRAWNYCH (vertex_client.py)            │
│     Gemini 2.5 Pro @ europe-west9, JSON mode                          │
│     SYSTEM: "Jesteś asystentem prawnym AI Act. WOLNO Ci cytować       │
│       WYŁĄCZNIE tekst dostarczony w sekcji KORPUS. Zakaz cytowania    │
│       artykułów spoza KORPUSU. Odpowiedź w JSON wg schemy."          │
│     USER: { klasyfikacja z T1 + odpowiedzi użytkownika +              │
│             korpus z T2 }                                             │
│     output: {                                                         │
│       uzasadnienie,                                                   │
│       obowiazki_dostawcy: [{tekst, podstawa}],                        │
│       obowiazki_deployera: [{tekst, podstawa}],                       │
│       watpliwosci_interpretacyjne: [...],                             │
│       rekomendacje_nastepne_kroki: [...]                              │
│     }                                                                 │
│                                                                      │
│  ▼ T4. ZŁOŻENIE ODPOWIEDZI (main.py)                                  │
│     merge(T1 + T3) + proweniencja z T2 + disclaimer                   │
│     Return 200 application/json                                       │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ response 200 { category, ...}
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  EKRAN 4: WYNIK                                                        │
│  ────────────────────────────────────────────                         │
│  ┌──────────────────────────────────────────────────────┐             │
│  │  ⚠ WYSOKIE RYZYKO                                    │ ← badge     │
│  │  Podstawa: Art. 6 ust. 2 + Zał. III pkt 5 lit. a    │  kolor      │
│  └──────────────────────────────────────────────────────┘             │
│                                                                       │
│  [ Uzasadnienie ]                                                     │
│  "System klasyfikuje się jako wysokiego ryzyka, ponieważ…"           │
│                                                                       │
│  [ Obowiązki dostawcy ]            [ Obowiązki deployera ]           │
│  ✓ System zarządzania ryzykiem     ✓ Monitoring post-deployment      │
│  ✓ Jakość i zarządzanie danymi     ✓ Rejestr incydentów              │
│  ✓ Dokumentacja techniczna         ✓ FRIA (Art. 27) przed wdroż.    │
│  ✓ Nadzór ludzki (Art. 14)         ✓ Informowanie osób                │
│  ✓ Oznaczenie CE                                                      │
│                                                                       │
│  [ Wątpliwości interpretacyjne ]  ← żółty callout                    │
│  • czy punkt X Zał. III obejmuje przypadek Y?                        │
│  • interakcja z Art. 22 RODO wymaga osobnej analizy                  │
│                                                                       │
│  [ Następne kroki ] ← timeline pionowy                               │
│  1. FRIA przed wdrożeniem (Art. 27)                                  │
│  2. Rejestracja w bazie UE (Art. 49)                                 │
│  3. Audyt jakości danych treningowych (Art. 10)                      │
│                                                                       │
│  Stopka: "Źródła: AI Act 2024/1689 (CELEX 32024R1689),               │
│           data korpusu 2026-04-18. Klasyfikacja ma charakter         │
│           doradczy, nie zastępuje porady prawnej."                   │
│                                                                       │
│  [ Pobierz raport PDF ]           [ ↺ Rozpocznij od nowa ]           │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ klik „Pobierz PDF"
                               ▼  POST /api/report  {full_state}
┌────────────────────────────────────────────────────────────────────────┐
│  BACKEND — GENERATOR PDF                                              │
│  report.py: Jinja2 → HTML → WeasyPrint → bytes                        │
│  Nagłówek: nazwa systemu · kategoria · data                           │
│  Treść: pełne uzasadnienie + checklist + cytaty artykułów             │
│  Stopka każdej strony: CELEX/ELI + data pobrania korpusu              │
│  Return: application/pdf, filename="ai_act_raport_{timestamp}.pdf"    │
└────────────────────────────────────────────────────────────────────────┘
```

**Kluczowe punkty flow:**

- **Sprawdzanie statusu prawnego = 3 etapy (T1–T3)**, nie jedna funkcja. Podział jest celowy: T1 jest deterministyczne i audytowalne (reguły w kodzie), T2 dostarcza materiał źródłowy (proweniencja), T3 to tylko redakcja tekstu na podstawie T1+T2.
- **Short-circuit na Art. 5** — jeśli T1 wykryje zakazaną praktykę, pipeline kończy się na T1 i **nie wywołuje LLM** (oszczędność + zero halucynacji w ekstremalnym przypadku).
- **LLM nie decyduje o statusie prawnym** — T3 Gemini dostaje już gotową kategorię z T1 i artykuły z T2. System prompt zabrania cytowania spoza KORPUSU → redukcja halucynacji prawnych.
- **Proweniencja dla audytora** — każda odpowiedź zawiera `legal_basis: ["ai_act:art_6_ust_2", ...]` oraz nagłówek korpusu (CELEX, ELI, data_pobrania), który trafia do PDF-a. Można odtworzyć rozstrzygnięcie.
- **Brak persystencji** — state trzymany w Alpine `x-data` po stronie przeglądarki; backend nie zapisuje niczego do pliku ani bazy. Po zamknięciu karty wszystko znika.
- **Transparentność (Art. 50)** — na każdym ekranie z wynikiem widoczna informacja, że klasyfikacja pochodzi częściowo z AI (Gemini) i ma charakter doradczy.

---

## 4. Źródła prawne — FORMEX XML z EUR-Lex, refresh przy starcie + offline fallback

Narzędzie traktuje **FORMEX XML z EUR-Lex** jako **jedyne autorytatywne źródło** tekstów prawnych (nie Markdown — ten byłby naszą interpretacją, nieweryfikowalną). Korpus jest odświeżany przy starcie kontenera + raz dziennie w tle; gdy sieć padnie, aplikacja używa kopii z repo (`fallback/`). Każda odpowiedź narzędzia zawiera proweniencję (CELEX, ELI, data, sha256) nadającą się do audytu.

### 4.1 Wykaz źródeł i endpointy EUR-Lex

| Akt | CELEX | ELI | Endpoint FORMEX XML (PL) |
|---|---|---|---|
| AI Act (Rozporządzenie 2024/1689) | `32024R1689` | `http://data.europa.eu/eli/reg/2024/1689/oj` | `https://eur-lex.europa.eu/legal-content/PL/TXT/XML/?uri=CELEX:32024R1689` |
| Karta Praw Podstawowych UE (2012/C 326/02) | `12012P/TXT` | — | `https://eur-lex.europa.eu/legal-content/PL/TXT/XML/?uri=CELEX:12012P/TXT` |
| RODO (Rozporządzenie 2016/679) | `32016R0679` | `http://data.europa.eu/eli/reg/2016/679/oj` | `https://eur-lex.europa.eu/legal-content/PL/TXT/XML/?uri=CELEX:32016R0679` |

Dodatkowo: **SPARQL Cellar** (`https://publications.europa.eu/webapi/rdf/sparql`) do sprawdzenia `dct:modified` — czy jest nowsza wersja skonsolidowana. **ISAP / eli.gov.pl** w rezerwie dla przyszłej polskiej ustawy wdrożeniowej.

EUR-Lex nie ma kluczowanego REST API, ale te URL-e są stabilne, bez rate-limitu istotnego dla naszej skali i nie wymagają rejestracji.

### 4.2 Zakres wyciągu — które artykuły używamy

- **AI Act:** Art. 3, 5, 6, 10, 14, 22, 27, 50 + **Załącznik III** (8 punktów).
- **KPP UE:** Art. 20, 21, 35, 41, 47.
- **RODO:** Art. 5, 6, 9, 22.

Pełne XML-e są pobierane w całości — wyciąg per artykuł następuje w runtime przez XPath.

### 4.3 Format pliku w `legal_sources/raw/`

Dwa pliki na każdy akt: **`{CELEX}.xml`** (niemodyfikowany FORMEX z EUR-Lex) + **`{CELEX}.meta.json`**:

```json
{
  "celex": "32024R1689",
  "eli": "http://data.europa.eu/eli/reg/2024/1689/oj",
  "akt": "Rozporządzenie (UE) 2024/1689 (AI Act)",
  "jezyk": "pl",
  "zrodlo_url": "https://eur-lex.europa.eu/legal-content/PL/TXT/XML/?uri=CELEX:32024R1689",
  "data_pobrania": "2026-04-18T09:12:44Z",
  "data_weryfikacji": "2026-04-18T09:12:44Z",
  "sha256": "a3f1c9e4…",
  "rozmiar_bajtow": 1284732,
  "wersja": "original"
}
```

`data_pobrania` = kiedy treść faktycznie się zmieniła. `data_weryfikacji` = kiedy ostatnio sprawdzaliśmy EUR-Lex i hash się zgadzał. Różnica: weryfikacja codzienna, pobranie tylko przy zmianie.

### 4.4 Cykl życia korpusu (Opcja B — refresh przy starcie + cron 24 h)

```
┌─────────────────────────────────────────────────────────────┐
│  STARTUP kontenera `api` (lub tick cron co 24 h)            │
│  ─────────────────────────────────────────────              │
│  for akt in AKTY:                                           │
│    1. HEAD/GET https://eur-lex.europa.eu/... CELEX          │
│    2. jeśli sieć padnie → wczytaj legal_sources/fallback/   │
│       + log WARN „offline mode, korpus z {data}"            │
│    3. oblicz sha256 pobranego XML                           │
│    4. porównaj z meta.json.sha256                           │
│       — bez zmian → tylko update data_weryfikacji           │
│       — zmiana → zapis do raw/, update data_pobrania        │
│         + log INFO „korpus zaktualizowany, nowy sha:…"      │
│    5. parse XML do in-memory dict artykułów                 │
└─────────────────────────────────────────────────────────────┘
```

**Offline-first:** aplikacja startuje nawet bez sieci — fallback zawsze działa. Sieć jest opcjonalnym ulepszeniem.

### 4.5 Jak korpus jest używany w runtime

1. `legal.py` przy starcie buduje `articles: dict[str, Article]`, np.:
   ```python
   articles["ai_act:art_5_ust_1_lit_a"] = Article(
       celex="32024R1689",
       tekst="Zakazuje się następujących praktyk…",
       meta=meta_json,
   )
   ```
2. Klasyfikator zwraca `legal_basis: ["ai_act:art_6_ust_2", "ai_act:zal_III_pkt_5_lit_a"]` — same referencje.
3. Prompt Gemini dostaje **tekst** tych artykułów jako sekcja `KORPUS`, z instrukcją „cytuj wyłącznie stąd".
4. PDF raportu w stopce każdej strony: `Źródło: EUR-Lex CELEX 32024R1689 · pobrano 2026-04-18 · sha256: a3f1c9e4…`.

### 4.6 Skrypt `scripts/refresh_sources.py` — do inicjalnego buildu i deweloperskiego odświeżania

Pseudokod:
```python
AKTY = [
    ("32024R1689", "32024R1689.xml"),
    ("12012P/TXT", "12012P_TXT.xml"),
    ("32016R0679", "32016R0679.xml"),
]
for celex, fname in AKTY:
    url = f"https://eur-lex.europa.eu/legal-content/PL/TXT/XML/?uri=CELEX:{celex}"
    xml = httpx.get(url, timeout=30).content
    sha = hashlib.sha256(xml).hexdigest()
    (RAW / fname).write_bytes(xml)
    (RAW / fname.replace(".xml", ".meta.json")).write_text(json.dumps({
        "celex": celex, "sha256": sha,
        "data_pobrania": now_iso(), ...
    }))
shutil.copytree(RAW, FALLBACK, dirs_exist_ok=True)  # snapshot offline
```

Uruchamiany lokalnie przy inicjalnym buildu oraz zawsze gdy chcemy „zaszyć" świeższy fallback w repo.

---

## 5. Kluczowe decyzje techniczne

| Decyzja | Uzasadnienie | Alternatywa (odrzucona) |
|---|---|---|
| **Hybryda reguły + LLM** | Klasyfikacja ryzyka jest deterministyczna prawnie — LLM tylko do generacji tekstu. Unikam halucynacji kategorii. | Pełny LLM end-to-end (ryzyko błędnej klasyfikacji). |
| **Statyczny korpus prawny w repo (`legal_sources/`)** | Reprodukowalność, proweniencja (CELEX+ELI+data), grounding LLM, demo offline. | Dynamiczny fetch z EUR-Lex w runtime (wolne, ryzyko zmian HTML, zależność sieci). |
| **TailwindCSS + AlpineJS (przez CDN)** | Estetyczny, nowoczesny UI bez build-pipeline; Tailwind daje spójny design-system, Alpine wystarcza dla reaktywnego formularza bez Reacta/Vue. | Streamlit (odrzucone — wygląd „dashboardowy"); React/Next.js (overkill dla MVP solo). |
| **Gemini 2.5 Pro (Vertex AI) w `europe-west9`** | Mocny reasoning prawny; region fizycznie w EOG (Paryż) — dane nie opuszczają EOG, zgodność z RODO i wewnętrzną polityką projektu; JSON mode wspierany. | GPT-4/Claude (wymaga zmiany stacku); multi-region `eu` (może routować poza EOG). |
| **nginx jako serwer statyczny + reverse proxy** | Jedyny punkt wejścia dla przeglądarki, brak CORS, łatwy deploy. | FastAPI+Jinja2 (mieszanie warstw — backend renderujący HTML). |
| **FastAPI jako oddzielny backend** | Czysta separacja prezentacji od logiki → łatwiej pokazać architekturę w raporcie, przyszła integracja z innymi UI. | Wszystko w jednym serwisie (szybsze, ale gorzej uzasadnialne architektonicznie). |
| **WeasyPrint do PDF** | Sprawdzony w zadaniu kazusu, dobra typografia. | ReportLab (niższy poziom, dużo kodu). |
| **Service account JSON w `secrets/` + mount read-only** | Bezpieczniej niż env var, zgodne z best-practice GCP. | Key w env (widoczny w `docker inspect`). |

---

## 6. Struktura raportu (3+ strony) — szkielet

1. **Problem etyczny** — firmy nie znają swoich obowiązków z AI Act; risk over/under-compliance.
2. **Użytkownik narzędzia** — dostawca/deployer systemu AI; kontekst: przygotowanie do wdrożenia, audyt zgodności.
3. **Opis narzędzia** — wejście (ankieta) → logika (reguły + Gemini) → wyjście (klasyfikacja + PDF).
4. **Uzasadnienie techniczne** — patrz sekcja 5 planu; dodatkowo proweniencja źródeł prawnych (sekcja 4).
5. **Analiza etyczna narzędzia** — ryzyka: (a) nadmierne zaufanie użytkownika do klasyfikacji („AI audytuje AI"), (b) halucynacje LLM w sekcji obowiązków, (c) RODO — przetwarzanie opisu systemu. Mitygacje: disclaimery, ograniczenie LLM do generacji tekstu nie klasyfikacji, brak persystencji danych.
6. **Odniesienie do AI Act** — samo narzędzie jest **ograniczonego ryzyka** (Art. 50 — generuje tekst, wchodzi w interakcję; nie jest w Zał. III). Obowiązek transparentności: użytkownik wie, że rozmawia z AI i że klasyfikacja jest doradcza, nie wiążąca prawnie.
7. **Wnioski i ograniczenia** — MVP obejmuje ~10 pytań; brak GPAI, FRIA, pełnej mapy Zał. III; brak historii ankiet.
8. **Podział pracy** — praca indywidualna (wszystko: technika, raport, prezentacja).

---

## 7. Plan wdrożenia — kolejność prac

1. **Szkielet repo** — `docker-compose.yml`, `Dockerfile` × 2, `requirements.txt` × 2, `.gitignore`.
2. **Korpus prawny** — pobrać z EUR-Lex wskazane artykuły (AI Act, KPP, RODO) do `legal_sources/*.md` z nagłówkiem proweniencji; napisać `scripts/refresh_sources.py`.
3. **Loader korpusu** — `api/legal.py` + testy (czy słownik zawiera `ai_act:art_5`, `ai_act:zal_III_pkt_5` itd.).
4. **Vertex client** — minimalne wywołanie Gemini 2.5 Pro z JSON mode, test credentials.
5. **Classifier** — reguły w `classifier.py`, testy jednostkowe na case'ach (RefundAI = WYSOKIE, chatbot marketingowy = OGRANICZONE, social scoring = NIEDOPUSZCZALNY).
6. **API endpoints** — `POST /api/classify` (reguły + LLM z groundingiem na `legal_sources/`), `POST /api/report` (PDF).
7. **Frontend HTML** — `index.html` + Tailwind (Play CDN lub standalone CLI) + AlpineJS + `lucide` ikonki; dwa widoki: formularz i wynik.
8. **nginx config** — serve static + `location /api/ { proxy_pass http://api:8000/; }`.
9. **Template PDF** — HTML + CSS w stylu wzorca Harvard (reużycie z kazusu CW2); stopka z CELEX + datą pobrania.
10. **Smoke test end-to-end** — case RefundAI z kazusu: oczekiwana kategoria WYSOKIE RYZYKO, Zał. III pkt 5 lit. a.
11. **README + instrukcja uruchomienia** — `docker compose up`, `http://localhost:8080`.

---

## 8. Pytania otwarte do potwierdzenia

1. **Region Vertex AI** — `europe-west9` (Paryż, EOG) — **potwierdzone**.
2. **Project ID** — wyciągnąć z JSON key automatycznie, czy podać jawnie w `.env`?
3. **Model** — `gemini-2.5-pro` (jakość) czy `gemini-2.5-flash` (koszt/szybkość)? Dla MVP: Flash wystarcza.
4. **Języki** — UI i raport po polsku (konsekwentnie z kazusem), prompt do Gemini też po polsku.
5. **Zakres ankiety** — 10 pytań MVP czy 15 (dodać GPAI i FRIA)?
6. **Autentykacja użytkownika** — dla MVP brak (demo lokalnie); do rozważenia w sekcji „ograniczenia".
7. **Źródła prawne** — zakres artykułów z sekcji 4.2 OK, czy dorzucić coś jeszcze (np. Art. 52 GPAI, Art. 86 prawo do wyjaśnienia)?

---

*Plan opracowany na bazie briefingu „Praca Projektowa — narzędzie techniczne oparte na AI" (waga 60%). Technologia: Python + FastAPI + Vertex AI Gemini (region `europe-west9`, EOG-only) + TailwindCSS + AlpineJS + nginx + WeasyPrint. Uruchomienie: `docker compose up` → `http://localhost:8080`.*
