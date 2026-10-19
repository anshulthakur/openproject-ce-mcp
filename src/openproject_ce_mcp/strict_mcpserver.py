from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from typing import Any

from mcp import types
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mcp.types import Icon, ToolAnnotations
from pydantic import ConfigDict, ValidationError

from .tool_errors import ToolInputError

logger = logging.getLogger(__name__)


def _non_finite(value: Any) -> bool:
    """True when a number anywhere inside the value is NaN or Infinity (the JSON parser of the
    transport accepts both), which would reach OpenProject as invalid JSON or fail to serialize."""
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_non_finite(item) for item in value.values())
    if isinstance(value, list):
        return any(_non_finite(item) for item in value)
    return False


def _reject_constant(constant: str) -> Any:
    raise ValueError(f"{constant} is not a JSON number")


def _finite_float(text: str) -> float:
    """A literal such as 1e999 is valid JSON but overflows to infinity, which `parse_constant` never sees."""
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"{text} is not a finite number")
    return number


def _admits_container(schema: dict[str, Any]) -> bool:
    if schema.get("type") in ("array", "object") or "$ref" in schema or "allOf" in schema:
        return True
    return any(_admits_container(option) for option in (*schema.get("anyOf", []), *schema.get("oneOf", [])))


class _StrictFuncMetadata(FuncMetadata):
    """FuncMetadata whose JSON-text pre-parse is limited to arguments that may be a list or an object.

    The SDK decodes JSON text for every argument that is not annotated `str`, so a client that
    sends a list as text still works. For a scalar argument that decoding is not wanted: the
    value must arrive with its own type.
    """

    container_fields: frozenset[str] = frozenset()

    def pre_parse_json(self, data: dict[str, Any]) -> dict[str, Any]:
        parsed = dict(data)
        for key, value in data.items():
            if key in self.container_fields and isinstance(value, str):
                try:
                    decoded = json.loads(value, parse_constant=_reject_constant, parse_float=_finite_float)
                except (ValueError, RecursionError):
                    continue
                if isinstance(decoded, list | dict):
                    parsed[key] = decoded
        return parsed


class StrictMCPServer(MCPServer):
    """MCPServer with fail-closed argument validation.

    MCPServer's auto-generated per-tool Pydantic argument models inherit
    ``ArgModelBase``, which sets no ``extra=`` and therefore defaults to
    pydantic's ``extra="ignore"``. An unknown or misnamed keyword argument
    (e.g. ``filters=`` on a tool that only accepts ``version=``) is silently
    dropped before validation ever runs, and the tool executes with defaults
    for the arguments the caller actually meant to set — with no error
    surfaced anywhere. This subclass intercepts the raw arguments dict before
    that drop happens and rejects unknown top-level keys explicitly.

    Instantiate in place of ``MCPServer`` as a matter of discipline, not
    because the SDK strictly requires it under the current (late-bound-
    through-``self``) dispatch wiring: ``MCPServer.__init__`` passes
    ``on_call_tool=self._handle_call_tool`` to the low-level server, and
    ``_handle_call_tool`` calls ``self.call_tool(...)`` at request time, so
    the override is reached regardless of when ``__class__`` was set.
    ``verify_strict_dispatch()`` is what actually guards against a future
    SDK change silently breaking this override, not this docstring.
    """

    async def call_tool(
        self, name: str, arguments: dict[str, Any], context: Any | None = None
    ) -> types.CallToolResult | types.InputRequiredResult:
        tool = self._tool_manager.get_tool(name)
        if tool is not None:
            allowed = set(tool.parameters.get("properties", {}).keys())
            unknown = sorted(set(arguments.keys()) - allowed)
            if unknown:
                raise ToolInputError(
                    f"[validation_error] Unknown argument(s) for tool "
                    f"'{name}': {', '.join(unknown)}. "
                    f"Allowed arguments: {', '.join(sorted(allowed))}"
                )
            not_finite = sorted(key for key, value in arguments.items() if _non_finite(value))
            if not_finite:
                raise ToolInputError(
                    f"[validation_error] Argument(s) for tool '{name}' contain NaN or Infinity, "
                    f"which are not numbers: {', '.join(not_finite)}."
                )
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                # Field path and message only: the offending value itself can be caller data.
                field_errors = "; ".join(
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.__cause__.errors()
                )
                raise ToolInputError(
                    f"[validation_error] Invalid argument(s) for tool '{name}': {field_errors}"
                ) from exc
            raise

    def add_tool(
        self,
        fn: Callable[..., Any],
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: ToolAnnotations | None = None,
        icons: list[Icon] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> None:
        """As MCPServer.add_tool, plus a top-level `additionalProperties: false`
        on the generated schema.

        This is documentation for well-behaved clients that validate against
        the advertised schema before sending — it is not itself enforcement.
        The SDK advertises this schema but never validates a call against it
        before handler execution regardless; `call_tool` above remains the
        only real gate. Non-recursive: nested `dict[str, Any]`-typed
        parameters (e.g. `custom_fields`, `filters` payloads) keep their own,
        independently generated `additionalProperties`, untouched by this.
        """
        super().add_tool(
            fn,
            name=name,
            title=title,
            description=description,
            annotations=annotations,
            icons=icons,
            meta=meta,
            structured_output=structured_output,
        )
        tool_name = name or fn.__name__
        tool = self._tool_manager.get_tool(tool_name)
        if tool is not None:
            tool.parameters["additionalProperties"] = False
            self._make_arguments_strict(tool)

    @staticmethod
    def _make_arguments_strict(tool: Any) -> None:
        """Validate arguments in pydantic's strict mode: a boolean is not an integer, `"yes"` or `1`
        is not `true`, `5.0` and `"5"` are not integers, and NaN or Infinity are not numbers.
        Lax coercion turned `confirm="yes"` into a confirmed write and `group_id=true` into group 1.
        Only tools are covered: the server registers no resource templates or prompts.
        """
        meta = tool.fn_metadata
        base = meta.arg_model
        strict_model = type(
            base.__name__,
            (base,),
            {
                "model_config": ConfigDict(strict=True, allow_inf_nan=False, validate_default=True),
                "__module__": base.__module__,
            },
        )
        containers = frozenset(
            key for key, schema in tool.parameters.get("properties", {}).items() if _admits_container(schema)
        )
        carried = {name: getattr(meta, name) for name in FuncMetadata.model_fields if name != "arg_model"}
        tool.fn_metadata = _StrictFuncMetadata(arg_model=strict_model, container_fields=containers, **carried)


async def verify_strict_dispatch(mcp: StrictMCPServer) -> None:
    """Assert that unknown-argument rejection actually reaches this instance's
    dispatch path, not just its Python method-resolution order.

    Uses the low-level server's internal handler registry
    (``_lowlevel_server.get_request_handler``) rather than a full
    client-server roundtrip — SDK-internal and version-sensitive by
    necessity (there is no more public API for driving a request through the
    dispatch path directly), but appropriate for a startup check that must
    run fast and deterministically on every launch. A separate test
    (test_strict_mcpserver.py) additionally exercises the real client-server
    roundtrip via the SDK's ``mcp.client.Client`` to catch SDK changes to
    serialization/dispatch/middleware this direct call cannot see.
    """
    probe_name = "__strict_mcpserver_probe__"

    @mcp.tool(name=probe_name)
    async def _probe(known: str = "x", flag: bool = False) -> str:  # pragma: no cover - never runs
        return known

    try:
        params = types.CallToolRequestParams(name=probe_name, arguments={"known": "x", "__unknown__": "x"})
        entry = mcp._lowlevel_server.get_request_handler("tools/call")
        if entry is None:
            raise RuntimeError(
                "StrictMCPServer self-test failed: no 'tools/call' request handler is "
                "registered on the low-level server at all. The installed mcp SDK "
                "version likely changed how MCPServer registers its handlers with "
                "mcp.server.lowlevel.Server; strict argument validation cannot be "
                "verified. Refusing to start."
            )
        # The handler's declared type requires a real ServerRequestContext, but
        # for a plain tools/call dispatch it's only used to construct the
        # injected Context object, never dereferenced otherwise -- verified
        # at runtime that None works here. mypy can't see that leniency.
        result = await entry.handler(None, params)  # type: ignore[arg-type]
        is_error = getattr(result, "is_error", False)
        text = "".join(getattr(block, "text", "") for block in getattr(result, "content", []))
        if not is_error or "[validation_error]" not in text:
            raise RuntimeError(
                "StrictMCPServer self-test failed: an unknown tool argument was not "
                "rejected by the live dispatch path. The installed mcp SDK version "
                "likely changed how MCPServer.call_tool is wired into request "
                "handling; strict argument validation is currently NOT enforced. "
                "Refusing to start."
            )
        typed = types.CallToolRequestParams(name=probe_name, arguments={"flag": "true"})
        typed_result = await entry.handler(None, typed)  # type: ignore[arg-type]
        typed_text = "".join(getattr(block, "text", "") for block in getattr(typed_result, "content", []))
        if not getattr(typed_result, "is_error", False) or "flag" not in typed_text:
            raise RuntimeError(
                'StrictMCPServer self-test failed: the string "true" was accepted for a boolean '
                "tool argument. The installed mcp SDK version likely changed how tool arguments "
                "are validated; strict argument types are currently NOT enforced. "
                "Refusing to start."
            )
    finally:
        mcp.remove_tool(probe_name)
