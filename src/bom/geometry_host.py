"""bom.geometry_host — the geometry MCP tools (`tree_render`, `tree_measure`).

A shape-carrying domain calls `register_geometry_tools` alongside
`bom.host.register_tree_tools`; a non-spatial domain (a mind map, a notebook) does
not, and so never inherits a renderer that only speaks solids. Rendering and
measuring are geometry nouns — they belong here, not on the generic host surface.

Kept apart from `bom.geometry` on purpose: geometry's `realize`/`render`/measure work
with no MCP dependency at all (just Pillow for the raster), whereas these tools need
the MCP SDK. Importing this module needs `bom[host]`.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP, Image

from .geometry import bbox, realize, render, render_perspective, volume


def register_geometry_tools(mcp: FastMCP, get_ws) -> None:
    """Register `tree_render` and `tree_measure` on `mcp`, over the same `Workspace`
    resolver `bom.host.register_tree_tools` uses."""

    @mcp.tool()
    def tree_render(path: str = "", eye: list[float] | None = None,
                    look_at: list[float] | None = None, fov_deg: float = 50,
                    views: list[str] | None = None, style: str = "wire") -> Image:
        """Render a branch as a PNG from the viewpoint YOU choose: `eye` and `look_at`
        are [x, y, z] mm in the tree frame, `fov_deg` the field of view. Omit `eye` for
        a default corner view. Pass `views` (['top','front','left']) for flat drafting
        projections instead.

        `style='wire'` (default) draws every extrusion edge — an X-ray: solid = material,
        dashed = cuts, and you see through everything. Good for checking that geometry is
        where you think it is.

        `style='solid'` fills the faces, culls the ones facing away, draws far-to-near so
        surfaces occlude, and EVALUATES the booleans — so a hole is an absence, not a
        dashed box. This is the one to use to look at something, and the only one that
        works from INSIDE: put `eye` in the middle of a room at about 1.6 m and look
        across it. A body's back faces are the ones pointing away from you, so a room's
        air-volume culls itself away when you stand in it, and what you see is what you
        would actually see — the walls from the inside, their doorways, and the furniture.
        """
        ws = get_ws()
        if isinstance(ws, str):
            raise ValueError(ws)
        solids = realize(ws.effective(), path)
        png = (render(solids, views, fmt="png") if views
               else render_perspective(solids, eye, look_at, fov_deg,
                                       fmt="png", style=style))
        return Image(data=png, format="png")

    @mcp.tool()
    def tree_measure(path: str = "") -> str:
        """A geometry summary of a branch: its bounding box and signed-volume
        estimate. The measurement half of what used to ride on tree_check — now a
        geometry tool, so tree_check stays a pure rules check for every domain."""
        ws = get_ws()
        if isinstance(ws, str):
            return ws
        try:
            solids = realize(ws.effective(), path)
        except ValueError as e:
            return str(e)
        bb = bbox(solids)
        if bb is None:
            return "no solids in this branch yet"
        w = bb["max"][0] - bb["min"][0]
        d = bb["max"][1] - bb["min"][1]
        h = bb["max"][2] - bb["min"][2]
        return (f"bbox: {w:g} x {d:g} x {h:g} mm; "
                f"volume ~ {volume(solids) / 1e9:.4f} m3 ({len(solids)} solids)")
