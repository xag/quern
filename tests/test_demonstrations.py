"""Demonstrations: the proof obligation the third kind of knowledge never had.

Rules answer to examples and counter-examples. Solvers answered to prose. A gate
reading `solve('grounding/untrusted', self) == 0` cannot tell a contract that counts
guesses from one that returns 0 unconditionally, and it goes green either way — so
the contract every gate leans on was the one thing in the library published on its
word. These are the worked cases that end that, and the checks that they are worked
cases rather than a shape someone filled in.
"""

import json

import pytest

import quern.grounding  # noqa: F401 -- registers the standard natives and their spec
from quern.grounding import GROUNDING_SPEC
from quern.library import CounterExample, Library, Package, validate_package
from quern.solver import SolverDef
from quern.tree import (
    NATIVE,
    NATIVE_SPEC,
    Demonstration,
    KindDef,
    Node,
    Quern,
    Rule,
    check_demonstrations,
    register_native,
)


@pytest.fixture
def scratch_native():
    """Register natives under names this test owns, and take them away after —
    NATIVE is process-global, and a test that leaks into it makes the next one lie."""
    installed: list[str] = []

    def install(name: str, fn, spec=()):
        register_native(name, fn, spec)
        installed.append(name)
        return name
    yield install
    for name in installed:
        NATIVE.pop(name, None)
        NATIVE_SPEC.pop(name, None)


def pkg(**kw) -> Package:
    # a kind the package declares is a kind something in it has to be
    kw.setdefault("examples", [Node(id="c0", kind="crate")])
    return Package(name="counting", version="1",
                   vocabulary=[KindDef(kind="crate", description="holds things")],
                   **kw)


def crates(n: int) -> list[Node]:
    return [Node(id="yard", kind="yard",
                 children=[Node(id=f"c{i}", kind="crate") for i in range(n)])]


# --- the standard contracts, which is the point of the machinery ------------------

def test_the_shipped_natives_hold_against_every_scenario_they_state():
    for name, spec in GROUNDING_SPEC.items():
        assert check_demonstrations(spec) == [], f"{name} fails its own spec"


def test_the_spec_anticipates_the_scenarios_that_turn_a_gate_green_for_nothing():
    """Not coverage for its own sake. These four are the ones where a wrong answer is
    still a plausible answer, and each is the difference between a gate that means
    something and one that reads green over an absence."""
    said = {d.because for spec in GROUNDING_SPEC.values() for d in spec}
    blob = " ".join(said).lower()
    assert "empty branch answers 0" in blob            # nothing to doubt != checked
    assert "no link of that name" in blob              # a typo in a link name
    assert "never said how tight it is" in blob        # unstated tolerance
    assert "no longer exists" in blob                  # the wall that was deleted

    refusals = [d for spec in GROUNDING_SPEC.values() for d in spec
                if d.expect_error is not None]
    assert len(refusals) == 2, "absence must be demonstrated, not assumed"


def test_a_native_answering_wrongly_is_caught_by_its_own_spec():
    """The spec has to be able to fail, or every run of it is theatre."""
    bad = GROUNDING_SPEC["grounding/untrusted"][1].model_copy(update={"expect": 99.0})
    assert check_demonstrations([bad]) == [
        "grounding/untrusted (one guess in the branch is one count): "
        "expected 99, answered 1"]


def test_absence_is_refused_and_not_answered_zero():
    """The scenario the whole `expect_error` shape exists for: a gate pointed at a
    node that is gone must say so. Answering 0 would read as 'nothing untrusted'."""
    dem = Demonstration(contract="grounding/untrusted", nodes=[], args=["ghost"],
                        expect=0.0, because="if absence answered zero")
    assert check_demonstrations([dem]) == [
        "grounding/untrusted (if absence answered zero): the call raised: "
        "no node at 'ghost'"]


# --- the gate over natives ---------------------------------------------------------

def test_a_package_declaring_a_registered_native_publishes_with_its_scenarios(tmp_path):
    p = pkg(solvers=[SolverDef(name="grounding/untrusted", native=True,
                               description="counts what is not safe to act on")])
    log = validate_package(p, tmp_path, Library(tmp_path))
    line = next(ln for ln in log if "grounding/untrusted" in ln)
    assert "10 demonstration(s) hold" in line
    assert "registered beside the implementation" in line
    assert "an empty branch answers 0" in line  # the scenarios are in the proof log


def test_a_native_this_install_does_not_implement_is_refused(tmp_path):
    """A package may claim any capability; publishing is where the claim meets the
    process that would have to honour it."""
    p = pkg(solvers=[SolverDef(name="geometry/volume", native=True)])
    with pytest.raises(ValueError, match="nothing is registered under that name"):
        validate_package(p, tmp_path, Library(tmp_path))


def test_a_native_with_no_spec_is_refused(tmp_path, scratch_native):
    scratch_native("test/bare", lambda tree, path="": 0.0)
    p = pkg(solvers=[SolverDef(name="test/bare", native=True)])
    with pytest.raises(ValueError, match="registers no spec"):
        validate_package(p, tmp_path, Library(tmp_path))


def test_a_native_that_fails_its_spec_cannot_be_published(tmp_path, scratch_native):
    """The spec is registered beside the implementation, so this is the case where the
    code drifted from what it promised — caught at the door of the library."""
    scratch_native("test/liar", lambda tree, path="": 0.0, spec=[
        Demonstration(contract="test/liar", nodes=crates(0), args=["yard"], expect=0,
                      because="an empty yard"),
        Demonstration(contract="test/liar", nodes=crates(3), args=["yard"], expect=3,
                      because="three crates"),
    ])
    p = pkg(solvers=[SolverDef(name="test/liar", native=True)])
    with pytest.raises(ValueError, match="fails its own demonstration"):
        validate_package(p, tmp_path, Library(tmp_path))


def test_one_expected_answer_is_no_evidence(tmp_path, scratch_native):
    """A contract returning that number unconditionally satisfies every demonstration
    in the set. This is the counter-example argument, one level down."""
    def count(tree, path=""):
        node = tree.get(path)
        return float(len(node.children)) if node else 0.0

    scratch_native("test/count", count, spec=[
        Demonstration(contract="test/count", nodes=crates(0), args=["yard"], expect=0,
                      because="an empty yard"),
        Demonstration(contract="test/count", nodes=[Node(id="yard", kind="yard")],
                      args=["yard"], expect=0, because="a yard with nothing in it"),
    ])
    p = pkg(solvers=[SolverDef(name="test/count", native=True)])
    with pytest.raises(ValueError, match="every demonstration .* expects the same"):
        validate_package(p, tmp_path, Library(tmp_path))


def test_a_package_may_add_scenarios_to_a_native_it_did_not_write(tmp_path,
                                                                  scratch_native):
    """The registered spec cannot be softened by a package — but it can be *extended*:
    a domain that leans on a contract in a way its author never considered says so
    here, and the addition is checked like the rest."""
    def count(tree, path=""):
        node = tree.get(path)
        return float(len(node.children)) if node else 0.0

    scratch_native("test/count", count, spec=[
        Demonstration(contract="test/count", nodes=crates(0), args=["yard"], expect=0,
                      because="an empty yard"),
        Demonstration(contract="test/count", nodes=crates(2), args=["yard"], expect=2,
                      because="two crates"),
    ])
    p = pkg(solvers=[SolverDef(name="test/count", native=True)],
            demonstrations=[Demonstration(
                contract="test/count", nodes=crates(40), args=["yard"], expect=40,
                because="a yard at the scale this domain actually sees")])
    log = validate_package(p, tmp_path, Library(tmp_path))
    line = next(ln for ln in log if "test/count" in ln)
    assert "3 demonstration(s) hold" in line
    assert "2 registered beside the implementation + 1 from the package" in line


def test_a_demonstration_must_name_a_contract_the_package_declares(tmp_path):
    p = pkg(demonstrations=[Demonstration(contract="nobody/home", args=[""], expect=1,
                                          because="a contract from thin air")])
    with pytest.raises(ValueError, match="does not declare"):
        validate_package(p, tmp_path, Library(tmp_path))


# --- the gate over packaged wasm ----------------------------------------------------
#
# A module that answers one of two fixed proposals depending on how long the payload
# is. Crude, and exactly enough: it really executes in the sandbox, it really varies
# with what it is handed, and its two answers are far enough apart that a demonstration
# can tell them apart.

_SMALL = '{"diagnostics":[],"proposals":[{"path":"w","param":"cut","value":1}]}'
_LARGE = '{"diagnostics":[],"proposals":[{"path":"w","param":"cut","value":2}]}'


def _payload_len(node: Node, path: str) -> int:
    return len(json.dumps({"path": path,
                           "slice": node.model_dump(exclude_none=True),
                           "params": {}}))


def _module(threshold: int) -> bytes:
    import wasmtime
    small, large = _SMALL.replace('"', '\\"'), _LARGE.replace('"', '\\"')
    return wasmtime.wat2wasm(f'''
      (module
        (memory (export "memory") 1)
        (data (i32.const 1024) "{small}")
        (data (i32.const 2048) "{large}")
        (func (export "alloc") (param i32) (result i32) i32.const 4096)
        (func (export "run") (param $ptr i32) (param $len i32) (result i64)
          (if (result i64) (i32.lt_u (local.get $len) (i32.const {threshold}))
            (then (i64.or (i64.shl (i64.const 1024) (i64.const 32))
                          (i64.const {len(_SMALL)})))
            (else (i64.or (i64.shl (i64.const 2048) (i64.const 32))
                          (i64.const {len(_LARGE)}))))))
    ''')


THIN = Node(id="w", kind="wall")
FAT = Node(id="w", kind="wall", params={"a": {"value": 1.0}, "b": {"value": 2.0},
                                        "c": {"value": 3.0}})
CUTOFF = (_payload_len(THIN, "w") + _payload_len(FAT, "w")) // 2


def wasm_pkg(dems) -> Package:
    return Package(name="cutter", version="1",
                   solvers=[SolverDef(name="cutter/plan", reads=[""])],
                   demonstrations=dems)


def prop(value: float):
    return [{"path": "w", "param": "cut", "value": value}]


GOOD = [Demonstration(contract="cutter/plan", nodes=[THIN], args=["w"],
                      expect_proposals=prop(1), because="a bare wall"),
        Demonstration(contract="cutter/plan", nodes=[FAT], args=["w"],
                      expect_proposals=prop(2), because="a wall with dimensions")]


def test_the_fixture_module_really_varies_with_its_input():
    """If it did not, every claim below about catching drift would be untestable."""
    assert _payload_len(THIN, "w") < CUTOFF < _payload_len(FAT, "w")


def test_a_wasm_solver_that_demonstrates_nothing_is_refused(tmp_path):
    """It meets the ABI. The ABI says it is callable, not that it is right."""
    lib = Library(tmp_path)
    with pytest.raises(ValueError, match="demonstrates nothing"):
        lib.publish(wasm_pkg([]), {"cutter/plan": _module(CUTOFF)})


def test_a_wasm_solver_proving_itself_publishes(tmp_path):
    lib = Library(tmp_path)
    log = lib.publish(wasm_pkg(GOOD), {"cutter/plan": _module(CUTOFF)})
    line = next(ln for ln in log if "cutter/plan" in ln and "demonstration" in ln)
    assert "2 demonstration(s) hold" in line
    assert "a wall with dimensions" in line


def test_a_wasm_solver_whose_answer_drifted_is_refused(tmp_path):
    """Same demonstrations, a module that no longer honours them: the threshold moved,
    so both calls now take the same branch. This is what a solver regression looks
    like from the library's side."""
    lib = Library(tmp_path)
    with pytest.raises(ValueError, match="fails its own demonstration"):
        lib.publish(wasm_pkg(GOOD), {"cutter/plan": _module(0)})


def test_a_wasm_solver_demonstrating_one_answer_twice_is_refused(tmp_path):
    lib = Library(tmp_path)
    same = [GOOD[0], GOOD[0].model_copy(update={"because": "another bare wall"})]
    with pytest.raises(ValueError, match="every demonstration .* expects the same"):
        lib.publish(wasm_pkg(same), {"cutter/plan": _module(CUTOFF)})


def test_web_and_prose_artifacts_owe_no_demonstration(tmp_path):
    """They serve experience and guidance and never propose a value, so there is no
    answer to be wrong about — the purity boundary decides the obligation."""
    lib = Library(tmp_path)
    log = lib.publish(Package(
        name="jog", version="1",
        solvers=[SolverDef(name="jog-pad", medium="web"),
                 SolverDef(name="jog-howto", medium="prose")]),
        {"jog-pad": b"<html>pad</html>", "jog-howto": b"drag gently."})
    assert sum("stored" in line for line in log) == 2
    assert not any("demonstration" in line for line in log)


# --- the shape itself ---------------------------------------------------------------

def test_a_demonstration_states_exactly_one_expectation():
    with pytest.raises(ValueError, match="exactly one"):
        Demonstration(contract="x", because="states none")
    with pytest.raises(ValueError, match="exactly one"):
        Demonstration(contract="x", expect=1, expect_error="boom",
                      because="states two")


def test_a_contract_answering_the_wrong_shape_says_so():
    tree = Quern()
    dem = Demonstration(contract="test/shape", args=[""], expect=1.0,
                        because="asked for a number")
    got = check_demonstrations(
        [dem], tree, lambda t, name, args: {"diagnostics": [], "proposals": []})
    assert "answered in another shape" in got[0]


# --- the first kind of knowledge ----------------------------------------------------
#
# A kind's MEANING is prose and a reader judges it. Whether anything IS one is
# mechanical, and it is the word-with-no-referent the whole gate exists against.

CRATE = KindDef(kind="crate", description="holds things")
NAMESPACE = KindDef(kind="counting", description="Convention pack, not a node kind: "
                                                 "somewhere for the contracts to hang.",
                    convention=True)


def test_a_kind_nothing_is_cannot_be_published(tmp_path):
    with pytest.raises(ValueError, match=r"1 kind\(s\) that no example is: crate"):
        validate_package(Package(name="counting", version="1", vocabulary=[CRATE]),
                         tmp_path, Library(tmp_path))


def test_a_kind_is_demonstrated_anywhere_in_an_example_tree(tmp_path):
    """Nested counts: a kind that only ever appears as somebody's child is still a
    kind something is."""
    log = validate_package(
        Package(name="counting", version="1", vocabulary=[CRATE],
                examples=[Node(id="yard", kind="yard",
                               children=[Node(id="c0", kind="crate")])]),
        tmp_path, Library(tmp_path))
    assert any("1 kind(s) instantiated" in line for line in log)


def test_a_convention_may_name_nothing_and_publish(tmp_path):
    log = validate_package(Package(name="counting", version="1", vocabulary=[NAMESPACE]),
                           tmp_path, Library(tmp_path))
    assert any("1 convention(s) held to naming nothing: counting" in line for line in log)


def test_the_convention_flag_is_a_claim_and_not_an_escape_hatch(tmp_path):
    """The half that makes the flag worth having. If declaring `convention=True` only
    ever bought an exemption, anyone could flip it and the check would read as a check
    while being none — so a kind that says nothing is one is held to it."""
    with pytest.raises(ValueError, match="declared a convention.*but an example"):
        validate_package(
            Package(name="counting", version="1", vocabulary=[NAMESPACE],
                    examples=[Node(id="oops", kind="counting")]),
            tmp_path, Library(tmp_path))


def test_a_counter_example_does_not_demonstrate_a_kind(tmp_path):
    """A defect is not a referent. A kind whose only appearance is in the node a rule
    must REJECT has never been shown as something sound, which is what a consumer of
    the vocabulary is being asked to build with."""
    with pytest.raises(ValueError, match="no example is: crate"):
        validate_package(
            Package(name="counting", version="1", vocabulary=[CRATE],
                    rules=[Rule(name="crate-is-labelled", kind="crate",
                                expr="param(self, 'label') > 0")],
                    examples=[Node(id="yard", kind="yard")],
                    counter_examples=[CounterExample(
                        rule="crate-is-labelled", node=Node(id="bare", kind="crate"),
                        because="a crate with no label")]),
            tmp_path, Library(tmp_path))


def test_a_convention_caught_by_a_counter_example_is_refused_too(tmp_path):
    with pytest.raises(ValueError, match="declared a convention.*but a counter-example"):
        validate_package(
            Package(name="counting", version="1", vocabulary=[NAMESPACE, CRATE],
                    rules=[Rule(name="crate-is-labelled", kind="crate",
                                expr="param(self, 'label') > 0")],
                    examples=[Node(id="c0", kind="crate",
                                   params={"label": {"value": 1.0}})],
                    counter_examples=[CounterExample(
                        rule="crate-is-labelled",
                        nodes=[Node(id="bare", kind="crate"),
                               Node(id="sneaky", kind="counting")],
                        because="a crate with no label")]),
            tmp_path, Library(tmp_path))


def test_the_shipped_grounding_package_declares_its_namespace(tmp_path):
    """The package this substrate's own gates lean on is the case the flag was added
    for: one entry, naming a namespace its three contracts hang prose on."""
    voc = Library(".quern/library").get("grounding", "1.2.0").vocabulary
    assert [(k.kind, k.convention) for k in voc] == [("grounding", True)]
