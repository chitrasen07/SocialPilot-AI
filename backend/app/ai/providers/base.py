from typing import Protocol

from pydantic import BaseModel

from app.ai.schemas import Usage


class AIProvider(Protocol):
    name: str
    model: str

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel]
    ) -> tuple[BaseModel, Usage]: ...

    async def generate_reply(self, prompt: str) -> tuple[str, float, Usage]: ...
