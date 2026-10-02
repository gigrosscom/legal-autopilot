"""Owner 02.10 «Навык должен работать везде»: the ZANN legal method reaches every model call that reasons about law."""

from konsilier import chat
from konsilier.core import ai
from konsilier.core.legal_method import LEGAL_METHOD
from konsilier.lawagent import agent


def test_method_is_in_every_prompt():
    assert LEGAL_METHOD in chat.SYSTEM
    assert LEGAL_METHOD in agent.SYSTEM
    assert LEGAL_METHOD in ai._COMMON_RULES  # classification, facts, statement of circumstances, demands


def test_method_names_no_country_and_formats_safely():
    assert "{" not in LEGAL_METHOD and "}" not in LEGAL_METHOD
    for word in ("Kazakhstan", "Казахстан", "РК", "KZ"):
        assert word not in LEGAL_METHOD
