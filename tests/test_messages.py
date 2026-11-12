"""What kinds and rules say to people (`tree.Messages`): whole sentences per language, held at
publish to the same messages with the same blanks in every language."""

import json

import pytest

from quern.library import Library, Package, check_messages, package_digest
from quern.tree import KindDef, Rule

from test_library import bolt, fasteners

SAID = {
    "fr": {"heading": "Boulons",
           "missing-mass": "{ $count ->\n    [one] Un boulon ne dit pas sa masse : « { $name } ».\n   *[other] { $count } boulons ne disent pas leur masse.\n}"},
    "en": {"heading": "Bolts",
           "missing-mass": "{ $count ->\n    [one] One bolt does not state its mass: “{ $name }”.\n   *[other] { $count } bolts do not state their mass.\n}"},
}


def saying(kind_messages=None, rule_messages=None) -> Package:
    pkg = fasteners()
    pkg.vocabulary[0].messages = kind_messages
    pkg.rules[0].messages = rule_messages
    return pkg


def test_a_package_that_says_nothing_keeps_its_digest():
    """The field is None by default and left out of the canonical form, so every package
    published before it existed keeps the digest its consumers locked."""
    pkg = fasteners()
    assert "messages" not in json.loads(pkg.model_dump_json(exclude_none=True))["vocabulary"][0]
    assert package_digest(pkg) == package_digest(saying())
    assert package_digest(pkg) != package_digest(saying(SAID))


def test_whole_sentences_in_every_language_publish(tmp_path):
    rule_said = {"fr": {"red": "Ce boulon ne pèse rien."}, "en": {"red": "This bolt weighs nothing."}}
    log = Library(tmp_path).publish(saying(SAID, rule_said), {})
    assert any("2 item(s) say what they mean to people in en, fr" in line for line in log)
    assert check_messages(fasteners()) == ""


@pytest.mark.parametrize("change, refused", [
    (lambda m: m["en"].pop("heading"), "do not say the same messages (heading)"),
    (lambda m: m["en"].__setitem__("missing-mass", "{ $count } bolts do not state their mass."),
     "en fills ['count'] and fr fills ['count', 'name']"),
    (lambda m: m["en"].__setitem__("heading", "Bolts {"), "is not a Fluent pattern"),
    (lambda m: m.__setitem__("French", m.pop("fr")), "'French' is not a language tag"),
])
def test_a_translation_that_drops_a_sentence_or_a_blank_is_refused(tmp_path, change, refused):
    said = json.loads(json.dumps(SAID))
    change(said)
    with pytest.raises(ValueError, match="kind 'bolt'") as e:
        Library(tmp_path).publish(saying(said), {})
    assert refused in str(e.value)


def test_a_rule_is_held_to_it_too(tmp_path):
    with pytest.raises(ValueError, match="rule 'bolt-has-mass': en and fr do not say the same messages"):
        Library(tmp_path).publish(saying(rule_messages={"fr": {"red": "Rien."}, "en": {}}), {})
