from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AIAssistantResponse:
    response: str
    api_responses: list[Any]
    history: list[Any]


class AIAssistantBase(ABC):
    @abstractmethod
    async def process_query(
        self, query: str, artifacts: list
    ) -> AIAssistantResponse: ...

class ToolCallingAIAssistant(AIAssistantBase):
    @abstractmethod
    def process_response(
        self, response: AIAssistantResponse, tag_name: str
    ) -> str:
        ...