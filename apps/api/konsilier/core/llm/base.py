from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class Attachment:
    content_type: str
    data: bytes
    filename: str = "file"


class LLMProvider(Protocol):
    """Single capability the core needs: a JSON answer that matches ``schema``.

    ``task`` names the job (qualify, extract_fields, extract_evidence, narrative,
    classify_response) so that providers/mocks can route or log; ``user`` is a
    JSON document with the task input. Inputs are already PII-redacted.
    """

    def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        attachments: tuple[Attachment, ...] = (),
    ) -> dict[str, Any]: ...
