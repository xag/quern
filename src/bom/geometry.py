"""geometry — the first standard domain package, a consumer of the core.

Nothing here is privileged: the core substrate assigns no meaning to a node's
`payload`; this package is what interprets a `shape` payload (box/prism/cylinder/
mesh + booleans) and a `transform` payload (translate mm, rotate about z) into
world-space solids, renders them, and measures them. Its functions register as the
native implementations of the `geometry/…` contracts the rule language reaches with
solve(). A custom or shared WASM module honouring the same contracts could replace
them; if a native disagrees with the contract, the native is the bug.

mm, z-up: conventions of THIS package, documented in GEOMETRY_PACKAGE — never of
the substrate.
"""

from __future__ import annotations

import io
import math
from typing import Any

from pydantic import BaseModel, Field

from .library import Package
from .tree import Node, Bom, get_node, register_native, _segs
from .solver import SolverDef


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
    size: list[float | str] | None = None
    polygon: list[list[float]] | None = None
    height: float | str | None = None
    diameter: float | str | None = None
    uri: str | None = None


def _shape_of(node: Node) -> Shape | None:
    d = node.payload.get("shape")
    return Shape.model_validate(d) if d else None


def _transform_of(node: Node) -> Transform | None:
    d = node.payload.get("transform")
    return Transform.model_validate(d) if d else None


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
    keeps its true dimensions no matter how it sits in the tree.
    """

    path: str
    kind: str
    footprint: list[list[float]]
    z0: float
    z1: float
    dims: list[float]
    role: str  # add | cut
    mesh: str | None = None


Pose = tuple[float, float, float, float]  # x, y, z, rotation rad


def realize(tree: Bom, path: str = "") -> list[SolidView]:
    """Flatten a subtree into world-space solids for rendering and checks."""
    start = get_node(tree, path)
    if start is None:
        raise ValueError(f"no node at '{path}'")
    chain_to_start: list[Node] = [tree.root]
    for seg in _segs(path):
        chain_to_start.append(chain_to_start[-1].child(seg))
    out: list[SolidView] = []
    _walk(chain_to_start, _base_pose(chain_to_start[:-1]), "add", path, out)
    return out


def _base_pose(ancestors: list[Node]) -> Pose:
    pose: Pose = (0.0, 0.0, 0.0, 0.0)
    for node in ancestors:
        pose = _compose(pose, _transform_of(node))
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
    pose = _compose(parent_pose, _transform_of(node))
    s = _shape_of(node)
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


# --- checks ---------------------------------------------------------------------

def bbox(solids: list[SolidView]) -> dict[str, list[float]] | None:
    adds = [s for s in solids if s.role == "add"]
    if not adds:
        return None
    xs = [p[0] for s in adds for p in s.footprint]
    ys = [p[1] for s in adds for p in s.footprint]
    zs = [v for s in adds for v in (s.z0, s.z1)]
    return {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}


def volume(solids: list[SolidView]) -> float:
    """Signed sum of extrusion volumes (cuts subtract; overlaps not resolved —
    an estimate for sanity checks, not a metrology result)."""
    total = 0.0
    for s in solids:
        area = abs(_shoelace(s.footprint))
        v = area * (s.z1 - s.z0)
        total += v if s.role == "add" else -v
    return total


def clearance(a: list[SolidView], b: list[SolidView]) -> float:
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


# --- render ---------------------------------------------------------------------

VIEWS = ("top", "front", "left")
_ADD = (61, 149, 232)
_CUT = (207, 148, 48)
_TEXT = (92, 103, 118)
_BG = (255, 255, 255)


def render_png(solids: list[SolidView], views: list[str], px: int = 480) -> bytes:
    """The requested orthographic views side by side, as one PNG (flat drafting
    projections; use render_perspective_png for a chosen viewpoint)."""
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


def render_perspective_png(
    solids: list[SolidView],
    eye: list[float] | None = None,
    look_at: list[float] | None = None,
    fov_deg: float = 50.0,
    px: int = 640,
) -> bytes:
    """A pinhole-camera wireframe of the solids, seen from where the caller says.

    `eye` and `look_at` are [x, y, z] mm in the tree frame; when omitted, the
    camera backs away from the bounding box along a corner direction. Solids draw
    as their extrusion edges; cuts dashed; geometry behind the camera is clipped.
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
    right = _norm3(_cross(fwd, up)) or [1.0, 0.0, 0.0]
    up2 = _cross(right, fwd)
    focal = 1.0 / math.tan(math.radians(max(min(fov_deg, 160.0), 5.0)) / 2)
    near = 10.0

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
            for z in (s.z0, s.z1):
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
    if a[2] < near and b[2] < near:
        return None
    if a[2] >= near and b[2] >= near:
        return a, b
    t = (near - a[2]) / (b[2] - a[2])
    cut = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
    return (cut, b) if a[2] < near else (a, cut)


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


def _dashed_line(drw, a, b, color, dash: int = 5) -> None:
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    steps = max(int(length / dash), 1)
    for k in range(0, steps, 2):
        t1, t2 = k / steps, min((k + 1) / steps, 1.0)
        drw.line([(a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1),
                  (a[0] + (b[0] - a[0]) * t2, a[1] + (b[1] - a[1]) * t2)], fill=color)


# --- standard registration: geometry as content, natives as accelerators --------

def _bb(tree: Bom, p: str) -> dict:
    b = bbox(realize(tree, p))
    if b is None:
        raise ValueError(f"'{p}' has no solids")
    return b


GEOMETRY_NATIVES = {
    "geometry/volume": lambda tree, p: volume(realize(tree, p)),
    "geometry/bbox_w": lambda tree, p: _bb(tree, p)["max"][0] - _bb(tree, p)["min"][0],
    "geometry/bbox_d": lambda tree, p: _bb(tree, p)["max"][1] - _bb(tree, p)["min"][1],
    "geometry/bbox_h": lambda tree, p: _bb(tree, p)["max"][2] - _bb(tree, p)["min"][2],
    "geometry/z_min": lambda tree, p: _bb(tree, p)["min"][2],
    "geometry/z_max": lambda tree, p: _bb(tree, p)["max"][2],
    "geometry/clearance": lambda tree, a, b: clearance(realize(tree, a),
                                                        realize(tree, b)),
}


def register_standard() -> None:
    for name, fn in GEOMETRY_NATIVES.items():
        register_native(name, fn)


from .tree import KindDef  # noqa: E402  (kept below the natives for readability)

GEOMETRY_PACKAGE = Package(
    name="geometry",
    version="1.0.0",
    description="Shape conventions (box/prism/cylinder/mesh + booleans over "
                "children, mm, z-up) carried in a node's payload, and the solver "
                "contracts the rule language reaches with solve('geometry/…', path): "
                "volume, bbox_w/d/h, z_min/z_max, clearance(a, b). Implemented "
                "natively here; any module honouring the same contracts may replace "
                "it.",
    publisher="standard library",
    vocabulary=[
        KindDef(kind="geometry", description="Convention pack, not a node kind: a "
                "node gets a solid by carrying a shape payload — box {size [w,d,h]}, "
                "prism {polygon, height}, cylinder {diameter, height}, mesh {uri}, "
                "union/difference/intersection over children. Vertical extrusions, "
                "mm, z up."),
    ],
    solvers=[
        SolverDef(name=name, native=True,
                  description="standard geometry contract; see the package description",
                  reads=[""])
        for name in GEOMETRY_NATIVES
    ],
)
