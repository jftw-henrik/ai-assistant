from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used by the LLM."""

    @property
    @abstractmethod
    def description(self) -> str:
        """When the agent should use this tool."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool arguments."""

    @abstractmethod
    def execute(self, **kwargs: Any) -> None:
        """Run the tool with validated arguments."""

    def to_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
