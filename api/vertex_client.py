"""Klient Vertex AI (Gemini) z wymuszonym regionem EOG i strukturalnym outputem JSON.

Zakres odpowiedzialności:
  - Inicjalizacja vertexai SDK z credentials z GOOGLE_APPLICATION_CREDENTIALS.
  - Weryfikacja, że location mieści się w EOG (patrz config.REGIONY_EOG).
  - Wywołanie Gemini z system+user prompt i response_schema → dict.
  - NIE: decyduje o kategorii ryzyka (to robi classifier.py).
  - NIE: przechowuje danych użytkownika (stateless).

Użycie:
    client = VertexClient.from_settings()
    result = client.generate_structured(
        system="Jesteś audytorem AI Act…",
        user="Klasyfikacja: WYSOKIE RYZYKO\\n\\nKorpus: …",
        response_schema=SCHEMA_WYNIK_KLASYFIKACJI,
    )
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from config import Settings, get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    payload: dict[str, Any]
    model_name: str
    prompt_tokens: int | None = None
    response_tokens: int | None = None


class VertexClient:
    def __init__(self, project: str, location: str, model_name: str):
        # Lazy import — vertexai jest ciężki i niepotrzebny przy samych testach corpus/classifier
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project, location=location)
        self._model_name = model_name
        self._model = GenerativeModel(model_name)
        log.info("VertexClient zainicjalizowany: project=%s location=%s model=%s",
                 project, location, model_name)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "VertexClient":
        s = settings or get_settings()
        s.validate_region_eog()
        return cls(
            project=s.vertex_project_id,
            location=s.vertex_location,
            model_name=s.model_name,
        )

    def generate_structured(
        self,
        system: str,
        user: str,
        response_schema: dict[str, Any],
        temperature: float = 0.2,
        max_output_tokens: int = 8192,
    ) -> GenerationResult:
        """Wywołuje Gemini z wymuszonym JSON-owym outputem wg response_schema."""
        from vertexai.generative_models import GenerationConfig, Part

        config = GenerationConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        # Vertex AI SDK łączy system instruction na poziomie modelu; prostszy wariant
        # to podać wszystko jako jeden prompt z sekcjami.
        prompt = f"{system}\n\n---\n\n{user}"
        response = self._model.generate_content(
            [Part.from_text(prompt)],
            generation_config=config,
        )

        tekst = response.text or ""
        try:
            payload = json.loads(tekst)
        except json.JSONDecodeError as e:
            log.error("Gemini zwrócił nie-JSON: %s", tekst[:500])
            raise RuntimeError(f"Gemini nie zwrócił poprawnego JSON: {e}") from e

        usage = getattr(response, "usage_metadata", None)
        return GenerationResult(
            payload=payload,
            model_name=self._model_name,
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            response_tokens=getattr(usage, "candidates_token_count", None),
        )

    def ping(self) -> str:
        """Szybki test połączenia — wysyła minimalny prompt."""
        from vertexai.generative_models import Part
        response = self._model.generate_content([Part.from_text("Odpowiedz jednym słowem: ok")])
        return (response.text or "").strip()
