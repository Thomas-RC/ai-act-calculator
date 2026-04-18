"""FastAPI entrypoint — endpointy: /api/health, /api/meta, /api/classify.

Przepływ /api/classify:
  1. Walidacja ankiety (pydantic).
  2. classifier.classify() → WynikKlasyfikacji.
  3. Jeśli short_circuit (NIEDOPUSZCZALNY) — zwracamy bez LLM.
  4. W przeciwnym razie: legal.build_prompt_corpus() + Gemini (VertexClient).
  5. Merge → OdpowiedzKlasyfikacji.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from classifier import classify
from config import Settings, get_settings
from legal import Corpus
from prompts import RESPONSE_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from report import render_pdf
from schemas import (
    Ankieta,
    MetaZrodla,
    OdpowiedzKlasyfikacji,
    RaportRequest,
    WynikAnalizaLLM,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


# --- stan aplikacji ---

class Stan:
    corpus: Corpus | None = None
    settings: Settings | None = None
    vertex: object | None = None  # VertexClient, lazy import


STAN = Stan()


@asynccontextmanager
async def lifespan(app: FastAPI):
    STAN.settings = get_settings()
    STAN.settings.validate_region_eog()
    log.info("Ładuję korpus prawny z %s", STAN.settings.legal_sources_dir)
    STAN.corpus = Corpus.load(STAN.settings.legal_sources_dir)
    log.info("Korpus załadowany z katalogu '%s', artykułów: %d",
             STAN.corpus.source, len(STAN.corpus.refs()))
    # Vertex client init lazy — dopiero przy pierwszym /api/classify z LLM-em
    yield
    log.info("Zamykam aplikację.")


app = FastAPI(
    title="Kalkulator ryzyka AI Act",
    description="Klasyfikator systemów AI pod kątem Rozporządzenia 2024/1689 (AI Act).",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — w docker-compose nginx proxuje /api/, więc frontend wali same-origin.
# Tu CORS jest dla testów (np. wywołanie /api bezpośrednio).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Endpointy ---

@app.get("/api/health")
def health():
    assert STAN.corpus and STAN.settings
    return {
        "status": "ok",
        "corpus_source": STAN.corpus.source,
        "corpus_articles": len(STAN.corpus.refs()),
        "vertex_location": STAN.settings.vertex_location,
        "vertex_project": STAN.settings.vertex_project_id,
        "model": STAN.settings.model_name,
    }


@app.get("/api/meta", response_model=list[MetaZrodla])
def meta():
    """Proweniencja wszystkich aktów prawnych w korpusie (dla stopki PDF i UI)."""
    assert STAN.corpus
    return [
        MetaZrodla(
            celex=m.celex,
            akt=m.akt,
            eli=m.eli,
            data_pobrania=m.data_pobrania,
            data_weryfikacji=m.data_weryfikacji,
            sha256=m.sha256,
        )
        for m in STAN.corpus.metas.values()
    ]


def _get_vertex():
    if STAN.vertex is None:
        from vertex_client import VertexClient
        STAN.vertex = VertexClient.from_settings(STAN.settings)
    return STAN.vertex


@app.post("/api/classify", response_model=OdpowiedzKlasyfikacji)
def endpoint_classify(ankieta: Ankieta) -> OdpowiedzKlasyfikacji:
    assert STAN.corpus and STAN.settings

    # Etap 1 — deterministyczna klasyfikacja
    wynik_reguly = classify(ankieta)
    log.info("Klasyfikacja: %s (short_circuit=%s)",
             wynik_reguly.kategoria.value, wynik_reguly.short_circuit)

    # Etap 2 — jeśli short_circuit, zwróć bez LLM
    wynik_llm: WynikAnalizaLLM | None = None
    if not wynik_reguly.short_circuit:
        # Etap 2a — złóż korpus do promptu
        refs_do_promptu = list(dict.fromkeys(
            wynik_reguly.legal_basis + wynik_reguly.powiazane_artykuly
        ))
        istniejace_refs = [r for r in refs_do_promptu if STAN.corpus.has(r)]
        if len(istniejace_refs) != len(refs_do_promptu):
            brakujace = set(refs_do_promptu) - set(istniejace_refs)
            log.warning("Brak w korpusie: %s (pomijam)", brakujace)

        korpus_blok = STAN.corpus.build_prompt_corpus(istniejace_refs)
        user_prompt = build_user_prompt(ankieta, wynik_reguly, korpus_blok)

        # Etap 2b — wywołanie Gemini
        try:
            vertex = _get_vertex()
            gen = vertex.generate_structured(
                system=SYSTEM_PROMPT,
                user=user_prompt,
                response_schema=RESPONSE_SCHEMA,
            )
            wynik_llm = WynikAnalizaLLM.model_validate(gen.payload)
            log.info("Gemini: prompt_tokens=%s response_tokens=%s",
                     gen.prompt_tokens, gen.response_tokens)
        except Exception as e:
            log.exception("Vertex AI nie zadziałał: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Backend LLM niedostępny: {e}",
            )

    # Etap 3 — merge odpowiedzi
    return OdpowiedzKlasyfikacji(
        kategoria=wynik_reguly.kategoria,
        wynik_reguly=wynik_reguly,
        wynik_llm=wynik_llm,
        korpus_meta=[
            MetaZrodla(
                celex=m.celex, akt=m.akt, eli=m.eli,
                data_pobrania=m.data_pobrania,
                data_weryfikacji=m.data_weryfikacji,
                sha256=m.sha256,
            )
            for m in STAN.corpus.metas.values()
        ],
    )


@app.post("/api/report")
def endpoint_report(req: RaportRequest) -> Response:
    """Generuje PDF raportu na podstawie wyniku klasyfikacji + (opcjonalnie) ankiety."""
    try:
        pdf_bytes = render_pdf(req.odpowiedz, req.ankieta)
    except Exception as e:
        log.exception("Nie udało się wygenerować PDF-a: %s", e)
        raise HTTPException(status_code=500, detail=f"Błąd generacji PDF: {e}")

    filename = f"ai_act_raport_{req.odpowiedz.kategoria.value.lower()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
