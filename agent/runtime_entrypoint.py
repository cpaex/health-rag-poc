"""AgentCore Runtime entrypoint (SPEC.md §6 build order, Phase 6).

Packaged ARM64-compatible and invoked via `InvokeAgentRuntime`. Delegates to
agent.supervisor.run(). Implemented in Phase 6.
"""

from __future__ import annotations


def handler(event: dict, context=None) -> dict:  # noqa: ANN001
    raise NotImplementedError("Phase 6: AgentCore Runtime entrypoint")
