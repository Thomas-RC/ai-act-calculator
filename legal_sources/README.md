# Korpus prawny — `legal_sources/`

Teksty prawne używane przez kalkulator ryzyka AI Act, pobierane bezpośrednio z EUR-Lex.

## Uwaga o formacie

EUR-Lex udostępnia endpoint `/legal-content/PL/TXT/XML/`, ale **zwraca on tylko NOTICE** (metadane Cellar w formacie `<NOTICE>`), nie tekst ustawy. Właściwa treść po polsku dostępna jest pod `/legal-content/PL/TXT/HTML/` jako strukturalny XHTML z klarowną semantyką — każdy artykuł ma `id="art_N"`, załączniki `id="anx_X"`, ustępy `id="NNN.xxx"`.

Dlatego korpus trzymamy jako **XHTML, nie FORMEX XML**. Do parsowania per artykuł używamy `lxml` + XPath (`//div[@id="art_5"]`).

## Pliki

| Plik | Akt | CELEX | Rozmiar |
|---|---|---|---|
| `raw/32024R1689.html` | AI Act (Rozporządzenie 2024/1689) | `32024R1689` | ~1,34 MB |
| `raw/12012P_TXT.html` | Karta Praw Podstawowych UE | `12012P/TXT` | ~42 kB |
| `raw/32016R0679.html` | RODO (Rozporządzenie 2016/679) | `32016R0679` | ~843 kB |

Dla każdego pliku istnieje `{CELEX}.meta.json` z proweniencją: `celex`, `eli`, `zrodlo_url`, `data_pobrania`, `data_weryfikacji`, `sha256`, `rozmiar_bajtow`.

## Dwa katalogi

- **`raw/`** — volatile, nie commitowany. Tu trafia świeży download przy starcie kontenera `api` albo po ręcznym uruchomieniu skryptu.
- **`fallback/`** — snapshot commitowany do repo, używany offline albo gdy EUR-Lex chwilowo niedostępne.

## Odświeżenie

```bash
python scripts/refresh_sources.py
```

Skrypt pobiera HTML z EUR-Lex, liczy sha256, zapisuje do `raw/` + `meta.json`, a na koniec synchronizuje `fallback/ ← raw/`. Commituj `fallback/` w razie potrzeby.
