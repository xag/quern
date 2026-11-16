"""certification@0.1.0: what a standard is made of, as two kinds a certificate is run from.

A standard is knowledge like any other: rules in a package and, in the tree, the nodes that
say what those rules are for. A `criterion` names the rules that judge one thing about a
subject; a `level` is a use the subject may be put to, and requires criteria. Whoever
certifies (quern.certify.certificate, beside this module) reads these two kinds and knows no domain: a package
that publishes a better criterion, another rule or a new level changes the certificate of
everything it applies to, and no code changes with it.

What a level allows is the level's to say: payload `allows` names what reaching it opens
(a document shown, an entry shared), in the words of whoever reads it. A reader that holds
something back asks the tree which level allows it; it never names a level itself.

Two rules keep a standard from saying nothing: a criterion names what it judges, by which
rules and what it measures; a level names the kind of subject it is a use of and requires
criteria that exist.
"""

from __future__ import annotations

from .library import CounterExample, Package
from .tree import KindDef, Node, Rule


def _say(fr: str, en: str, key: str) -> dict:
    return {"fr": {key: fr}, "en": {key: en}}


VOCABULARY = [
    KindDef(
        kind="criterion",
        description="One thing a standard judges about a subject. Payload: `applies_to` (the "
        "kind of node it judges, or several), `rules` (the names of the rules that judge it) "
        "and `measures` (what it is a measure of, in the standard's own word: completeness, "
        "reliability, consistency, presentation). Held when every rule it names holds on the "
        "subject and beneath it. Payload `say`, per language, is its name for people.",
        messages=_say("Critère", "Criterion", "heading"),
    ),
    KindDef(
        kind="level",
        description="A use a subject may be put to. Payload: `of` (the kind of subject) and "
        "`allows` (what reaching it opens, as the names its readers ask by: a document shown, "
        "an entry shared; may be empty); the link `requires` to the criteria that use needs. "
        "Reached when every criterion it requires is held. Payload `say`, per language, is "
        "its name for people.",
        links={"requires": "the criteria this use needs"},
        messages=_say("Niveau", "Level", "heading"),
    ),
]

RULES = [
    Rule(
        name="a-criterion-names-what-it-judges",
        kind="criterion",
        description="A criterion names the kind of node it judges, the rules that judge it, "
        "and what it measures.",
        expr="len(payload(self, 'rules', '')) > 0 and len(payload(self, 'applies_to', '')) > 0 "
             "and len(payload(self, 'measures', '')) > 0",
        messages=_say("Ce critère ne dit pas ce qu'il juge, par quelles règles, ou ce qu'il mesure.",
                      "This criterion does not say what it judges, by which rules, or what it measures.",
                      "red"),
    ),
    Rule(
        name="a-level-requires-criteria",
        kind="level",
        description="A level says the kind of subject it is a use of and requires criteria "
        "that exist.",
        expr="len(payload(self, 'of', '')) > 0 and len(linked(self, 'requires')) > 0 and "
             "every(c, linked(self, 'requires'), some(k, nodes('criterion'), k == c))",
        messages=_say("Ce niveau ne dit pas de quoi il est un usage, ou exige un critère qui n'existe pas.",
                      "This level does not say what it is a use of, or requires a criterion that does not exist.",
                      "red"),
    ),
]

EXAMPLES = [
    Node(id="standards", kind="", children=[
        Node(id="states-its-size", kind="criterion", name="Its size is stated",
             payload={"applies_to": "box", "measures": "completeness", "rules": ["a-box-states-its-size"]}),
        Node(id="can-be-shipped", kind="level", name="Can be shipped",
             payload={"of": "box", "allows": ["shipping-label"]},
             links={"requires": ["standards/states-its-size"]}),
    ]),
]

_BAD = [
    Node(id="standards", kind="", children=[
        Node(id="says-nothing", kind="criterion", payload={"applies_to": "box", "measures": "completeness"}),
        Node(id="needs-nothing", kind="level", payload={"of": "box"}, links={"requires": ["standards/ghost"]}),
    ]),
]

COUNTER_EXAMPLES = [
    CounterExample(rule="a-criterion-names-what-it-judges", nodes=_BAD,
                   because="a criterion that names no rule judges nothing"),
    CounterExample(rule="a-level-requires-criteria", nodes=_BAD,
                   because="a level requiring a criterion that does not exist"),
]

PACKAGE = Package(
    name="certification",
    version="0.1.0",
    description="What a standard is made of: a criterion names the rules that judge one thing "
                "about a subject and what it measures; a level is a use the subject may be put "
                "to, requires criteria, and says what reaching it allows. A certificate "
                "(quern.certify) is run from these two kinds and the rules a standard's own "
                "package carries, so a standard improves by republishing, with no reader changed.",
    publisher="standard library",
    vocabulary=VOCABULARY,
    rules=RULES,
    examples=EXAMPLES,
    counter_examples=COUNTER_EXAMPLES,
)


def build() -> Package:
    return PACKAGE
