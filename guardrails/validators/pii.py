"""
PIIValidator — detects PII in PT-BR text using two complementary layers:

Layer 1 — Regex + checksum (fast, deterministic)
    CPF (formatted + raw, Módulo 11), CNPJ (checksum), cartão (Luhn),
    telefone (PT-BR DDD formats), email.

Layer 2 — Presidio + spaCy pt_core_news_sm (NER, ~50ms extra)
    PERSON (person names), LOCATION (addresses, cities).
    Only runs when Layer 1 passes to avoid wasted latency on already-blocked inputs.
    Gracefully disabled if presidio-analyzer or the spaCy model is not installed.

`details` keys populated by `run()`:
- `entities`: dict mapping entity type → list of (start, end) span tuples
- `stage`: "input" or "output"
- `patterns_checked`: regex pattern names checked
- `presidio_enabled`: bool — whether Presidio layer was active
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping

from guardrails._pii_patterns import CHECKSUM_VALIDATORS, COMPILED_PII, PII_PATTERNS
from guardrails.validators.base import ValidatorResult

# cpf_raw is an implementation detail; surface it as "cpf" to callers
_ALIAS: dict[str, str] = {"cpf_raw": "cpf"}

# Presidio entity types we care about (NER-only — everything else is handled by regex)
_PRESIDIO_ENTITIES = ["PERSON", "LOCATION"]
_PRESIDIO_LANG = "pt"
_PRESIDIO_MIN_SCORE = 0.85  # spaCy pt_core_news_sm returns ~0.85 for everything

# spaCy pt_core_news_sm is notoriously noisy with false positives on common words.
# We maintain a deny-list of lower-cased tokens that should NEVER be treated as PII,
# even if Presidio tags them as PERSON or LOCATION.
# spaCy pt_core_news_sm has ~40% false-positive rate on PT-BR text.
# We maintain a comprehensive deny-list of tokens that must NEVER be
# treated as PII. This covers common words, banking terms, and frequent
# false positives observed in production.
_PRESIDIO_DENYLIST = {
    # ── banking / product terms ──
    "cartão",
    "gold",
    "cDB",
    "cdb",
    "poupanca",
    "poupança",
    "investimento",
    "renda",
    "juros",
    "taxa",
    "anuidade",
    "limite",
    "beneficio",
    "benefício",
    "pontos",
    "milhas",
    "cashback",
    "fatura",
    "banco",
    "seguro",
    "conta",
    "corrente",
    "saldo",
    "transferencia",
    "transferência",
    "ted",
    "doc",
    "pix",
    "emprestimo",
    "empréstimo",
    "financiamento",
    "consignado",
    "cheque",
    "aplicação",
    "aplicacao",
    "resgate",
    "rentabilidade",
    "prazo",
    "vencimento",
    "cliente",
    "gerente",
    "assessor",
    "atendimento",
    "ouvidoria",
    "sac",
    "agência",
    "agencia",
    "caixa",
    "atm",
    "app",
    "internet",
    "banking",
    "corretora",
    "corretor",
    "administradora",
    "administrador",
    "fundos",
    "fundo",
    "ações",
    "ação",
    "titulos",
    "título",
    "debentures",
    "cri",
    "cra",
    "lf",
    "lc",
    "cp",
    "cdi",
    "ipca",
    "selic",
    "prefixado",
    "pós-fixado",
    "pos-fixado",
    "multimercado",
    "cambial",
    "exterior",
    "previdencia",
    "previdência",
    "vida",
    "morte",
    "invalidez",
    "acidente",
    "residencial",
    "veicular",
    "empresarial",
    "rural",
    "agrícola",
    # ── common verbs / auxiliaries ──
    "ser",
    "estar",
    "ter",
    "haver",
    "fazer",
    "dar",
    "ir",
    "vir",
    "ver",
    "saber",
    "querer",
    "poder",
    "dever",
    "passar",
    "falar",
    "dizer",
    "ficar",
    "achar",
    "parecer",
    "continuar",
    "voltar",
    "entrar",
    "sair",
    "tomar",
    "colocar",
    "encontrar",
    "permanecer",
    "sentir",
    "ouvir",
    "conseguir",
    "receber",
    "mandar",
    "escrever",
    "ler",
    "abrir",
    "fechar",
    "começar",
    "terminar",
    "acabar",
    "existir",
    "trazer",
    "levar",
    "conhecer",
    "pensar",
    "acreditar",
    "esperar",
    "precisar",
    "gostar",
    "amar",
    "odiar",
    "preferir",
    "evitar",
    "tentar",
    "conseguir",
    # ── common words / stopwords ──
    "ignore",
    "previous",
    "instructions",
    "tell",
    "system",
    "prompt",
    "como",
    "funciona",
    "melhor",
    "mercado",
    "qual",
    "oi",
    "olá",
    "ola",
    "bom",
    "dia",
    "boa",
    "noite",
    "tarde",
    "obrigado",
    "obrigada",
    "por",
    "favor",
    "ajuda",
    "ajudar",
    "dúvida",
    "duvida",
    "pergunta",
    "resposta",
    "sim",
    "não",
    "nao",
    "talvez",
    "pode",
    "poderia",
    "gostaria",
    "quero",
    "queria",
    "preciso",
    "muito",
    "bem",
    "mal",
    "mais",
    "menos",
    "aqui",
    "ai",
    "aí",
    "la",
    "lá",
    "onde",
    "quando",
    "porque",
    "porquê",
    "pois",
    "mas",
    "porém",
    "porem",
    "então",
    "entao",
    "assim",
    "também",
    "tambem",
    "já",
    "ja",
    "ainda",
    "sempre",
    "nunca",
    "talvez",
    "agora",
    "hoje",
    "amanhã",
    "ontem",
    "depois",
    "antes",
    "durante",
    "entre",
    "sobre",
    "sob",
    "acima",
    "abaixo",
    "dentro",
    "fora",
    "atrás",
    "frente",
    "mesmo",
    "mesma",
    "outro",
    "outra",
    "outros",
    "outras",
    "todos",
    "todas",
    "algum",
    "alguns",
    "nenhum",
    "nenhuns",
    "todo",
    "toda",
    "nada",
    "algo",
    "alguém",
    "ninguém",
    "tudo",
    "este",
    "esta",
    "estes",
    "estas",
    "esse",
    "essa",
    "esses",
    "essas",
    "aquele",
    "aquela",
    "aqueles",
    "aquelas",
    "isto",
    "isso",
    "aquilo",
    "meu",
    "minha",
    "meus",
    "minhas",
    "teu",
    "tua",
    "teus",
    "tuas",
    "seu",
    "sua",
    "seus",
    "suas",
    "nosso",
    "nossa",
    "nossos",
    "nossas",
    "dele",
    "dela",
    "deles",
    "delas",
    "me",
    "mim",
    "comigo",
    "te",
    "ti",
    "contigo",
    "se",
    "si",
    "consigo",
    "nos",
    "conosco",
    "vos",
    "convosco",
    "lhe",
    "lhes",
    "o",
    "a",
    "os",
    "as",
    "lo",
    "la",
    # ── output-specific false positives ──
    "fico",
    "fica",
    "ficam",
    "ficou",
    "ficaram",
    "ficando",
    "propriedade",
    "nossos",
    "nossas",
    "sobre",
    "produtos",
    "informações",
    "informacoes",
    "detalhes",
    "condições",
    "condicoes",
    "características",
    "caracteristicas",
    "benefícios",
    "beneficios",
    "vantagens",
    "desvantagens",
    "recomendo",
    "recomendamos",
    "sugiro",
    "sugerimos",
    "aconselho",
    "aconselhamos",
    # ── location-like false positives ──
    "rua",
    "avenida",
    "av",
    "travessa",
    "estrada",
    "rodovia",
    "br",
    "sp",
    "rj",
}

logger = logging.getLogger(__name__)


def _build_presidio_engine():
    """Build a Presidio AnalyzerEngine configured for PT-BR with spaCy.

    Returns None (with a warning) if presidio-analyzer or pt_core_news_sm is missing.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError:
        logger.warning("presidio-analyzer not installed — NER-based PII detection (PERSON, LOCATION) disabled")
        return None

    try:
        config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": _PRESIDIO_LANG, "model_name": "pt_core_news_sm"}],
        }
        provider = NlpEngineProvider(nlp_configuration=config)
        engine = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            supported_languages=[_PRESIDIO_LANG],
        )
        return engine
    except OSError:
        logger.warning("spaCy model 'pt_core_news_sm' not found — run: python -m spacy download pt_core_news_sm. NER-based PII detection (PERSON, LOCATION) disabled.")
        return None


class PIIValidator:
    name = "pii"

    def __init__(self, stage: str = "input", presidio_engine=None) -> None:
        """
        Args:
            stage: "input" or "output".
            presidio_engine: pre-built AnalyzerEngine instance (shared across
                validators to avoid loading the spaCy model twice). Pass None to
                build a new engine; pass False to disable Presidio entirely.
        """
        if stage not in {"input", "output"}:
            raise ValueError(f"stage must be 'input' or 'output', got {stage!r}")
        self.stage = stage

        if presidio_engine is False:
            self._presidio = None
        elif presidio_engine is None:
            self._presidio = _build_presidio_engine()
        else:
            self._presidio = presidio_engine

    def run(self, text: str, context: Mapping[str, Any] | None = None) -> ValidatorResult:
        t0 = time.perf_counter()
        entities: dict[str, list[tuple[int, int]]] = {}

        # ── Layer 1: regex + checksum ─────────────────────────────────────
        for entity_type, pattern in COMPILED_PII.items():
            raw_spans = [m.span() for m in pattern.finditer(text)]
            if not raw_spans:
                continue

            checksum = CHECKSUM_VALIDATORS.get(entity_type)
            valid_spans = [s for s in raw_spans if checksum(text[s[0] : s[1]])] if checksum else raw_spans
            if not valid_spans:
                continue

            canonical = _ALIAS.get(entity_type, entity_type)
            entities.setdefault(canonical, []).extend(valid_spans)

        # ── Layer 2: Presidio NER (PERSON, LOCATION) ──────────────────────
        # Only run on INPUT. Output guard uses regex only (Layer 1) because:
        #   - Regex catches the critical PII (CPF, card, email, phone)
        #   - spaCy pt_core_news_sm is EXTREMELY noisy on LLM-generated text
        #   - Names/addresses in user input ARE sensitive and must be caught
        if self.stage == "input" and self._presidio and not entities:
            # Only run if Layer 1 found nothing — avoids latency on already-blocked inputs
            try:
                results = self._presidio.analyze(
                    text=text,
                    entities=_PRESIDIO_ENTITIES,
                    language=_PRESIDIO_LANG,
                )
                for r in results:
                    if r.score < _PRESIDIO_MIN_SCORE:
                        continue
                    matched_text = text[r.start : r.end]
                    # Check if any token in the matched text is on the deny-list.
                    # spaCy often groups tokens (e.g. "Cartão Gold" as LOCATION);
                    # if ANY word in the group is a known false-positive, skip it.
                    tokens = {t.lower().strip(".,;:!?*-_") for t in matched_text.split()}
                    if tokens & _PRESIDIO_DENYLIST:
                        continue
                    entities.setdefault(r.entity_type.lower(), []).append((r.start, r.end))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Presidio analysis failed: %s", exc)

        passed = not entities
        first_entity = next(iter(entities), None) if entities else None

        return ValidatorResult(
            passed=passed,
            category=f"pii_{self.stage}",
            score=None,
            details={
                "rule_violated": first_entity,
                "entities": entities,
                "stage": self.stage,
                "patterns_checked": list(PII_PATTERNS.keys()),
                "presidio_enabled": self._presidio is not None,
            },
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
