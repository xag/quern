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

import colorsys
import hashlib
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


def _parent(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else ""


def _ccw(pts: list[list[float]]) -> list[list[float]]:
    return pts if _shoelace(pts) > 0 else list(reversed(pts))


def evaluate(solids: list[SolidView]) -> list[SolidView]:
    """Resolve the cuts: turn stock-and-holes into the solid that is actually there.

    `realize` flattens a boolean into its operands — one `add` and its `cut`s, side by
    side — because that is enough to measure with and to draw as a wireframe. It is not
    enough to *see*: a door drawn as a dashed box is not a doorway, and a wall you cannot
    see through is not a wall with a door in it.

    Everything here is a vertical extrusion, which makes the boolean exact and cheap: cut
    the z-range into slabs at every operand's floor and ceiling, and inside a slab the
    problem is two-dimensional. Subtract the polygons, re-extrude, done. No B-rep kernel,
    no approximation.

    A cut only bites its own siblings — the operands of one `difference` node — so a hole
    in one wall cannot punch through another that happens to stand in the same place.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    adds = [s for s in solids if s.role == "add"]
    cuts = [s for s in solids if s.role == "cut"]
    if not cuts:
        return adds

    out: list[SolidView] = []
    for a in adds:
        mine = [c for c in cuts if _parent(c.path) == _parent(a.path)]
        if not mine:
            out.append(a)
            continue
        breaks = sorted({a.z0, a.z1} | {z for c in mine for z in (c.z0, c.z1)
                                        if a.z0 < z < a.z1})
        stock = Polygon(a.footprint)
        if not stock.is_valid:
            stock = stock.buffer(0)
        for lo, hi in zip(breaks, breaks[1:]):
            here = [c for c in mine if c.z0 < hi and c.z1 > lo]  # active in this slab
            shape = stock
            if here:
                holes = unary_union([Polygon(c.footprint).buffer(0) for c in here])
                shape = stock.difference(holes)
            if shape.is_empty:
                continue
            pieces = getattr(shape, "geoms", [shape])
            for piece in pieces:
                if piece.is_empty or piece.area <= 0:
                    continue
                ring = [[float(x), float(y)] for x, y in piece.exterior.coords[:-1]]
                if len(ring) < 3:
                    continue
                out.append(SolidView(path=a.path, kind=a.kind, footprint=_ccw(ring),
                                     z0=lo, z1=hi, dims=a.dims, role="add",
                                     mesh=a.mesh))
    return out


def contains(outer: list[SolidView], inner: list[SolidView], tol: float = 0.0) -> bool:
    """Is `inner`'s bounding box within `outer`'s, allowing `tol` of overhang?

    Bounding boxes, so this is an enclosure *screen*, not a proof — it catches the
    thing that is somewhere else entirely, which is the mistake worth catching. The
    tolerance is what lets a feature sit ON a face (straddling it) and still count
    as belonging to the body.
    """
    bo, bi = bbox(outer), bbox(inner)
    if bo is None or bi is None:
        raise ValueError("empty branch")
    return all(bi["min"][i] >= bo["min"][i] - tol and bi["max"][i] <= bo["max"][i] + tol
               for i in range(3))


def overlap(a: list[SolidView], b: list[SolidView]) -> float:
    """Volume of the bounding-box intersection (0 = disjoint). Two bodies that must
    not occupy the same space — rooms, parts — are wrong the moment this is > 0."""
    ba, bb = bbox(a), bbox(b)
    if ba is None or bb is None:
        raise ValueError("empty branch")
    dims = [max(0.0, min(ba["max"][i], bb["max"][i]) - max(ba["min"][i], bb["min"][i]))
            for i in range(3)]
    return dims[0] * dims[1] * dims[2]


def shared_edge(a: list[SolidView], b: list[SolidView], tol: float = 1.0) -> float:
    """Length of boundary the two branches actually share, in plan.

    NOT bbox distance. Two bodies stacked apart can have a bbox clearance of zero
    while sharing no boundary at all — so `clearance(a, b) == 0` is no evidence that
    they adjoin, and a survey that claims they do can be wrong in exactly that way.
    This walks the footprint edges and sums the length over which an edge of `a` is
    collinear with an edge of `b` (within `tol`) and overlaps it. Solids whose
    z-ranges do not overlap share nothing.
    """
    total = 0.0
    for sa in (s for s in a if s.role == "add"):
        for sb in (s for s in b if s.role == "add"):
            if min(sa.z1, sb.z1) - max(sa.z0, sb.z0) <= 0:
                continue  # different storeys: no shared wall
            for ea in _edges(sa.footprint):
                for eb in _edges(sb.footprint):
                    total += _collinear_overlap(ea, eb, tol)
    return total


def _edges(pts: list[list[float]]) -> list[tuple[list[float], list[float]]]:
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n)]


def _collinear_overlap(ea, eb, tol: float) -> float:
    """Length over which two segments lie on the same line (within tol) and overlap."""
    (a0, a1), (b0, b1) = ea, eb
    dx, dy = a1[0] - a0[0], a1[1] - a0[1]
    length = math.hypot(dx, dy)
    if length < tol:
        return 0.0
    ux, uy = dx / length, dy / length
    # both of b's endpoints must sit on a's line (perpendicular distance within tol)
    for p in (b0, b1):
        if abs(-uy * (p[0] - a0[0]) + ux * (p[1] - a0[1])) > tol:
            return 0.0
    # project onto a's direction and intersect the two intervals
    tb = sorted(ux * (p[0] - a0[0]) + uy * (p[1] - a0[1]) for p in (b0, b1))
    lo, hi = max(0.0, tb[0]), min(length, tb[1])
    return max(0.0, hi - lo)


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


def render(solids: list[SolidView], views: list[str], px: int = 480,
           fmt: str = "png") -> bytes:
    """The requested orthographic views side by side (flat drafting projections;
    use render_perspective for a chosen viewpoint). `fmt` is the encoding — a data
    argument, not a name: "png" today, the seam where svg/others would slot in."""
    if fmt != "png":
        raise ValueError(f"unsupported render format '{fmt}' — only 'png' so far")
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


_SURFACE = (214, 219, 226)   # what a kindless solid is made of
_EDGE = (108, 118, 132)
_L = math.sqrt(0.4 ** 2 + 0.7 ** 2 + 0.9 ** 2)
_LIGHT = [-0.4 / _L, -0.7 / _L, 0.9 / _L]   # a key light over the viewer's left shoulder


def _kind_colour(kind: str) -> tuple[int, int, int]:
    """A muted, stable colour per kind — so a shelf does not look like the wall behind it.

    Derived from the kind's own name, not from a table: the substrate has no list of kinds
    to consult, and a domain that invents one at runtime gets a colour for it immediately.
    Same name, same colour, every render.
    """
    if not kind:
        return _SURFACE
    hue = (int(hashlib.sha1(kind.encode()).hexdigest()[:8], 16) % 360) / 360.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.74, 0.34)   # light and unsaturated: it is a hint
    return (int(r * 255), int(g * 255), int(b * 255))


def _faces(s: SolidView) -> list[tuple[list[list[float]], list[float]]]:
    """An extrusion's faces, each with its outward normal."""
    pts = _ccw(s.footprint)
    n = len(pts)
    out = [([[p[0], p[1], s.z1] for p in pts], [0.0, 0.0, 1.0]),
           ([[p[0], p[1], s.z0] for p in reversed(pts)], [0.0, 0.0, -1.0])]
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        normal = _norm3([dy, -dx, 0.0])  # CCW ring: outward is to the right of the edge
        if normal is None:
            continue
        out.append(([[a[0], a[1], s.z0], [b[0], b[1], s.z0],
                     [b[0], b[1], s.z1], [a[0], a[1], s.z1]], normal))
    return out


def render_perspective(
    solids: list[SolidView],
    eye: list[float] | None = None,
    look_at: list[float] | None = None,
    fov_deg: float = 50.0,
    px: int = 640,
    fmt: str = "png",
    style: str = "wire",
) -> bytes:
    """A pinhole camera on the solids, seen from where the caller says.

    `eye` and `look_at` are [x, y, z] mm in the tree frame; when omitted, the camera
    backs away from the bounding box along a corner direction. Geometry behind the
    camera is clipped. `fmt` is the encoding (data, not a name): "png" today.

    `style` is 'wire' — extrusion edges, cuts dashed, everything visible through
    everything — or 'solid': filled faces, back faces culled, drawn far-to-near so
    surfaces occlude, and the booleans EVALUATED so a hole is an absence rather than a
    dashed box.

    'solid' is what makes an interior view possible, and it needs no special case to do
    it. A body's back faces are the ones pointing away from the eye, so standing inside a
    closed box culls every one of its faces and the box disappears — which is precisely
    what should happen to a room's air when you stand in the room. What is left is what
    you would actually see: the walls, from the inside, and whatever is in the room.
    """
    if fmt != "png":
        raise ValueError(f"unsupported render format '{fmt}' — only 'png' so far")
    if style not in ("wire", "solid"):
        raise ValueError(f"unknown style '{style}' — 'wire' or 'solid'")
    from PIL import Image, ImageDraw

    if style == "solid":
        solids = evaluate(solids)

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

    if style == "solid":
        painted = []
        for s in solids:
            for poly, normal in _faces(s):
                centre3 = [sum(p[i] for p in poly) / len(poly) for i in range(3)]
                towards = [centre3[i] - eye[i] for i in range(3)]
                if sum(normal[i] * towards[i] for i in range(3)) >= 0:
                    continue  # a back face: we are looking at its far side
                cam = [to_cam(p) for p in poly]
                cam = _clip_polygon_near(cam, near)
                if len(cam) < 3:
                    continue
                depth = sum(c[2] for c in cam) / len(cam)
                lit = abs(sum(normal[i] * _LIGHT[i] for i in range(3)))
                shade = 0.45 + 0.55 * lit  # ambient, so nothing is pure black
                fill = tuple(int(c * shade) for c in _kind_colour(s.kind))
                painted.append((depth, [(c[0] / c[2] * focal, c[1] / c[2] * focal)
                                        for c in cam], fill))

        img = Image.new("RGB", (px, px), _BG)
        if not painted:
            ImageDraw.Draw(img).text((10, 10), "nothing in view", fill=_TEXT)
            return _encode(img)
        draw = ImageDraw.Draw(img)
        half = px / 2
        for _, poly, fill in sorted(painted, key=lambda f: -f[0]):  # far to near
            xy = [(half + x * half, half - y * half) for x, y in poly]
            draw.polygon(xy, fill=fill, outline=_EDGE)
        return _encode(img)

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


def _encode(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _clip_polygon_near(poly: list[tuple], near: float) -> list[tuple]:
    """Sutherland–Hodgman against the near plane. A face that straddles the camera has to
    be cut, not dropped: standing in a room, the wall behind you straddles it, and so does
    the floor under your feet."""
    out: list[tuple] = []
    n = len(poly)
    for i in range(n):
        cur, nxt = poly[i], poly[(i + 1) % n]
        cur_in, nxt_in = cur[2] >= near, nxt[2] >= near
        if cur_in:
            out.append(cur)
        if cur_in != nxt_in:
            t = (near - cur[2]) / (nxt[2] - cur[2])
            out.append(tuple(cur[j] + (nxt[j] - cur[j]) * t for j in range(3)))
    return out


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


def _sorted_dims(tree: Bom, p: str) -> list[float]:
    b = _bb(tree, p)
    return sorted(b["max"][i] - b["min"][i] for i in range(3))


def _pair(tree: Bom, a: str, b: str) -> tuple[list[SolidView], list[SolidView]]:
    """Realize two branches for comparison, with `b`'s own solids removed from `a`.

    `realize` flattens a whole subtree, so a feature that hangs UNDER the body it is
    being compared against would otherwise be part of it — and every question
    ("is the window inside the room?", "do they overlap?") would answer itself. A
    body is compared against everything it contains except the thing in question.
    """
    inner = realize(tree, b)
    outer = [s for s in realize(tree, a)
             if not (s.path == b or s.path.startswith(f"{b}/"))]
    return outer, inner


GEOMETRY_NATIVES = {
    "geometry/volume": lambda tree, p: volume(realize(tree, p)),
    "geometry/bbox_w": lambda tree, p: _bb(tree, p)["max"][0] - _bb(tree, p)["min"][0],
    "geometry/bbox_d": lambda tree, p: _bb(tree, p)["max"][1] - _bb(tree, p)["min"][1],
    "geometry/bbox_h": lambda tree, p: _bb(tree, p)["max"][2] - _bb(tree, p)["min"][2],
    "geometry/z_min": lambda tree, p: _bb(tree, p)["min"][2],
    "geometry/z_max": lambda tree, p: _bb(tree, p)["max"][2],
    "geometry/clearance": lambda tree, a, b: clearance(realize(tree, a),
                                                        realize(tree, b)),
    # Does this branch produce a solid at all? The predicate behind "it has a shape".
    "geometry/realizes": lambda tree, p: float(
        bool([s for s in realize(tree, p) if s.role == "add"])),
    "geometry/solids": lambda tree, p: float(
        len([s for s in realize(tree, p) if s.role == "add"])),
    # Adjacency, told truthfully: shared boundary, not bbox proximity.
    "geometry/shared_edge": lambda tree, a, b, tol=1.0: shared_edge(
        *_pair(tree, a, b), tol),
    "geometry/contains": lambda tree, a, b, tol=0.0: float(
        contains(*_pair(tree, a, b), tol)),
    "geometry/overlap": lambda tree, a, b: overlap(*_pair(tree, a, b)),
    # The two smallest bbox dimensions: what has to fit through an aperture.
    "geometry/bbox_min": lambda tree, p: _sorted_dims(tree, p)[0],
    "geometry/bbox_mid": lambda tree, p: _sorted_dims(tree, p)[1],
}


def register_standard() -> None:
    for name, fn in GEOMETRY_NATIVES.items():
        register_native(name, fn)


from .tree import KindDef  # noqa: E402  (kept below the natives for readability)

GEOMETRY_PACKAGE = Package(
    name="geometry",
    version="1.1.0",
    description="Shape conventions (box/prism/cylinder/mesh + booleans over "
                "children, mm, z-up) carried in a node's payload, and the solver "
                "contracts the rule language reaches with solve('geometry/…', path): "
                "volume, bbox_w/d/h, bbox_min/mid, z_min/z_max, clearance(a, b), "
                "realizes(p) and solids(p) (does this branch produce a solid at all), "
                "contains(a, b, tol) and overlap(a, b) (enclosure and collision, by "
                "bounding box), and shared_edge(a, b, tol) — the length of boundary "
                "two bodies actually share in plan. Note shared_edge is not clearance: "
                "two bodies can have zero clearance and share no boundary, so only "
                "shared_edge answers 'do these adjoin'. Implemented natively here; any "
                "module honouring the same contracts may replace it.",
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


# Importing the geometry package installs its geometry/* natives — the cost falls on
# consumers that actually reach for shapes, not on every `import bom`. Idempotent, so
# a consumer may also call register_standard() explicitly.
register_standard()
