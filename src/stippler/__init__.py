"""Hand-drawn weighted Voronoi stippling.

Grayscale image -> stipple geometry/output, with controls for early-stopped
relaxation, varying dot size, positional jitter, imperfect dot edges and
contrast (gamma). Optional Lu et al. scientific-illustration enhancements
(boundary/silhouette density, interior sparsity, lighting, depth, silhouette
curves) are toggled via :class:`IllustrationParams`. Targets Python 3.9.10 for
Rhino 8 CPython compatibility.

The high-level entry point is :func:`stipple`, which returns a
:class:`StippleResult` carrying the points, radii, per-dot polygons and
optional silhouette curves. Render helpers (:func:`render_matplotlib`,
:func:`render_svg`, :func:`save_points`) turn that into files.
"""
from . import voronoi
from .illustration import IllustrationParams
from .pipeline import (
    StippleResult,
    stipple,
    load_density,
    prepare_density,
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

__version__ = "0.2.0.0"

__all__ = [
    "StippleResult",
    "stipple",
    "IllustrationParams",
    "load_density",
    "prepare_density",
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
