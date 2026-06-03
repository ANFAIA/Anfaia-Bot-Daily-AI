"""Base port for an agent.

An agent is a unit of work with a typed input and a typed output. This
abstraction is deliberately neutral with respect to the orchestration framework:
today they run in our own sequential pipeline, but the same contract can be
wrapped as a LangGraph node, a CrewAI task or an AutoGen agent without touching
each agent's internal logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Agent[TInput, TOutput](ABC):
    """Generic contract for a system agent."""

    #: Stable name used in logs and metrics.
    name: str = "agent"

    @abstractmethod
    async def run(self, input_data: TInput) -> TOutput:
        """Run the agent on the input and produce the output."""
