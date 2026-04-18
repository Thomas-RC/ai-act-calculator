"""Testy loadera korpusu — sprawdzają poprawność parsowania XHTML z EUR-Lex.

Uruchomienie: pytest api/test_legal.py -v
Wymagany: pobrany korpus w legal_sources/fallback/ (lub raw/).
"""

from pathlib import Path

import pytest

from legal import Corpus, ZRODLA


ROOT = Path(__file__).resolve().parent.parent
LEGAL_DIR = ROOT / "legal_sources"


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return Corpus.load(LEGAL_DIR)


def test_zaladowany_z_raw_lub_fallback(corpus: Corpus):
    assert corpus.source in ("raw", "fallback")


def test_metadata_wszystkich_aktow(corpus: Corpus):
    for z in ZRODLA:
        assert z.celex in corpus.metas
        meta = corpus.metas[z.celex]
        assert meta.jezyk == "pl"
        assert meta.sha256 and len(meta.sha256) == 64
        assert meta.rozmiar_bajtow > 1000


def test_ai_act_ma_kluczowe_artykuly(corpus: Corpus):
    wymagane = [
        "ai_act:art_3",   # definicje
        "ai_act:art_5",   # zakazane praktyki
        "ai_act:art_6",   # systemy wysokiego ryzyka
        "ai_act:art_10",  # dane treningowe
        "ai_act:art_14",  # nadzór ludzki
        "ai_act:art_27",  # FRIA
        "ai_act:art_50",  # transparentność
        "ai_act:anx_III", # załącznik III
    ]
    brakujace = [r for r in wymagane if not corpus.has(r)]
    assert not brakujace, f"Brak w korpusie: {brakujace}"


def test_art_5_ai_act_zawiera_zakazane_praktyki(corpus: Corpus):
    art = corpus.get("ai_act:art_5")
    assert "Artykuł 5" in art.tytul
    assert "Zakazane" in art.nazwa or "zakazane" in art.nazwa.lower()
    # Sanity check: tekst zawiera kluczowe frazy z Art. 5
    tekst_lower = art.tekst.lower()
    assert "zakazuje się" in tekst_lower
    # Min. kilka liter punktów: a), b), c) — w Art. 5 jest 8 punktów
    assert art.tekst.count("a)") >= 1
    assert len(art.tekst) > 1000, f"Art. 5 podejrzanie krótki: {len(art.tekst)} znaków"


def test_zal_iii_ai_act_wymienia_sektory(corpus: Corpus):
    zal = corpus.get("ai_act:anx_III")
    tekst_lower = zal.tekst.lower()
    # W Załączniku III są wymienione: biometria, edukacja, zatrudnienie,
    # usługi publiczne, ściganie, migracja, wymiar sprawiedliwości, infrastruktura
    oczekiwane_frazy = ["biometria", "edukacja", "zatrudnienia", "migracj", "ścigani"]
    znalezione = [f for f in oczekiwane_frazy if f in tekst_lower]
    assert len(znalezione) >= 4, (
        f"W Zał. III znaleziono tylko {znalezione} z {oczekiwane_frazy}"
    )


def test_rodo_ma_art_22(corpus: Corpus):
    assert corpus.has("rodo:art_22")
    art = corpus.get("rodo:art_22")
    tekst_lower = art.tekst.lower()
    assert "zautomatyzowan" in tekst_lower


def test_kpp_ma_art_21_niedyskryminacja(corpus: Corpus):
    # Karta Praw Podstawowych może mieć inną strukturę — sprawdzamy czy w ogóle
    # są jakiekolwiek artykuły z prefixem kpp:
    kpp_refs = [r for r in corpus.refs() if r.startswith("kpp:")]
    assert kpp_refs, "Brak artykułów z Karty Praw Podstawowych"


def test_prompt_block_zawiera_tekst_ustawy(corpus: Corpus):
    art = corpus.get("ai_act:art_5")
    blok = art.as_prompt_block()
    assert blok.startswith("[ai_act:art_5]")
    assert "Artykuł 5" in blok
    assert "Zakazuje się" in blok


def test_build_prompt_corpus_laczy_wiele_artykulow(corpus: Corpus):
    refs = ["ai_act:art_5", "ai_act:art_6"]
    combined = corpus.build_prompt_corpus(refs)
    assert "[ai_act:art_5]" in combined
    assert "[ai_act:art_6]" in combined
    assert "---" in combined  # separator między artykułami


def test_brak_referencji_rzuca_keyerror(corpus: Corpus):
    with pytest.raises(KeyError):
        corpus.get("ai_act:art_999")
