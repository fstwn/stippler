"""Hand-drawn weighted Voronoi stippling.

Grayscale image -> stipple geometry/output, with controls for early-stopped
relaxation, varying dot size, positional jitter, imperfect dot edges and
contrast (gamma). Targets Python 3.9.10 for Rhino 8 CPython compatibility.

The high-level entry point is :func:`stipple`, which returns a
:class:`StippleResult` carrying the points, radii and per-dot polygons. Render
helpers (:func:`render_matplotlib`, :func:`render_svg`, :func:`save_points`)
turn that into files.
"""
from . import voronoi
from .pipeline import (
    StippleResult,
    stipple,
    load_density,
    normalize,
    initialization,
    relax,
    assign_radii,
    apply_position_jitter,
    dot_polygons,
    render_matplotlib,
    render_svg,
    save_points,
    main,
)

__version__ = "0.1.0"

__all__ = [
    "StippleResult",
    "stipple",
    "load_density",
    "normalize",
    "initialization",
    "relax",
    "assign_radii",
    "apply_position_jitter",
    "dot_polygons",
    "render_matplotlib",
    "render_svg",
    "save_points",
    "main",
    "voronoi",
    "__version__",
]
