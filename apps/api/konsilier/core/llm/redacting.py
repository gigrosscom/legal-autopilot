from __future__ import annotations

import json
from typing import Any

from ..pii import PiiVault
from .base import Attachment, LLMProvider


class RedactingLLM:
    """Wraps any provider: redacts PII in the input, restores labels in the output.

    The core only talks to the LLM through this wrapper, so forgetting to redact
    is not possible. Attachments are passed only when explicitly allowed.
    """

    def __init__(self, provider: LLMProvider, vault: PiiVault):
        self.provider = provider
        self.vault = vault

    def complete_json(self, *, task: str, system: str, payload: dict[str, Any],
                      schema: dict[str, Any], attachments: tuple[Attachment, ...] = ()) -> dict[str, Any]:
        redacted = self.vault.redact_obj(payload)
        result = self.provider.complete_json(
            task=task, system=system, user=json.dumps(redacted, ensure_ascii=False, default=str),
            schema=schema, attachments=attachments,
        )
        return self.vault.restore_obj(result)
