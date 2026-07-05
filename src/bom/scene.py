"""The generic design substrate: a BOM-like tree where semantics are data.

One structural concept — the node. A node has a free-text `kind` (an étiquette, not
a class: nothing in this module branches on it), parameters whose every number is a
provenance-carrying Quantity, named `links` to other nodes, an optional parametric
shape, and children. What a kind *means* lives in the scene's `vocabulary`, written
and read through the same API as the tree — the MCP-tools principle applied to the
model: semantics accompany the data instead of being fixed in code.

Shapes are deliberately few and generic: vertical extrusions (box, prism, cylinder),
mesh references, and boolean grouping (union | difference | intersection over the
node's children). Shape arguments may name a parameter (looked up through the
ancestor chain, BOM-style) so a branch re-dimensions by editing one param.

Nodes are addressed by slash paths ("wardrobe/frame/side-left"), so an iterating
client edits a branch without resending the tree — the loop of issue #9: write a
subtree, render, refine.
"""

from __future__ import annotations

import io
import math
from typing import Any

from pydantic import BaseModel, Field

from .provenance import Quantity


class Transform(BaseModel):
    """Placement relative to the parent node: translate mm, then rotate about z."""

    translate: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotate_z_deg: float = 0.0


class Shape(BaseModel):
    """A parametric solid, or a boolean over the node's children.

    Ops: box (size [w, d, h]) | prism (polygon + height) | cylinder (diameter +
    height) | mesh (uri) | union | difference | intersection. Booleans take the
    children in order; for `difference` the first child is the stock, the rest are
    cuts. Numeric arguments accept a parameter name instead of a number.
    """

    op: str
    size: list[float | str] | None = None       # box: [w, d, h]
    polygon: list[list[float]] | None = None    # prism footprint, [x, y] mm
    height: float | str | None = None           # prism | cylinder
    diameter: float | str | None = None         # cylinder
    uri: str | None = None                      # mesh reference (e.g. a .glb)


class Node(BaseModel):
    """One BOM line: a component, an assembly, or anything the vocabulary defines."""

    id: str
    kind: str = ""   # free label — meaning lives in the scene vocabulary, not here
    name: str = ""
    transform: Transform | None = None
    shape: Shape | None = None
    params: dict[str, Quantity] = Field(default_factory=dict)
    links: dict[str, list[str]] = Field(default_factory=dict)  # name -> node paths
    meta: dict[str, str] = Field(default_factory=dict)
    children: list[Node] = Field(default_factory=list)

    def child(self, cid: str) -> Node | None:
        return next((c for c in self.children if c.id == cid), None)


class KindDef(BaseModel):
    """One vocabulary entry: what a `kind` means, in prose the next client reads.

    This is where semantics live — registered at runtime, per home, by whoever
    designs there. `params` and `links` document the names a node of this kind is
    expected to carry ("depth: rail-to-front in mm", "separates: the two spaces").
    """

    kind: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    links: dict[str, str] = Field(default_factory=dict)


class Rule(BaseModel):
    """A solver defined at runtime and capitalized in the store, like vocabulary.

    `expr` is a boolean expression in the safe rule language (arithmetic,
    comparisons, and/or/not, and geometry functions over realized branches:
    volume(p), bbox_w/d/h(p), z_min/z_max(p), clearance(a, b), param(p, name)).
    Scope: `kind` runs the rule once per node of that kind (its params are in
    scope, `self` is its path); `path` pins it to one branch; neither = global.
    No predefined semantics: the rule carries its own meaning in `description`.
    """

    name: str
    expr: str
    description: str = ""
    kind: str | None = None
    path: str | None = None


class Scene(BaseModel):
    """A home's design tree plus the semantics that give it meaning — vocabulary
    (what kinds are) and rules (what must hold), both data, both written through
    the same API as the tree."""

    vocabulary: list[KindDef] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    root: Node = Field(default_factory=lambda: Node(id="scene"))


# --- path addressing ----------------------------------------------------------

def get_node(scene: Scene, path: str) -> Node | None:
    node = scene.root
    for seg in _segs(path):
        node = node.child(seg)
        if node is None:
            return None
    return node


def semantics_at(scene: Scene, path: str, depth: int | None = None) -> dict[str, Any]:
    """The meaning of a slice of the tree, discovered with the slice itself.

    Returns the vocabulary entries for every kind present at `path` (down to
    `depth`) and the rules that apply there — so a client learns what it is
    looking at exactly as it navigates, the way an MCP tool carries its own
    description. Nothing global to fetch, nothing to know in advance.
    """
    node = get_node(scene, path)
    if node is None:
        return {}
    kinds: set[str] = set()

    def collect(n: Node, d: int | None) -> None:
        if n.kind:
            kinds.add(n.kind)
        if d is not None and d <= 0:
            return
        for c in n.children:
            collect(c, None if d is None else d - 1)

    collect(node, depth)
    voc = {k.kind: k.model_dump(exclude_defaults=True)
           for k in scene.vocabulary if k.kind in kinds}
    rules = [r.model_dump(exclude_none=True) for r in scene.rules
             if (r.kind in kinds if r.kind is not None else
                 (r.path or "").startswith(path) or path.startswith(r.path or ""))]
    out: dict[str, Any] = {}
    if voc:
        out["kinds"] = voc
    if rules:
        out["rules"] = rules
    undefined = sorted(k for k in kinds if k not in voc)
    if undefined:
        out["undefined_kinds"] = undefined  # meaning nobody wrote down yet
    return out


def set_node(scene: Scene, path: str, data: dict[str, Any]) -> Node:
    """Create or update the node at `path`. Given fields replace those fields
    (children included — edit a child by addressing it, not by resending lists);
    missing intermediate nodes are created as bare groups."""
    segs = _segs(path)
    if not segs:
        raise ValueError("the root is not editable — address a child path")
    node = scene.root
    for seg in segs[:-1]:
        nxt = node.child(seg)
        if nxt is None:
            nxt = Node(id=seg)
            node.children.append(nxt)
        node = nxt
    leaf = node.child(segs[-1])
    data = dict(data)
    data.pop("id", None)  # the path names the node; ids inside payloads are noise
    if leaf is None:
        leaf = Node(id=segs[-1], **data)
        node.children.append(leaf)
    else:
        patched = leaf.model_copy(update={
            k: _coerce(Node, k, v) for k, v in data.items()})
        node.children[node.children.index(leaf)] = patched
        leaf = patched
    return leaf


def delete_node(scene: Scene, path: str) -> Node:
    segs = _segs(path)
    if not segs:
        raise ValueError("the root is not deletable")
    parent = get_node(scene, "/".join(segs[:-1]))
    target = parent.child(segs[-1]) if parent is not None else None
    if target is None:
        raise ValueError(f"no node at '{path}'")
    parent.children.remove(target)
    return target


def _segs(path: str) -> list[str]:
    return [s for s in (path or "").split("/") if s]


def _coerce(model: type[BaseModel], field: str, value: Any) -> Any:
    """Validate one field's payload through the model so dicts become models."""
    if value is None:
        return None
    return model.__pydantic_validator__.validate_assignment(
        model.model_construct(), field, value).__dict__[field]


# --- parameter resolution (BOM-style: nearest ancestor wins) -------------------

def resolve(value: float | str | None, chain: list[Node]) -> float | None:
    """A shape argument is a number, or the name of a param found by walking the
    ancestor chain from the node outwards."""
    if value is None or isinstance(value, (int, float)):
        return None if value is None else float(value)
    for node in reversed(chain):
        q = node.params.get(value)
        if q is not None:
            return q.value
    raise ValueError(f"unknown parameter '{value}' on '{'/'.join(n.id for n in chain)}'")


# --- realization: tree -> world-space solids -----------------------------------

class SolidView(BaseModel):
    """One realized solid: a vertical extrusion in world space, tagged add|cut.

    `dims` are the solid's own [w, d, h] in its local frame — what you would cut
    it to. The world-space footprint places it; the dims size it: a rotated panel
    keeps its true dimensions no matter how it sits in the scene.
    """

    path: str
    kind: str
    footprint: list[list[float]]  # world-space polygon, mm
    z0: float
    z1: float
    dims: list[float]  # local [w, d, h] mm
    role: str  # add | cut
    mesh: str | None = None  # mesh solids carry their uri; drawn as a labelled box


def realize(scene: Scene, path: str = "") -> list[SolidView]:
    """Flatten a subtree into world-space solids for rendering and checks."""
    start = get_node(scene, path)
    if start is None:
        raise ValueError(f"no node at '{path}'")
    chain_to_start: list[Node] = [scene.root]
    for seg in _segs(path):
        chain_to_start.append(chain_to_start[-1].child(seg))
    out: list[SolidView] = []
    _walk(chain_to_start, _base_pose(chain_to_start[:-1]), "add", path, out)
    return out


Pose = tuple[float, float, float, float]  # x, y, z, rotation rad


def _base_pose(ancestors: list[Node]) -> Pose:
    pose: Pose = (0.0, 0.0, 0.0, 0.0)
    for node in ancestors:
        pose = _compose(pose, node.transform)
    return pose


def _compose(pose: Pose, t: Transform | None) -> Pose:
    if t is None:
        return pose
    x, y, z, a = pose
    dx, dy, dz = t.translate
    ca, sa = math.cos(a), math.sin(a)
    return (x + dx * ca - dy * sa, y + dx * sa + dy * ca, z + dz,
            a + math.radians(t.rotate_z_deg))


def _walk(chain: list[Node], parent_pose: Pose, role: str, path: str,
          out: list[SolidView]) -> None:
    node = chain[-1]
    pose = _compose(parent_pose, node.transform)
    s = node.shape
    boolean = s is not None and s.op in ("union", "difference", "intersection")
    if s is not None and not boolean:
        solid = _primitive(chain, s, pose, role, path)
        if solid is not None:
            out.append(solid)
    for i, c in enumerate(node.children):
        child_role = role
        if boolean and s.op == "difference" and i > 0:
            child_role = "cut" if role == "add" else "add"
        _walk([*chain, c], pose, child_role,
              f"{path}/{c.id}" if path else c.id, out)


def _primitive(chain: list[Node], s: Shape, pose: Pose, role: str,
               path: str) -> SolidView | None:
    node = chain[-1]
    x, y, z, a = pose

    def place(pts: list[list[float]]) -> list[list[float]]:
        ca, sa = math.cos(a), math.sin(a)
        return [[x + px * ca - py * sa, y + px * sa + py * ca] for px, py in pts]

    if s.op == "box":
        if not s.size or len(s.size) != 3:
            raise ValueError(f"box at '{path}' needs size [w, d, h]")
        w, d, h = (resolve(v, chain) for v in s.size)
        return SolidView(path=path, kind=node.kind, role=role,
                         footprint=place([[0, 0], [w, 0], [w, d], [0, d]]),
                         z0=z, z1=z + h, dims=[w, d, h])
    if s.op == "prism":
        if not s.polygon or len(s.polygon) < 3 or s.height is None:
            raise ValueError(f"prism at '{path}' needs polygon (>=3) + height")
        h = resolve(s.height, chain)
        local = [[float(px), float(py)] for px, py in s.polygon]
        lw = max(p[0] for p in local) - min(p[0] for p in local)
        ld = max(p[1] for p in local) - min(p[1] for p in local)
        return SolidView(path=path, kind=node.kind, role=role,
                         footprint=place(local),
                         z0=z, z1=z + h, dims=[lw, ld, h])
    if s.op == "cylinder":
        if s.diameter is None or s.height is None:
            raise ValueError(f"cylinder at '{path}' needs diameter + height")
        dia, h = resolve(s.diameter, chain), resolve(s.height, chain)
        r = dia / 2
        pts = [[r + r * math.cos(t), r + r * math.sin(t)]
               for t in (k * math.tau / 24 for k in range(24))]
        return SolidView(path=path, kind=node.kind, role=role,
                         footprint=place(pts), z0=z, z1=z + h, dims=[dia, dia, h])
    if s.op == "mesh":
        size = s.size or [100, 100, 100]
        w, d, h = (resolve(v, chain) for v in size)
        return SolidView(path=path, kind=node.kind, role=role, mesh=s.uri,
                         footprint=place([[0, 0], [w, 0], [w, d], [0, d]]),
                         z0=z, z1=z + h, dims=[w, d, h])
    raise ValueError(f"unknown shape op '{s.op}' at '{path}'")


# --- checks: the solver plug-point ---------------------------------------------

def bbox(solids: list[SolidView]) -> dict[str, list[float]] | None:
    adds = [s for s in solids if s.role == "add"]
    if not adds:
        return None
    xs = [p[0] for s in adds for p in s.footprint]
    ys = [p[1] for s in adds for p in s.footprint]
    zs = [v for s in adds for v in (s.z0, s.z1)]
    return {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}


def volume_mm3(solids: list[SolidView]) -> float:
    """Signed sum of extrusion volumes (cuts subtract; overlaps not resolved —
    an estimate for sanity checks, not a metrology result)."""
    total = 0.0
    for s in solids:
        area = abs(_shoelace(s.footprint))
        v = area * (s.z1 - s.z0)
        total += v if s.role == "add" else -v
    return total


def clearance_mm(a: list[SolidView], b: list[SolidView]) -> float:
    """Minimum bbox distance between two realized branches (0 = touch/overlap)."""
    ba, bb = bbox(a), bbox(b)
    if ba is None or bb is None:
        raise ValueError("empty branch")
    gaps = []
    for i in range(3):
        gaps.append(max(ba["min"][i] - bb["max"][i], bb["min"][i] - ba["max"][i], 0.0))
    return math.hypot(math.hypot(gaps[0], gaps[1]), gaps[2])


def _shoelace(pts: list[list[float]]) -> float:
    n = len(pts)
    return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
               for i in range(n)) / 2


# --- render: orthographic views to PNG ------------------------------------------

VIEWS = ("top", "front", "left")
_ADD = (61, 149, 232)     # solid outline
_CUT = (207, 148, 48)     # dashed outline: a cut
_TEXT = (92, 103, 118)
_BG = (255, 255, 255)


def render_png(solids: list[SolidView], views: list[str], px: int = 480) -> bytes:
    """The requested orthographic views side by side, as one PNG.

    Every solid here is a vertical extrusion, so top is exact and front/left are
    exact silhouettes (x- or y-extent × height). Cuts draw dashed. This is the
    fast preview loop; kernel-fidelity booleans arrive with the CAD phase.
    """
    from PIL import Image, ImageDraw

    views = [v for v in views if v in VIEWS] or ["top"]
    pad = 24
    panels = []
    for view in views:
        polys = [(s, _project(s, view)) for s in solids]
        pts = [p for _, poly in polys for p in poly]
        if not pts:
            continue
        min_x, max_x = min(p[0] for p in pts), max(p[0] for p in pts)
        min_y, max_y = min(p[1] for p in pts), max(p[1] for p in pts)
        w, h = max(max_x - min_x, 1), max(max_y - min_y, 1)
        scale = (px - 2 * pad) / max(w, h)
        pw, ph = int(w * scale) + 2 * pad, int(h * scale) + 2 * pad + 18
        img = Image.new("RGB", (pw, ph), _BG)
        drw = ImageDraw.Draw(img)
        drw.text((pad, 2), view, fill=_TEXT)
        for s, poly in polys:
            xy = [(pad + (p[0] - min_x) * scale, ph - pad - (p[1] - min_y) * scale)
                  for p in poly]
            if s.role == "add":
                drw.polygon(xy, outline=_ADD)
            else:
                _dashed(drw, xy, _CUT)
        panels.append(img)

    if not panels:
        img = Image.new("RGB", (240, 60), _BG)
        ImageDraw.Draw(img).text((10, 20), "nothing to render", fill=_TEXT)
        panels = [img]
    total_w = sum(p.width for p in panels) + 8 * (len(panels) - 1)
    total_h = max(p.height for p in panels)
    sheet = Image.new("RGB", (total_w, total_h), _BG)
    cx = 0
    for p in panels:
        sheet.paste(p, (cx, 0))
        cx += p.width + 8
    buf = io.BytesIO()
    sheet.save(buf, format="PNG")
    return buf.getvalue()


def _project(s: SolidView, view: str) -> list[list[float]]:
    if view == "top":
        return s.footprint
    xs = [p[0] for p in s.footprint]
    ys = [p[1] for p in s.footprint]
    lo, hi = (min(xs), max(xs)) if view == "front" else (min(ys), max(ys))
    return [[lo, s.z0], [hi, s.z0], [hi, s.z1], [lo, s.z1]]


# --- perspective: the caller owns the viewpoint ---------------------------------

def render_perspective_png(
    solids: list[SolidView],
    eye: list[float] | None = None,
    look_at: list[float] | None = None,
    fov_deg: float = 50.0,
    px: int = 640,
) -> bytes:
    """A pinhole-camera wireframe of the solids, seen from where the caller says.

    `eye` and `look_at` are [x, y, z] mm in the scene frame; when omitted, the
    camera backs away from the bounding box along a corner direction so something
    sensible appears, but the point of this renderer is that the viewpoint is
    *yours*. Solids draw as their extrusion edges; cuts draw dashed. Geometry
    behind the camera is clipped, not guessed.
    """
    from PIL import Image, ImageDraw

    centre, radius = _scene_sphere(solids)
    if look_at is None:
        look_at = centre
    if eye is None:
        k = radius * 2.2 / math.sqrt(3)
        eye = [centre[0] + k, centre[1] - k, centre[2] + k * 0.9]

    fwd = _norm3([look_at[i] - eye[i] for i in range(3)])
    if fwd is None:
        raise ValueError("eye and look_at coincide — nothing to look at")
    up = [0.0, 0.0, 1.0]
    right = _norm3(_cross(fwd, up)) or [1.0, 0.0, 0.0]  # looking straight up/down
    up2 = _cross(right, fwd)
    focal = 1.0 / math.tan(math.radians(max(min(fov_deg, 160.0), 5.0)) / 2)
    near = 10.0  # mm

    def to_cam(p: list[float]) -> tuple[float, float, float]:
        d = [p[i] - eye[i] for i in range(3)]
        return (sum(d[i] * right[i] for i in range(3)),
                sum(d[i] * up2[i] for i in range(3)),
                sum(d[i] * fwd[i] for i in range(3)))

    segments: list[tuple[tuple, tuple, str]] = []
    for s in solids:
        pts = s.footprint
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            for z in (s.z0, s.z1):  # bottom and top rings
                segments.append(((a[0], a[1], z), (b[0], b[1], z), s.role))
            segments.append(((a[0], a[1], s.z0), (a[0], a[1], s.z1), s.role))

    projected: list[tuple[tuple, tuple, str]] = []
    for a, b, role in segments:
        ca, cb = to_cam(list(a)), to_cam(list(b))
        clipped = _clip_near(ca, cb, near)
        if clipped is None:
            continue
        ca, cb = clipped
        projected.append((
            (ca[0] / ca[2] * focal, ca[1] / ca[2] * focal),
            (cb[0] / cb[2] * focal, cb[1] / cb[2] * focal), role))

    img_pad = 20
    if not projected:
        img = Image.new("RGB", (240, 60), _BG)
        ImageDraw.Draw(img).text((10, 20), "nothing in view", fill=_TEXT)
    else:
        xs = [v for a, b, _ in projected for v in (a[0], b[0])]
        ys = [v for a, b, _ in projected for v in (a[1], b[1])]
        w, h = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
        scale = (px - 2 * img_pad) / max(w, h)
        pw = int(w * scale) + 2 * img_pad
        ph = int(h * scale) + 2 * img_pad
        img = Image.new("RGB", (pw, ph), _BG)
        drw = ImageDraw.Draw(img)
        for a, b, role in projected:
            xy = [(img_pad + (a[0] - min(xs)) * scale, ph - img_pad - (a[1] - min(ys)) * scale),
                  (img_pad + (b[0] - min(xs)) * scale, ph - img_pad - (b[1] - min(ys)) * scale)]
            if role == "add":
                drw.line(xy, fill=_ADD)
            else:
                _dashed_line(drw, xy[0], xy[1], _CUT)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _scene_sphere(solids: list[SolidView]) -> tuple[list[float], float]:
    pts = [[p[0], p[1], z] for s in solids for p in s.footprint for z in (s.z0, s.z1)]
    if not pts:
        return [0.0, 0.0, 0.0], 1000.0
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
    radius = max(math.dist(centre, p) for p in pts) or 1000.0
    return centre, radius


def _norm3(v: list[float]) -> list[float] | None:
    n = math.sqrt(sum(x * x for x in v))
    return None if n < 1e-9 else [x / n for x in v]


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _clip_near(a: tuple, b: tuple, near: float):
    """Clip a camera-space segment to the near plane (z >= near)."""
    if a[2] < near and b[2] < near:
        return None
    if a[2] >= near and b[2] >= near:
        return a, b
    t = (near - a[2]) / (b[2] - a[2])
    cut = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
    return (cut, b) if a[2] < near else (a, cut)


def _dashed_line(drw, a, b, color, dash: int = 5) -> None:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    steps = max(int(length / dash), 1)
    for k in range(0, steps, 2):
        t1, t2 = k / steps, min((k + 1) / steps, 1.0)
        drw.line([(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1),
                  (a[0] + (b[0] - a[0]) * t2, a[1] + (b[1] - a[1]) * t2)], fill=color)


# --- the rule language: solvers as data, evaluated safely -----------------------
#
# A tiny recursive-descent evaluator instead of eval(): rules come from clients at
# runtime on a multi-tenant server, so they get arithmetic, comparisons, booleans,
# string literals and a fixed set of geometry functions — nothing else.

class RuleResult(BaseModel):
    rule: str
    node: str  # the path the rule ran against ("" = global)
    ok: bool
    detail: str = ""


def run_rules(scene: Scene, path: str = "") -> list[RuleResult]:
    """Evaluate every rule that applies at or under `path`."""
    out: list[RuleResult] = []
    for rule in scene.rules:
        for node_path, variables in _rule_bindings(scene, rule, path):
            try:
                value = _eval_expr(rule.expr, _env(scene), variables)
                out.append(RuleResult(rule=rule.name, node=node_path, ok=bool(value)))
            except Exception as e:  # a broken rule must report, not crash the check
                out.append(RuleResult(rule=rule.name, node=node_path, ok=False,
                                      detail=str(e)))
    return out


def _rule_bindings(scene: Scene, rule: Rule, under: str):
    """(path, variables) pairs the rule evaluates against."""
    if rule.kind is not None:
        for node_path, node in _iter_paths(scene.root, ""):
            if node.kind == rule.kind and node_path.startswith(under):
                variables = {k: q.value for k, q in node.params.items()}
                variables["self"] = node_path
                yield node_path, variables
    else:
        target = rule.path or ""
        if target.startswith(under) or under.startswith(target):
            node = get_node(scene, target)
            variables = ({k: q.value for k, q in node.params.items()}
                         if node is not None else {})
            variables["self"] = target
            yield target, variables


def _iter_paths(node: Node, path: str):
    for c in node.children:
        cpath = f"{path}/{c.id}" if path else c.id
        yield cpath, c
        yield from _iter_paths(c, cpath)


def _env(scene: Scene) -> dict[str, Any]:
    def solids(p: str) -> list[SolidView]:
        return realize(scene, p)

    def _bb(p: str) -> dict[str, list[float]]:
        b = bbox(solids(p))
        if b is None:
            raise ValueError(f"'{p}' has no solids")
        return b

    return {
        "volume": lambda p: volume_mm3(solids(p)),
        "bbox_w": lambda p: _bb(p)["max"][0] - _bb(p)["min"][0],
        "bbox_d": lambda p: _bb(p)["max"][1] - _bb(p)["min"][1],
        "bbox_h": lambda p: _bb(p)["max"][2] - _bb(p)["min"][2],
        "z_min": lambda p: _bb(p)["min"][2],
        "z_max": lambda p: _bb(p)["max"][2],
        "clearance": lambda a, b: clearance_mm(solids(a), solids(b)),
        "count": lambda p: len((get_node(scene, p) or Node(id="_")).children),
        "param": lambda p, name: _param_of(scene, p, name),
        "abs": abs, "min": min, "max": max,
    }


def _param_of(scene: Scene, path: str, name: str) -> float:
    node = get_node(scene, path)
    if node is None or name not in node.params:
        raise ValueError(f"no param '{name}' at '{path}'")
    return node.params[name].value


def _eval_expr(src: str, env: dict[str, Any], variables: dict[str, Any]) -> Any:
    tokens = _tokenize(src)
    value, pos = _parse_or(tokens, 0, env, variables)
    if pos != len(tokens):
        raise ValueError(f"unexpected '{tokens[pos][1]}'")
    return value


def _tokenize(src: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
        elif c.isdigit() or (c == "." and i + 1 < len(src) and src[i + 1].isdigit()):
            j = i
            while j < len(src) and (src[j].isdigit() or src[j] == "."):
                j += 1
            out.append(("num", float(src[i:j])))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            out.append(("name", src[i:j]))
            i = j
        elif c in "'\"":
            j = src.find(c, i + 1)
            if j < 0:
                raise ValueError("unterminated string")
            out.append(("str", src[i + 1:j]))
            i = j + 1
        elif src[i:i + 2] in ("<=", ">=", "==", "!="):
            out.append(("op", src[i:i + 2]))
            i += 2
        elif c in "+-*/<>(),":
            out.append(("op", c))
            i += 1
        else:
            raise ValueError(f"bad character '{c}'")
    return out


def _parse_or(toks, i, env, var):
    v, i = _parse_and(toks, i, env, var)
    while i < len(toks) and toks[i] == ("name", "or"):
        r, i = _parse_and(toks, i + 1, env, var)
        v = bool(v) or bool(r)
    return v, i


def _parse_and(toks, i, env, var):
    v, i = _parse_not(toks, i, env, var)
    while i < len(toks) and toks[i] == ("name", "and"):
        r, i = _parse_not(toks, i + 1, env, var)
        v = bool(v) and bool(r)
    return v, i


def _parse_not(toks, i, env, var):
    if i < len(toks) and toks[i] == ("name", "not"):
        v, i = _parse_not(toks, i + 1, env, var)
        return not bool(v), i
    return _parse_cmp(toks, i, env, var)


def _parse_cmp(toks, i, env, var):
    v, i = _parse_sum(toks, i, env, var)
    if i < len(toks) and toks[i][0] == "op" and toks[i][1] in ("<", "<=", ">", ">=", "==", "!="):
        op = toks[i][1]
        r, i = _parse_sum(toks, i + 1, env, var)
        v = {"<": v < r, "<=": v <= r, ">": v > r, ">=": v >= r,
             "==": v == r, "!=": v != r}[op]
    return v, i


def _parse_sum(toks, i, env, var):
    v, i = _parse_term(toks, i, env, var)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "+-":
        op = toks[i][1]
        r, i = _parse_term(toks, i + 1, env, var)
        v = v + r if op == "+" else v - r
    return v, i


def _parse_term(toks, i, env, var):
    v, i = _parse_unary(toks, i, env, var)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "*/":
        op = toks[i][1]
        r, i = _parse_unary(toks, i + 1, env, var)
        v = v * r if op == "*" else v / r
    return v, i


def _parse_unary(toks, i, env, var):
    if i < len(toks) and toks[i] == ("op", "-"):
        v, i = _parse_unary(toks, i + 1, env, var)
        return -v, i
    return _parse_atom(toks, i, env, var)


def _parse_atom(toks, i, env, var):
    if i >= len(toks):
        raise ValueError("unexpected end of expression")
    kind, val = toks[i]
    if kind in ("num", "str"):
        return val, i + 1
    if kind == "op" and val == "(":
        v, i = _parse_or(toks, i + 1, env, var)
        if i >= len(toks) or toks[i] != ("op", ")"):
            raise ValueError("missing ')'")
        return v, i + 1
    if kind == "name":
        if i + 1 < len(toks) and toks[i + 1] == ("op", "("):
            fn = env.get(val)
            if fn is None:
                raise ValueError(f"unknown function '{val}'")
            args = []
            i += 2
            if toks[i] != ("op", ")"):
                while True:
                    a, i = _parse_or(toks, i, env, var)
                    args.append(a)
                    if i < len(toks) and toks[i] == ("op", ","):
                        i += 1
                        continue
                    break
            if i >= len(toks) or toks[i] != ("op", ")"):
                raise ValueError("missing ')'")
            return fn(*args), i + 1
        if val in var:
            return var[val], i + 1
        raise ValueError(f"unknown name '{val}'")
    raise ValueError(f"unexpected '{val}'")


def _dashed(drw, xy: list[tuple[float, float]], color, dash: int = 5) -> None:
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(int(length / dash), 1)
        for k in range(0, steps, 2):
            t1, t2 = k / steps, min((k + 1) / steps, 1.0)
            drw.line([(x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1),
                      (x1 + (x2 - x1) * t2, y1 + (y2 - y1) * t2)], fill=color)
