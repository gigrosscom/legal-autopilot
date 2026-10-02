"""The chat's country rules live in the pack (packs/<cc>/pack.yaml chat_rules), never in the core prompt."""

from pathlib import Path

from konsilier.chat import SYSTEM
from konsilier.core.packs import PackRegistry


def test_pack_gives_its_chat_rules_and_the_core_prompt_stays_general(packs_dir: Path):
    reg = PackRegistry.load(packs_dir)
    rules = reg.pack("KZ").manifest.chat_rules
    assert "102" in rules and "258-VIII" in rules and "conciliation commission" in rules
    assert reg.pack("XX").manifest.chat_rules == ""  # a pack without rules: the general prompt only
    assert "country rules below" in SYSTEM
