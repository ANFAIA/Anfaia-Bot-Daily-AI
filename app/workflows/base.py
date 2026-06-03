"""Workflow abstraction.

Defines the `NewsWorkflow` contract. The business logic (which agents run and
in what order) lives behind this interface. A second phase can implement
`NewsWorkflow` on top of LangGraph, CrewAI, DeepAgents or AutoGen, reusing the
same agents and ports, without rewriting the domain or the API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import WorkflowReport


class NewsWorkflow(ABC):
    """Orchestrates the daily news pipeline end to end."""

    @abstractmethod
    async def run(self) -> WorkflowReport:
        """Runs the full workflow and returns a report of the result."""
