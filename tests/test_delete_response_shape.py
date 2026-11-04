"""Structural guard: the delete family answers with a message, not ``data: null``.

``NPGClient.delete()`` returns ``None`` for a 204 No Content response. A delete
tool that hands that raw result to ``{"success": True, "data": data}`` therefore
ships ``{"success": True, "data": null}`` — indistinguishable from "nothing
happened" and inconsistent with every other delete tool. The regression has
shipped three times (``npg_delete_proxy_host_geo`` and
``npg_delete_proxy_host_challenge`` in 2026-08, ``npg_end_user_sessions`` in
commit 01af82b), and each occurrence was invisible to the NPG API and to
transport-level checks: only the live body of the tool reveals it.

The contract pinned here: a delete-family tool (one whose only client verb is
``delete``) returns ``_mutate_result(data, "<message>")``. Exactly one bulk tool
returns per-host result rows by design and is listed in
``_PER_HOST_DELETE_RESULTS`` — that exemption is itself asserted, so a stale
entry fails instead of silently widening the hole.

Pure AST test — no MCP server, no network, no test stack.
"""

from __future__ import annotations

import ast
from pathlib import Path

from npg_mcp.toolsets import _tool_verbs

_MAIN_PY = Path(__file__).resolve().parents[1] / "npg_mcp" / "main.py"

# Delete tools that intentionally return per-host result rows instead of one
# message. ``npg_bulk_delete_proxy_hosts`` answers
# ``{"success": True, "data": [{"host_id", "success", "result"/"error"}, ...]}``
# — one entry per requested host — so a single message string cannot represent
# its outcome. Every other delete-family tool must pass a message.
_PER_HOST_DELETE_RESULTS = frozenset({"npg_bulk_delete_proxy_hosts"})

# Vacuity guard: a broken verb harvest or decorator parser that selects no
# tools must fail loudly rather than let the shape assertion pass on an empty
# set. The delete family has held >= 30 members since 2026-08.
_MIN_DELETE_FAMILY = 30

_FUNC_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _tool_functions() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Index top-level functions by the ``name=`` of their ``@mcp.tool`` decorator.

    Parsed independently of ``npg_mcp.toolsets`` so that a bug in the shared
    decorator parser surfaces as a mismatch between the two indexes instead of
    hiding a tool from both.
    """
    tree = ast.parse(_MAIN_PY.read_text(encoding="utf-8"))
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if not isinstance(node, _FUNC_NODES):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (isinstance(func, ast.Attribute) and func.attr == "tool"):
                continue
            for keyword in decorator.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                    if isinstance(keyword.value.value, str):
                        functions[keyword.value.value] = node
    return functions


def _delete_family() -> list[str]:
    """Registered tool names whose only harvested client verb is ``delete``."""
    verbs = _tool_verbs()
    return sorted(name for name, used in verbs.items() if used == frozenset({"delete"}))


def _mutate_calls(node: ast.AST) -> list[ast.Call]:
    """Every ``_mutate_result(...)`` call inside *node*."""
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_mutate_result"
    ]


def _message_argument(call: ast.Call) -> ast.expr | None:
    """The message argument of a ``_mutate_result(...)`` call, if supplied.

    ``_mutate_result(data, message)`` takes it positionally in every tool, but
    the keyword form is accepted too so a future ``message=`` call site is not
    misreported as missing.
    """
    if len(call.args) > 1:
        return call.args[1]
    for keyword in call.keywords:
        if keyword.arg == "message":
            return keyword.value
    return None


def _rejects_message(argument: ast.expr | None) -> str | None:
    """Why *argument* is not a usable message, or ``None`` when it is fine."""
    if argument is None:
        return "no message argument (a 204 response would surface as data: null)"
    if isinstance(argument, ast.Constant) and argument.value is None:
        return "message argument is the None literal"
    if isinstance(argument, ast.Constant) and argument.value == "":
        return "message argument is the empty string"
    return None


def _data_envelopes(node: ast.AST) -> list[str]:
    """Return statements in *node* that build a raw ``{"...": ..., "data": ...}``."""
    found: list[str] = []
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Return):
            continue
        value = statement.value
        if not isinstance(value, ast.Dict):
            continue
        keys = {
            key.value
            for key in value.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        if "data" in keys:
            found.append(f"line {statement.lineno}: {sorted(keys)}")
    return found


def test_delete_family_selector_is_populated() -> None:
    """The selector must find a real delete family, and both parsers must agree."""
    verbs = _tool_verbs()
    assert len(verbs) >= 100, (
        f"the verb harvest returned only {len(verbs)} tools — the AST parse of "
        f"npg_mcp/main.py is broken and the delete-shape guard would pass vacuously"
    )

    delete_family = _delete_family()
    assert len(delete_family) >= _MIN_DELETE_FAMILY, (
        f"found only {len(delete_family)} tools whose only verb is 'delete' "
        f"(expected >= {_MIN_DELETE_FAMILY}) — the verb harvest regressed: "
        f"{delete_family}"
    )

    functions = _tool_functions()
    assert set(functions) == set(verbs), (
        "the local decorator parser and toolsets._tool_verbs() disagree about the "
        f"registered tool surface: only-local={sorted(set(functions) - set(verbs))} "
        f"only-toolsets={sorted(set(verbs) - set(functions))}"
    )


def test_every_delete_tool_passes_a_message() -> None:
    """Every delete-family tool must pass a non-None message to ``_mutate_result``."""
    functions = _tool_functions()
    offenders: list[str] = []

    for name in _delete_family():
        if name in _PER_HOST_DELETE_RESULTS:
            continue
        node = functions.get(name)
        if node is None:
            offenders.append(
                f"{name}: no top-level function with an @mcp.tool(name=...) decorator"
            )
            continue
        calls = _mutate_calls(node)
        if not calls:
            offenders.append(
                f"{name}: no _mutate_result(data, <message>) call — a raw "
                f'{{"success": True, "data": data}} return surfaces data: null '
                f"for a 204 delete"
            )
            continue
        for call in calls:
            reason = _rejects_message(_message_argument(call))
            if reason is not None:
                offenders.append(f"{name}: line {call.lineno}: {reason}")

    assert not offenders, (
        "delete-family response shape violated — every tool whose only client verb "
        "is 'delete' must return a message (see _mutate_result in npg_mcp/main.py). "
        "Offenders:\n  " + "\n  ".join(offenders)
    )


def test_delete_tools_do_not_return_a_raw_data_envelope() -> None:
    """No unexempted delete tool may build a raw ``{"success": ..., "data": ...}``."""
    functions = _tool_functions()
    offenders: list[str] = []

    for name in _delete_family():
        if name in _PER_HOST_DELETE_RESULTS:
            continue
        node = functions.get(name)
        if node is None:  # already reported by the message test
            continue
        for location in _data_envelopes(node):
            offenders.append(f"{name}: {location}")

    assert not offenders, (
        "a delete tool builds a raw data envelope; route it through "
        "_mutate_result(data, message) so a 204 cannot surface as data: null. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )


def test_per_host_delete_allowlist_is_accurate() -> None:
    """The exemption list must stay narrow: real, delete-only, still returning rows."""
    functions = _tool_functions()
    verbs = _tool_verbs()

    for name in sorted(_PER_HOST_DELETE_RESULTS):
        assert name in verbs, (
            f"{name} is in _PER_HOST_DELETE_RESULTS but is not a registered tool — "
            f"remove the stale allowlist entry"
        )
        assert verbs[name] == frozenset({"delete"}), (
            f"{name} is allowlisted as a per-host delete tool but its harvested verbs "
            f"are {sorted(verbs[name])}"
        )
        node = functions.get(name)
        assert node is not None, f"{name} has no parseable @mcp.tool function body"
        envelopes = _data_envelopes(node)
        assert envelopes, (
            f"{name} no longer returns a per-host data envelope "
            f"({envelopes}) — if it now returns a message, drop it from "
            f"_PER_HOST_DELETE_RESULTS"
        )
