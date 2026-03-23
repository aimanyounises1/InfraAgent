"""Conversation memory manager for InfraAgent.

Provides in-memory, per-thread conversation history with a configurable
sliding window (``settings.memory_max_turns``). Each turn stores its
role, content, optional metadata, and a UTC timestamp.

Thread storage is module-level (process lifetime). For production
persistence, swap ``_thread_store`` with a database-backed implementation.

All public functions are async-safe and never raise -- invalid thread IDs
return empty results rather than errors.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level storage
# ---------------------------------------------------------------------------

_thread_store: dict[str, list[dict[str, Any]]] = {}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def get_conversation_context(thread_id: str) -> list[dict[str, Any]]:
    """Retrieve the conversation history for a given thread.

    Returns a copy of the turn list so callers cannot accidentally
    mutate the stored data.

    Args:
        thread_id: Unique identifier for the conversation thread.

    Returns:
        A list of turn dicts (each with ``role``, ``content``,
        ``timestamp``, and optionally ``metadata``). Returns an empty
        list if the thread does not exist.
    """
    if not thread_id:
        logger.warning("get_conversation_context called with empty thread_id")
        return []

    turns: list[dict[str, Any]] = _thread_store.get(thread_id, [])
    # Return a shallow copy so the caller cannot mutate internal state
    return list(turns)


async def save_turn(
    thread_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a conversation turn to a thread's history.

    Automatically enforces the sliding window defined by
    ``settings.memory_max_turns``. If the thread does not exist yet
    it is created.

    Args:
        thread_id: Unique identifier for the conversation thread.
        role: The role of the speaker (e.g. ``"user"``, ``"assistant"``).
        content: The textual content of the turn.
        metadata: Optional dict of extra data to attach (e.g. intent,
            tool calls, confidence scores).
    """
    if not thread_id:
        logger.warning("save_turn called with empty thread_id, ignoring")
        return

    if not role:
        logger.warning("save_turn called with empty role for thread=%s, ignoring", thread_id)
        return

    turn: dict[str, Any] = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if metadata:
        turn["metadata"] = metadata

    if thread_id not in _thread_store:
        _thread_store[thread_id] = []

    _thread_store[thread_id].append(turn)

    # Enforce sliding window
    max_turns: int = settings.memory_max_turns
    if max_turns > 0 and len(_thread_store[thread_id]) > max_turns:
        excess: int = len(_thread_store[thread_id]) - max_turns
        _thread_store[thread_id] = _thread_store[thread_id][excess:]
        logger.debug(
            "Thread %s: trimmed %d oldest turn(s), keeping %d",
            thread_id,
            excess,
            max_turns,
        )

    logger.debug(
        "Thread %s: saved %s turn (%d chars), total turns=%d",
        thread_id,
        role,
        len(content),
        len(_thread_store[thread_id]),
    )


async def clear_thread(thread_id: str) -> None:
    """Clear all conversation history for a thread.

    If the thread does not exist, this is a no-op.

    Args:
        thread_id: Unique identifier for the conversation thread.
    """
    if not thread_id:
        logger.warning("clear_thread called with empty thread_id, ignoring")
        return

    if thread_id in _thread_store:
        turn_count: int = len(_thread_store[thread_id])
        del _thread_store[thread_id]
        logger.info("Thread %s: cleared %d turn(s)", thread_id, turn_count)
    else:
        logger.debug("Thread %s: nothing to clear (not found)", thread_id)


def list_threads() -> list[str]:
    """List all active thread IDs that have conversation history.

    Returns:
        A list of thread ID strings. Empty list if no threads exist.
    """
    return list(_thread_store.keys())
