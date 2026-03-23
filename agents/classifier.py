"""Hybrid LLM + keyword intent classifier for InfraAgent.

Classifies user queries into one or more infrastructure domains
(kubernetes, gpu, incident) with confidence scores. Supports:

1. **Keyword scoring**: Fast, deterministic matching against domain keyword sets.
   Each domain gets a normalized 0.0-1.0 confidence score.
2. **LLM classification** (optional): When ``settings.classification_use_llm``
   is True and an LLM provider is available, uses structured prompting for
   richer classification. Falls back to keyword scoring on any failure.
3. **Context-aware follow-ups**: Short queries that reference prior context
   (pronouns, device indices) inherit intent from conversation history.

The classifier never crashes -- all code paths return a valid
``IntentClassification`` instance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from agents.state import IntentClassification
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain keyword sets
# ---------------------------------------------------------------------------

_KUBERNETES_KEYWORDS: set[str] = {
    "pod",
    "deploy",
    "service",
    "node",
    "namespace",
    "kubectl",
    "kubernetes",
    "k8s",
    "replica",
    "scale",
    "slurm",
    "squeue",
    "srun",
    "sbatch",
    "job queue",
    "partition",
    "cordon",
    "drain",
    "rollout",
    "rollback",
    "hpa",
    "autoscal",
    "configmap",
    "quota",
    "event",
}

_GPU_KEYWORDS: set[str] = {
    "gpu",
    "cuda",
    "nvidia",
    "utilization",
    "vram",
    "temperature",
    "power",
    "dcgm",
    "nvlink",
    "nvswitch",
    "nccl",
    "allreduce",
    "ecc",
    "xid",
    "topology",
    "hbm",
    "dgx",
    "h100",
    "a100",
    "b200",
    "tensor core",
    "interconnect",
    "collective",
    "infiniband",
}

_INCIDENT_KEYWORDS: set[str] = {
    "incident",
    "alert",
    "pagerduty",
    "jira",
    "grafana",
    "rca",
    "outage",
    "ticket",
    "postmortem",
    "correlat",
    "on-call",
    "oncall",
    "escalat",
}

_DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "kubernetes": _KUBERNETES_KEYWORDS,
    "gpu": _GPU_KEYWORDS,
    "incident": _INCIDENT_KEYWORDS,
}

# ---------------------------------------------------------------------------
# Follow-up detection heuristics
# ---------------------------------------------------------------------------

_FOLLOW_UP_PRONOUNS: set[str] = {
    "it",
    "that",
    "this",
    "them",
    "those",
    "these",
    "there",
    "the same",
}

_FOLLOW_UP_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:gpu|device|node|pod|cluster|incident)\s*\d+\b",
    re.IGNORECASE,
)


def _is_follow_up(query: str) -> bool:
    """Determine whether a query looks like a conversational follow-up.

    A query is considered a follow-up if it is short (fewer than 8 words)
    and contains pronouns or indexed references like "GPU 2".

    Args:
        query: The raw user query.

    Returns:
        True if the query appears to be a follow-up to a previous turn.
    """
    words: list[str] = query.split()
    if len(words) > 8:
        return False

    query_lower: str = query.lower()

    # Check for pronoun references
    for pronoun in _FOLLOW_UP_PRONOUNS:
        if pronoun in query_lower:
            return True

    # Check for indexed references like "GPU 2", "node 3"
    return bool(_FOLLOW_UP_PATTERN.search(query))


def _extract_last_intent(conversation_history: list[dict[str, Any]]) -> str | None:
    """Extract the primary intent from the most recent assistant turn.

    Walks backward through conversation history looking for a turn
    with intent metadata attached.

    Args:
        conversation_history: List of conversation turn dicts with at
            least ``role`` and optionally ``metadata`` keys.

    Returns:
        The intent string from the last turn that has one, or None.
    """
    for turn in reversed(conversation_history):
        metadata: dict[str, Any] | None = turn.get("metadata")
        if metadata and metadata.get("intent"):
            return str(metadata["intent"])
    return None


# ---------------------------------------------------------------------------
# Keyword-based scoring
# ---------------------------------------------------------------------------


def _score_keywords(query: str) -> dict[str, float]:
    """Score a query against each domain's keyword set.

    For each domain, counts how many keywords appear in the lowercased
    query, then normalizes by the size of that keyword set to produce
    a 0.0-1.0 confidence score.

    Args:
        query: The raw user query.

    Returns:
        Dict mapping domain name to confidence score (0.0-1.0).
    """
    query_lower: str = query.lower()
    scores: dict[str, float] = {}

    for domain, keywords in _DOMAIN_KEYWORDS.items():
        match_count: int = sum(1 for kw in keywords if kw in query_lower)
        scores[domain] = match_count / len(keywords) if keywords else 0.0

    return scores


def _build_keyword_classification(
    query: str,
    scores: dict[str, float],
    threshold: float,
    reasoning_prefix: str = "Keyword scoring",
) -> IntentClassification:
    """Build an IntentClassification from keyword confidence scores.

    Args:
        query: The original query (for logging/debugging).
        scores: Dict of domain -> confidence from ``_score_keywords``.
        threshold: Minimum confidence to consider a domain a match.
        reasoning_prefix: Prefix for the reasoning string.

    Returns:
        A fully populated IntentClassification instance.
    """
    matching_intents: list[str] = [domain for domain, score in scores.items() if score >= threshold]

    if not matching_intents:
        return IntentClassification(
            intents=[],
            confidence=scores,
            primary_intent="unknown",
            requires_multi_agent=False,
            reasoning=f"{reasoning_prefix}: no domain scored above threshold {threshold}",
        )

    # Sort by score descending, then alphabetically for determinism
    matching_intents.sort(key=lambda d: (-scores[d], d))
    primary: str = matching_intents[0]

    return IntentClassification(
        intents=matching_intents,
        confidence=scores,
        primary_intent=primary,
        requires_multi_agent=len(matching_intents) > 1,
        reasoning=(
            f"{reasoning_prefix}: matched {matching_intents} "
            f"(primary={primary}, confidence={scores[primary]:.2f})"
        ),
    )


# ---------------------------------------------------------------------------
# LLM-based classification
# ---------------------------------------------------------------------------

_LLM_CLASSIFICATION_PROMPT: str = """\
You are an intent classifier for an infrastructure monitoring system.
Classify the user query into one or more of these domains:
- "kubernetes": Kubernetes cluster operations, pods, deployments, services, Slurm HPC
- "gpu": GPU monitoring, CUDA, NVIDIA, DCGM, NVLink, NCCL, thermals, memory, power
- "incident": Incident management, alerts, PagerDuty, Jira, Grafana, RCA, outages

Respond ONLY with valid JSON in this exact format:
{
  "intents": ["<domain1>", "<domain2>"],
  "confidence": {"kubernetes": 0.0, "gpu": 0.0, "incident": 0.0},
  "primary_intent": "<highest confidence domain>",
  "reasoning": "<brief explanation>"
}

Rules:
- confidence values must be between 0.0 and 1.0
- intents list should only include domains with confidence >= 0.3
- if no domain matches, set primary_intent to "unknown" and intents to []
"""


async def _classify_with_llm(
    query: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> IntentClassification | None:
    """Attempt LLM-based classification of the query.

    Sends a structured prompt to the configured LLM provider and parses
    the JSON response into an ``IntentClassification``. Returns None on
    any failure so the caller can fall back to keyword scoring.

    Args:
        query: The user query to classify.
        conversation_history: Optional prior turns for context.

    Returns:
        An IntentClassification if the LLM succeeds, or None on failure.
    """
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from agents.llm_provider import get_llm

        llm = get_llm()
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM classifier: provider unavailable: %s", exc)
        return None

    try:
        messages: list[Any] = [SystemMessage(content=_LLM_CLASSIFICATION_PROMPT)]

        # Include recent conversation history for context
        if conversation_history:
            recent: list[dict[str, Any]] = conversation_history[-4:]
            history_text: str = "\n".join(
                f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in recent
            )
            messages.append(
                HumanMessage(
                    content=(
                        f"Recent conversation context:\n{history_text}\n\n"
                        f"Classify this query: {query}"
                    )
                )
            )
        else:
            messages.append(HumanMessage(content=f"Classify this query: {query}"))

        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=10.0,
        )

        content: str = response.content  # type: ignore[assignment]
        if not content:
            logger.debug("LLM classifier: empty response")
            return None

        # Extract JSON from the response (handle markdown code blocks)
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if not json_match:
            logger.debug("LLM classifier: no JSON found in response")
            return None

        parsed: dict[str, Any] = json.loads(json_match.group())

        # Validate and build classification
        intents: list[str] = parsed.get("intents", [])
        confidence: dict[str, float] = parsed.get("confidence", {})
        primary: str = parsed.get("primary_intent", "unknown")
        reasoning: str = parsed.get("reasoning", "LLM classification")

        # Ensure confidence values are valid floats in [0, 1]
        for domain in ("kubernetes", "gpu", "incident"):
            raw_val = confidence.get(domain, 0.0)
            try:
                confidence[domain] = max(0.0, min(1.0, float(raw_val)))
            except (TypeError, ValueError):
                confidence[domain] = 0.0

        # Validate primary intent
        valid_intents: set[str] = {"kubernetes", "gpu", "incident", "unknown"}
        if primary not in valid_intents:
            primary = "unknown"

        # Filter intents to valid domains
        intents = [i for i in intents if i in {"kubernetes", "gpu", "incident"}]

        return IntentClassification(
            intents=intents,
            confidence=confidence,
            primary_intent=primary,
            requires_multi_agent=len(intents) > 1,
            reasoning=f"LLM classification: {reasoning}",
        )

    except TimeoutError:
        logger.debug("LLM classifier: timed out after 10s")
        return None
    except json.JSONDecodeError as exc:
        logger.debug("LLM classifier: invalid JSON in response: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM classifier: unexpected error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def classify_query(
    query: str,
    conversation_history: list[dict[str, Any]] | None = None,
) -> IntentClassification:
    """Classify a user query into infrastructure domain intents.

    Uses a hybrid approach:
    1. If the query looks like a follow-up and conversation history is
       available, inherits the prior turn's intent.
    2. If ``settings.classification_use_llm`` is True, attempts LLM-based
       classification first.
    3. Falls back to keyword scoring if LLM is unavailable or fails.

    This function never raises -- it always returns a valid
    ``IntentClassification`` instance.

    Args:
        query: The user query to classify.
        conversation_history: Optional list of prior conversation turns,
            each a dict with ``role``, ``content``, and optionally ``metadata``.

    Returns:
        An IntentClassification with intents, confidence scores, and
        primary_intent set.
    """
    if not query or not query.strip():
        logger.warning("classify_query called with empty query")
        return IntentClassification(
            intents=[],
            confidence={"kubernetes": 0.0, "gpu": 0.0, "incident": 0.0},
            primary_intent="unknown",
            requires_multi_agent=False,
            reasoning="Empty query provided",
        )

    threshold: float = settings.classification_confidence_threshold

    # --- Step 1: Context-aware follow-up detection ---
    if conversation_history and _is_follow_up(query):
        prior_intent: str | None = _extract_last_intent(conversation_history)
        if prior_intent and prior_intent in {"kubernetes", "gpu", "incident"}:
            logger.info(
                "Follow-up query detected, inheriting intent=%s from history",
                prior_intent,
            )
            return IntentClassification(
                intents=[prior_intent],
                confidence={prior_intent: 0.8},
                primary_intent=prior_intent,
                requires_multi_agent=False,
                reasoning=(f"Follow-up query: inherited intent '{prior_intent}' from conversation"),
            )

    # --- Step 2: LLM classification (optional) ---
    if settings.classification_use_llm:
        llm_result: IntentClassification | None = await _classify_with_llm(
            query, conversation_history
        )
        if llm_result is not None:
            logger.info(
                "LLM classification succeeded: primary=%s, intents=%s",
                llm_result.primary_intent,
                llm_result.intents,
            )
            return llm_result

    # --- Step 3: Keyword scoring fallback ---
    scores: dict[str, float] = _score_keywords(query)
    classification: IntentClassification = _build_keyword_classification(
        query=query,
        scores=scores,
        threshold=threshold,
        reasoning_prefix="Keyword scoring",
    )

    logger.info(
        "Keyword classification: primary=%s, intents=%s, scores=%s",
        classification.primary_intent,
        classification.intents,
        {k: f"{v:.2f}" for k, v in scores.items()},
    )

    return classification
