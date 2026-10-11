"""Annotations shared by the MCP tool signatures."""

from __future__ import annotations

from pydantic import StrictInt

# The SDK validates tool arguments in lax mode, where a plain int would turn
# a JSON true into 1 and 7.0 into 7.
IdOrName = StrictInt | str
