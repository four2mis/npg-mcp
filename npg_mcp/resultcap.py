"""MCP-side result cap for read-only tools (``NPG_MAX_RESULT_CHARS``).

Every read/list/get tool answers with a ``{"success": ..., "data": ...}``
envelope. A handful of endpoints legitimately ship payloads far larger than any
agent's context window — the full cloud-provider catalogue (~700 KB), an
unbounded audit-log page, a multi-MB access log, a backup archive — and one such
call can evict everything the agent was working with. This module puts a single
shared ceiling on the serialized size of every read-only tool result.

Contract
--------
* ``NPG_MAX_RESULT_CHARS`` (default ``65536``) is the ceiling on the compact
  JSON serialization of a tool result. Read once at process start, clamped to
  ``[1024, 8000000]``; an unparseable value falls back to the default with a
  warning (same policy as ``NPG_HTTP_TIMEOUT``).
* A result at or under the ceiling is returned **untouched** — the same object,
  byte-identical to the pre-feature behavior. Nothing is reshaped, reordered or
  renamed on that path.
* An over-budget result is reduced **at data boundaries only**:

  1. string values longer than the clamp limit are truncated and marked in
     place (``"... [clamped N chars]"``), with the limit stepped down while the
     payload stays over budget;
  2. trailing items are dropped from the largest arrays first;
  3. only if neither can get under the ceiling (a pathological payload with no
     arrays and no long strings) the whole payload is placed inside one clamped
     string value (``data`` = compact JSON text + marker). That fallback is
     still complete, valid JSON — it never emits a half-written structure.

  Because every reduction rewrites a Python object which is then re-serialized
  by the MCP layer, a client can never receive truncated JSON: no cut ever
  lands mid-structure or mid-string.
* A ``truncated`` object is added next to ``data`` describing what happened:
  ``total_chars`` (the untouched payload's size), ``returned_chars`` (what the
  caller actually got), ``omitted_items`` (trailing array items dropped),
  ``clamped_strings`` (values shortened) and ``hint`` — a retry instruction
  naming the exact narrower parameters this tool really has (``limit``,
  ``offset``, ``sections``, ``lines``) or, when it has none, pointing at
  ``expand``.
* ``expand: bool = False`` is the per-call escape hatch: ``expand=true`` skips
  the cap entirely for that one call and returns the complete payload. It is a
  real tool parameter (declared in each capped tool's signature, so MCP clients
  see it in ``tools/list``) and is popped before the tool body runs, so it is
  never forwarded to the NPG API.
* ``npg_download_log_file`` is exempt: it already carries its own 256 KB cap
  with ``truncated``/``total_bytes``/``returned_bytes``/``hint`` metadata and
  pages through ``npg_view_log_file``.

Which tools are capped
----------------------
The ceiling applies to every tool whose ``readOnlyHint`` annotation is true
(derived in :mod:`npg_mcp.toolsets` from the HTTP verbs each tool body issues),
minus :data:`EXEMPT_TOOLS`. Instrumentation is keyed off the ``expand``
parameter being present in the tool's own signature — one source of truth, no
separate name list to drift: adding ``expand: bool = False`` opts a tool into
the cap, and ``tests/test_result_cap.py`` fails if a read-only tool is missing
it (or if a mutating tool accidentally grows one).
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import os
from typing import Any

logger = logging.getLogger("npg_mcp.resultcap")

# ── Configuration ──────────────────────────────────────────────────────
ENV_VAR = "NPG_MAX_RESULT_CHARS"
DEFAULT_MAX_RESULT_CHARS = 65536
_MIN_MAX_RESULT_CHARS = 1024
_MAX_MAX_RESULT_CHARS = 8_000_000

# Tool-parameter name that lifts the cap for a single call.
EXPAND_PARAM = "expand"
# Envelope key carrying the truncation metadata.
TRUNCATED_KEY = "truncated"
# Attribute stamped on a wrapped tool function so double instrumentation is a
# no-op (``main()`` may be called more than once in tests/embedded runs).
_WRAPPED_ATTR = "__npg_result_capped__"

# Tools that keep their own, already-documented payload cap.
EXEMPT_TOOLS: frozenset[str] = frozenset({"npg_download_log_file"})

# Tools whose ``data`` is an opaque encoded payload (base64 file bytes). Their
# truncation hint must say the shortened payload is not decodable, because a
# clamped base64 blob silently cannot be turned back into a file.
PAYLOAD_TOOLS: frozenset[str] = frozenset(
    {"npg_download_backup", "npg_get_certificate_download"}
)

# Space kept free for the ``truncated`` metadata block (plus JSON punctuation)
# while the payload itself is being shrunk, so the returned result always lands
# under the ceiling with the metadata included.
_META_RESERVE = 512
# Never clamp a string below this many characters — a 64-char prefix still
# identifies the value, and going lower saves nothing on real payloads.
_CLAMP_MIN_CHARS = 64
# Clamp-limit ladder: budget // divisor, stopping at _CLAMP_MIN_CHARS.
_CLAMP_LADDER_DIVISORS = (8, 32, 128)
# Safety bound on the array-trimming loop (each round removes >= 1 item).
_MAX_ARRAY_ROUNDS = 64
# Retry hint length ceiling (kept inside _META_RESERVE).
_MAX_HINT_CHARS = 240


def _parse_max_result_chars(raw: str) -> int:
    """Parse ``NPG_MAX_RESULT_CHARS``; invalid values fall back with a warning."""
    raw = (raw or "").strip()
    if not raw:
        return DEFAULT_MAX_RESULT_CHARS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not an integer, falling back to %s",
            ENV_VAR,
            raw,
            DEFAULT_MAX_RESULT_CHARS,
        )
        return DEFAULT_MAX_RESULT_CHARS
    if value < _MIN_MAX_RESULT_CHARS:
        logger.warning(
            "%s=%r is below the %s-char floor, clamping",
            ENV_VAR,
            raw,
            _MIN_MAX_RESULT_CHARS,
        )
        return _MIN_MAX_RESULT_CHARS
    if value > _MAX_MAX_RESULT_CHARS:
        logger.warning(
            "%s=%r is above the %s-char ceiling, clamping",
            ENV_VAR,
            raw,
            _MAX_MAX_RESULT_CHARS,
        )
        return _MAX_MAX_RESULT_CHARS
    return value


# Read once at process start so the budget cannot change mid-run.
_MAX_RESULT_CHARS: int = _parse_max_result_chars(os.environ.get(ENV_VAR, ""))


def max_result_chars() -> int:
    """Return the configured result ceiling in characters."""
    return _MAX_RESULT_CHARS


# ── Serialization helpers ──────────────────────────────────────────────


def _dumps(value: Any) -> str:
    """Serialize a tool result the way the budget is measured.

    Compact separators and ``default=str`` keep the measurement deterministic
    for values that carry non-JSON scalars (dates, UUID objects) without
    changing what the MCP layer eventually sends. ``ensure_ascii=False`` counts
    real characters rather than escape sequences.
    """
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _size(value: Any) -> int:
    """Character length of *value*'s compact JSON serialization."""
    return len(_dumps(value))


def _clamp_string(value: str, limit: int) -> str:
    """Shorten *value* to *limit* characters and mark the omission in place."""
    return value[:limit] + f"... [clamped {len(value) - limit} chars]"


def _clamp_strings(node: Any, limit: int, counter: dict[str, int]) -> Any:
    """Copy *node*, clamping every string value longer than *limit*.

    Only string VALUES are touched (dictionary keys are left alone — they are
    structural, and a pathologically long key is not a realistic NPG payload).
    Each round rebuilds from the pristine tree, so a marker written by an
    earlier round can never be re-clamped.
    """
    if isinstance(node, str):
        if len(node) > limit:
            counter["clamped"] += 1
            return _clamp_string(node, limit)
        return node
    if isinstance(node, dict):
        return {k: _clamp_strings(v, limit, counter) for k, v in node.items()}
    if isinstance(node, list | tuple):
        return [_clamp_strings(v, limit, counter) for v in node]
    return node


def _collect_arrays(node: Any, out: list[list]) -> None:
    """Collect live references to every array in *node* (in-place trimming)."""
    if isinstance(node, list):
        out.append(node)
        for item in node:
            _collect_arrays(item, out)
    elif isinstance(node, dict):
        for item in node.values():
            _collect_arrays(item, out)


def _trim_arrays(tree: Any, budget: int, stats: dict[str, int]) -> None:
    """Drop trailing items from the largest arrays until *tree* fits *budget*.

    Arrays are trimmed in place (the tree is a private copy). For each array the
    retained prefix is found by binary search using the array's own serialized
    size — a JSON array's contribution to its container is additive, so the
    total only needs to be measured once per round instead of per candidate.
    """
    total = _size(tree)
    for _ in range(_MAX_ARRAY_ROUNDS):
        if total <= budget:
            return
        arrays: list[list] = []
        _collect_arrays(tree, arrays)
        non_empty = [arr for arr in arrays if arr]
        if not non_empty:
            return
        target = max(non_empty, key=_size)
        arr_size = _size(target)
        count = len(target)
        need = total - budget
        # Smallest drop ``d`` in [1, count] whose retained prefix is small
        # enough. ``count`` always satisfies the bound (an empty array costs 2).
        low, high = 1, count
        while low < high:
            mid = (low + high) // 2
            if _size(target[: count - mid]) <= arr_size - need:
                high = mid
            else:
                low = mid + 1
        drop = low
        del target[count - drop :]
        total -= arr_size - _size(target)
        stats["omitted"] += drop


def _last_resort(tree: Any, budget: int) -> dict:
    """Whole-payload fallback: keep the JSON, but as one clamped string value.

    Reached only by payloads that carry no arrays and no oversized strings yet
    still exceed the ceiling (thousands of distinct keys). The result is still a
    complete, parseable JSON document — the payload text lives in ``data`` as a
    single string value, so nothing is ever cut mid-structure.

    The retained prefix is found by binary search on the *serialized* envelope:
    embedding JSON text inside a JSON string escapes every quote, so the
    escaped size — not the raw text length — is what has to fit.
    """
    text = _dumps(tree)
    if _size({"success": True, "data": text}) <= budget:
        return tree
    success = tree.get("success", True) if isinstance(tree, dict) else True

    def envelope_for(keep: int) -> dict:
        return {"success": success, "data": _clamp_string(text, keep)}

    low, high = _CLAMP_MIN_CHARS, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if _size(envelope_for(mid)) <= budget:
            low = mid
        else:
            high = mid - 1
    return envelope_for(low)


def _shrink(
    result: Any,
    budget: int,
    params: frozenset[str],
) -> tuple[Any, dict[str, int]]:
    """Reduce *result* to at most *budget* chars at data boundaries only."""
    stats = {"omitted": 0, "clamped": 0}
    tree: Any = result
    for divisor in _CLAMP_LADDER_DIVISORS:
        clamp_limit = max(_CLAMP_MIN_CHARS, budget // divisor)
        counter = {"clamped": 0}
        tree = _clamp_strings(result, clamp_limit, counter)
        stats["clamped"] = counter["clamped"]
        if _size(tree) <= budget:
            return tree, stats

    if _size(tree) > budget:
        _trim_arrays(tree, budget, stats)
    if _size(tree) > budget:
        tree = _last_resort(tree, budget)
    return tree, stats



def _retry_hint(tool_name: str, params: frozenset[str], limit: int) -> str:
    """Build the retry hint, naming only parameters the tool actually has."""
    if tool_name in PAYLOAD_TOOLS:
        lead = (
            "The shortened payload cannot be decoded — pass expand=true to "
            "fetch the whole file."
        )
    else:
        advice = []
        if "sections" in params:
            advice.append("fewer sections")
        if "limit" in params and "offset" in params:
            advice.append("a smaller limit and step through the rest with offset")
        elif "limit" in params:
            advice.append("a smaller limit")
        elif "offset" in params:
            advice.append("a larger offset")
        if "lines" in params:
            advice.append("fewer lines")
        if advice:
            lead = "Re-call with " + " / ".join(advice) + "."
        else:
            lead = "This tool has no paging parameters — request a narrower resource."
    hint = (
        f"Result truncated at the {limit}-char cap ({ENV_VAR}). {lead} "
        "expand=true lifts the cap for one call."
    )
    return hint[:_MAX_HINT_CHARS]


def cap_result(
    result: Any,
    *,
    tool_name: str = "",
    params: frozenset[str] = frozenset(),
    limit: int | None = None,
) -> Any:
    """Apply the shared result ceiling to one tool result.

    Returns *result* unchanged (same object) when it is already within budget —
    callers that fit keep byte-identical output. Otherwise returns an envelope
    of the same shape with the payload reduced at data boundaries and a
    ``truncated`` metadata object added.
    """
    ceiling = max_result_chars() if limit is None else limit
    total = _size(result)
    if total <= ceiling:
        return result

    hint = _retry_hint(tool_name, params, ceiling)
    budget = ceiling - _META_RESERVE
    envelope: dict[str, Any] | None = None
    size = 0
    for _ in range(3):
        tree, stats = _shrink(result, budget, params)
        meta: dict[str, Any] = {
            "total_chars": total,
            "returned_chars": 0,
            "omitted_items": stats["omitted"],
            "clamped_strings": stats["clamped"],
            "hint": hint,
        }
        if isinstance(tree, dict):
            envelope = dict(tree)
            envelope[TRUNCATED_KEY] = meta
        else:
            envelope = {"success": True, "data": tree, TRUNCATED_KEY: meta}

        # returned_chars describes the whole returned result (metadata
        # included), so converge on a fixed point — only the digit count moves.
        for _ in range(4):
            size = _size(envelope)
            if meta["returned_chars"] == size:
                break
            meta["returned_chars"] = size
        if size <= ceiling:
            return envelope
        # Escaping inside clamped strings can cost more than the reserve: shrink
        # again with the measured overshoot included.
        budget -= size - ceiling + 32
        if budget <= _CLAMP_MIN_CHARS:
            break
    return envelope if envelope is not None else result


# ── Tool instrumentation ───────────────────────────────────────────────


def _wrap(fn, tool_name: str, params: frozenset[str]):
    """Wrap an async tool function so its result passes through the cap."""

    @functools.wraps(fn)
    async def capped(*args, **kwargs):
        expand = bool(kwargs.pop(EXPAND_PARAM, False))
        result = await fn(*args, **kwargs)
        if expand:
            return result
        return cap_result(result, tool_name=tool_name, params=params)

    setattr(capped, _WRAPPED_ATTR, True)
    return capped


def instrument_tools(mcp) -> int:
    """Apply the result cap to every tool that declares ``expand``.

    Called once from ``main()`` right after :func:`npg_mcp.toolsets.annotate_tools`.
    Mutating the FastMCP ``Tool`` object's ``fn`` is enough: argument validation
    still runs against the original signature (``expand`` is a declared
    parameter), and the wrapper pops it before the tool body executes.

    Returns the number of tools capped. Never raises: a tool that cannot be
    instrumented is logged and left uncapped.
    """
    try:
        registered = mcp._tool_manager.list_tools()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("resultcap: cannot list tools to instrument: %s", exc)
        return 0

    applied = 0
    skipped_exempt: list[str] = []
    for tool in registered:
        try:
            signature = inspect.signature(tool.fn)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            logger.warning("resultcap: cannot inspect %r: %s", tool.name, exc)
            continue
        if EXPAND_PARAM not in signature.parameters:
            continue
        if tool.name in EXEMPT_TOOLS:
            skipped_exempt.append(tool.name)
            continue
        if getattr(tool.fn, _WRAPPED_ATTR, False):
            continue
        params = frozenset(signature.parameters) - {EXPAND_PARAM}
        try:
            tool.fn = _wrap(tool.fn, tool.name, params)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("resultcap: cannot instrument %r: %s", tool.name, exc)
            continue
        applied += 1

    logger.info(
        "resultcap: capped %d tool results at %d chars",
        applied,
        max_result_chars(),
    )
    if skipped_exempt:
        logger.info(
            "resultcap: %d tool(s) keep their own payload cap: %s",
            len(skipped_exempt),
            ", ".join(sorted(skipped_exempt)),
        )
    return applied
