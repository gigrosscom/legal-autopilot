from pathlib import Path

import pytest

from konsilier.core.packs import PackRegistry, PackValidationError
from konsilier.core.scenario import ScenarioValidationError, load_scenario_text, parse_condition, ConditionError

VALID = """
id: zz.demo.case
version: 0.1.0
ontology: DEMO.CASE
jurisdiction: ZZ
languages: [en]
owner: lawyer:zz
title: {en: Demo}
intake:
  - name
  - paid_on: {type: date}
  - amount: {type: money}
  - files: [receipt]
actions:
  - id: first
    title: {en: First}
    template: zz/first.docx
    addressee: {authority: court}
    deadline: {calendar_days: 10}
  - id: second
    when: first.response in [none, refusal]
    kind: handoff
"""


def errors_of(text: str, **kw) -> list[str]:
    with pytest.raises(ScenarioValidationError) as exc:
        load_scenario_text(text, source="test.yaml", **kw)
    return exc.value.errors


def test_valid_scenario_and_compact_intake():
    sc = load_scenario_text(VALID)
    assert [f.name for f in sc.intake] == ["name", "paid_on", "amount", "files"]
    assert sc.field("files").type == "evidence" and sc.field("files").optional
    assert sc.field("paid_on").type == "date"
    assert sc.is_draft
    assert sc.todos() == ["zz.demo.case:first: deadline 10 days — norm_ref TODO"]


def test_yaml_syntax_error_has_line_number():
    errs = errors_of("id: x\nactions: [\n  - broken")
    assert len(errs) == 1 and errs[0].startswith("YAML syntax error at line")


def test_top_level_must_be_mapping():
    assert errors_of("- a\n- b") == ["top level must be a mapping (key: value)"]


def test_missing_required_fields_are_listed_with_paths():
    errs = errors_of("id: zz.demo.case\nversion: 0.1.0\n")
    joined = "\n".join(errs)
    for field in ("ontology", "jurisdiction", "languages", "owner", "title", "intake", "actions"):
        assert f"{field}: Field required" in joined


def test_error_message_is_readable():
    with pytest.raises(ScenarioValidationError) as exc:
        load_scenario_text(VALID.replace("version: 0.1.0", "version: one"), source="packs/zz/demo.yaml")
    msg = str(exc.value)
    assert "Invalid scenario packs/zz/demo.yaml" in msg
    assert "version: version 'one' must be semver" in msg


@pytest.mark.parametrize("mutation,expected", [
    (("when: first.response in [none, refusal]", "when: first.response maybe refusal"), "cannot parse condition"),
    (("when: first.response in [none, refusal]", "when: first.response in [none, angry]"), "unknown response value"),
    (("when: first.response in [none, refusal]", "when: third.response == none"), "not an earlier action"),
    (("    deadline: {calendar_days: 10}", "    deadline: {calendar_days: 10, business_days: 3}"), "exactly one of"),
    (("    template: zz/first.docx\n", ""), "needs a template"),
    (("id: zz.demo.case", "id: kz.demo.case"), "does not match jurisdiction"),
    (("  - amount: {type: money}", "  - amount: {type: money}\n  - amount"), "duplicate intake fields"),
    (("  - amount: {type: money}", "  - amount: {type: banana}"), "intake[2].type"),
    (("    kind: handoff", "    kind: handoff\n    color: red"), "Extra inputs are not permitted"),
    (("  - name\n", "  - Name Field\n"), "must be snake_case"),
])
def test_invalid_scenarios_are_rejected(mutation, expected):
    old, new = mutation
    assert old in VALID
    errs = errors_of(VALID.replace(old, new))
    assert any(expected in e for e in errs), errs


def test_first_action_cannot_have_condition():
    text = VALID.replace("  - id: first\n", "  - id: first\n    when: first.response == none\n")
    assert any("must not have a 'when'" in e or "not an earlier action" in e for e in errors_of(text))


def test_missing_template_file_is_reported(tmp_path: Path):
    errs = errors_of(VALID, packs_root=tmp_path)
    assert errs == ["actions.first.template: file not found: zz/first.docx"]


def test_condition_dsl():
    c = parse_condition("a.response in [none, refusal] or b.response == partial and a.response != full")
    assert c.evaluate({"a": "none"})
    assert not c.evaluate({"a": "full"})
    assert c.evaluate({"a": "partial", "b": "partial"})
    assert not c.evaluate({})
    for bad in ("", "a.status == none", "a.response in []", "a.response == [x]", "a.response in none",
                "__import__('os').response == x"):
        with pytest.raises(ConditionError):
            parse_condition(bad)


def test_real_packs_are_valid():
    root = Path(__file__).resolve().parents[3] / "packs"
    registry = PackRegistry.load(root)
    ids = {s.id for s in registry.published()}
    assert {"kz.consumer.refund", "kz.money.credit_fraud"} <= ids


def test_pack_with_invalid_scenario_fails_loudly(packs_dir: Path):
    (packs_dir / "kz" / "scenarios" / "broken.yaml").write_text("id: kz.broken\nversion: x\n", encoding="utf-8")
    with pytest.raises(PackValidationError, match="broken.yaml"):
        PackRegistry.load(packs_dir)
