#! /usr/bin/env python3
# -----------------------------------------------------------------------------
# Hand-drawn Weighted Voronoi Stippling pipeline
#
# Builds on the weighted Voronoi stippler by Nicolas P. Rougier (BSD), itself a
# replication of "Weighted Voronoi Stippling", Adrian Secord, NPAR 2002.
#
# This module wraps the relaxation in a grayscale-image -> stipple-output
# pipeline and adds three controls that make the result read as hand drawn
# rather than machine generated:
#
#   1. Early-stopped relaxation. Fewer Lloyd iterations means the points never
#      settle into the regular hexagonal lattice, so local spacing stays
#      slightly uneven. This is the single biggest dial (`n_iter`, `epsilon`).
#   2. Varying dot size. A min/max radius spread plus per-dot random jitter
#      breaks the mechanical uniformity of constant-radius dots (`r_min`,
#      `r_max`, `size_jitter`).
#   3. Imperfect placement and edges. A little Gaussian positional jitter
#      (`position_jitter`) plus wobbly, non-mathematically-circular dot
#      outlines (`edge_noise`, `edge_segments`).
#
# Optional scientific-illustration enhancements (Lu et al., vis_stipple.pdf)
# live in ``illustration.py`` and are toggled via :class:`IllustrationParams`
# plus optional normal/depth maps passed to :func:`stipple`.
#
# Targets Python 3.9.10 to stay compatible with the Rhino 8 CPython runtime.
# The compute core (everything except `render_*`) depends only on numpy, scipy
# and Pillow; matplotlib is imported lazily and only for rasterized/vector
# preview rendering.
# -----------------------------------------------------------------------------
import os
import numpy as np
import scipy.ndimage
import scipy.spatial
from PIL import Image

try:
    from . import voronoi
    from .illustration import (
        IllustrationParams,
        build_illustration_density,
        compute_image_gradient,
        extract_silhouette_curves,
        gradient_size_scale,
        load_aux_map,
        resolve_normals,
    )
except ImportError:  # allow running the file directly (python pipeline.py)
    import voronoi
    from illustration import (
        IllustrationParams,
        build_illustration_density,
        compute_image_gradient,
        extract_silhouette_curves,
        gradient_size_scale,
        load_aux_map,
        resolve_normals,
    )


# -----------------------------------------------------------------------------
# Density preparation
# -----------------------------------------------------------------------------
def normalize(D):
    """Scale array into [0, 1]; return zeros if (near) constant."""
    Vmin, Vmax = D.min(), D.max()
    if Vmax - Vmin > 1e-5:
        return (D - Vmin) / (Vmax - Vmin)
    return np.zeros_like(D)


def _compute_zoom(shape, n_point):
    """Zoom factor so each Voronoi region covers ~500 pixels."""
    zoom = (n_point * 500) / (shape[0] * shape[1])
    zoom = int(round(np.sqrt(zoom)))
    return max(zoom, 1)


def prepare_density(
    filename,
    n_point,
    threshold=255,
    gamma=1.0,
    illustration=None,
    normal_map=None,
    depth_map=None,
):
    """Load a grayscale image and build the stippling density field.

    The image is resized so that each of the ``n_point`` Voronoi regions
    covers ~500 pixels (matching the original stippler), thresholded, inverted
    (dark ink = high density) and flipped vertically so that the point space
    uses a conventional y-up convention.

    When ``illustration`` is an active :class:`IllustrationParams` instance,
    optional Lu et al. factors modulate the tone field. ``normal_map`` and
    ``depth_map`` are optional auxiliary images (same framing as the beauty
    pass) resized to match.

    Returns
    -------
    density : (H, W) float array in [0, 1]
    density_P, density_Q : cumulative-sum helper arrays
    context : dict with ``tone``, ``grad_mag``, ``gx``, ``gy``, ``normals``,
        ``depth01`` (entries may be ``None``)
    """
    if illustration is None:
        illustration = IllustrationParams()

    img = Image.open(filename).convert("L")
    raw = np.asarray(img, dtype=np.float64)
    zoom = _compute_zoom(raw.shape, n_point)
    raw = scipy.ndimage.zoom(raw, zoom, order=0)
    raw = np.minimum(raw, threshold)

    tone = 1.0 - normalize(raw)
    if gamma != 1.0:
        tone = np.power(tone, gamma)
    tone = tone[::-1, :]
    shape = tone.shape

    depth01 = None
    if depth_map is not None:
        depth01 = load_aux_map(depth_map, shape, mode="L")
        depth01 = normalize(depth01)[::-1, :]

    normal_rgb = None
    normals_from_map = False
    if normal_map is not None:
        normal_rgb = load_aux_map(normal_map, shape, mode="RGB")[::-1, :, :]
        normals_from_map = True

    gx = gy = grad_mag = normals = None
    if illustration.active:
        gx, gy, grad_mag = compute_image_gradient(
            tone,
            illustration.gradient_sigma
        )
        normals = resolve_normals(tone, gx, gy, normal_rgb)
        density = build_illustration_density(
            tone,
            illustration,
            grad_mag=grad_mag,
            gx=gx,
            gy=gy,
            normals=normals,
            normals_from_map=normals_from_map,
            depth01=depth01,
        )
    else:
        density = tone

    density_P = density.cumsum(axis=1)
    density_Q = density_P.cumsum(axis=1)
    context = {
        "tone": tone,
        "grad_mag": grad_mag,
        "gx": gx,
        "gy": gy,
        "normals": normals,
        "normals_from_map": normals_from_map,
        "depth01": depth01,
    }
    return density, density_P, density_Q, context


def load_density(filename, n_point, threshold=255, gamma=1.0):
    """Backward-compatible wrapper around :func:`prepare_density`.

    Returns only ``(density, density_P, density_Q)``.
    """
    density, density_P, density_Q, _context = prepare_density(
        filename, n_point, threshold, gamma)
    return density, density_P, density_Q


def initialization(n, density, rng):
    """Rejection-sample ``n`` points with probability proportional to density.

    Points are returned in [0, W] x [0, H] (x, y), y-up.
    """
    samples = []
    while len(samples) < n:
        X = rng.uniform(0, density.shape[1], 10 * n)
        Y = rng.uniform(0, density.shape[0], 10 * n)
        P = rng.uniform(0, 1, 10 * n)
        index = 0
        while index < len(X) and len(samples) < n:
            x, y = X[index], Y[index]
            x_, y_ = int(np.floor(x)), int(np.floor(y))
            if P[index] < density[y_, x_]:
                samples.append([x, y])
            index += 1
    return np.array(samples)


# -----------------------------------------------------------------------------
# Feature 1: relaxation with early stopping
# -----------------------------------------------------------------------------
def relax(points, density, density_P, density_Q,
          n_iter=50, epsilon=0.0, progress=False):
    """Run Lloyd relaxation (weighted Voronoi centroids), stopping early.

    Two independent ways to stop early:

    * ``n_iter`` -- the hard cap. Lowering it is the primary dial: with few
      iterations the points never reach the regular lattice, so spacing stays
      organically uneven.
    * ``epsilon`` -- optional convergence detector. When the mean displacement
      of the configuration between two iterations drops below ``epsilon``
      (in density-pixel units) the relaxation stops. ``epsilon <= 0`` disables
      it, so ``n_iter`` alone governs the result.

    Displacement is measured order-independently via nearest-neighbour matching
    (the centroid list is not in the same order as the input points).
    """
    iterator = range(n_iter)
    if progress:
        try:
            import tqdm
            iterator = tqdm.trange(n_iter)
        except ImportError:
            pass

    for _ in iterator:
        prev = points
        regions, points = voronoi.centroids(
            points, density, density_P, density_Q)
        if epsilon > 0 and len(prev) and len(points):
            tree = scipy.spatial.cKDTree(prev)
            dist, _idx = tree.query(points, k=1)
            if dist.mean() < epsilon:
                break
    return points


# -----------------------------------------------------------------------------
# Feature 2: varying dot size
# -----------------------------------------------------------------------------
def assign_radii(points, density, r_min, r_max, size_jitter=0.0, rng=None,
                 grad_mag=None, gradient_size_strength=0.0):
    """Assign a radius (density-pixel units) to every point.

    The base radius is driven by local density (darker -> bigger), mapped into
    ``[r_min, r_max]``. ``size_jitter`` then adds per-dot multiplicative noise
    so that, even at equal density, real nib/pressure variation is mimicked and
    the tell-tale constant-radius look disappears. When ``grad_mag`` is given
    and ``gradient_size_strength > 0``, radii are further scaled by local
    gradient magnitude (Lu et al. Eq. 4). Results are clamped to ``[r_min,
    r_max]``.
    """
    if rng is None:
        rng = np.random.default_rng()

    Pi = points.astype(int)
    X = np.clip(Pi[:, 0], 0, density.shape[1] - 1)
    Y = np.clip(Pi[:, 1], 0, density.shape[0] - 1)
    d = density[Y, X]

    radii = r_min + (r_max - r_min) * d
    if grad_mag is not None and gradient_size_strength > 0:
        scale = gradient_size_scale(grad_mag, gradient_size_strength)
        radii = radii * scale[Y, X]
    if size_jitter > 0:
        radii = radii * (1.0 + rng.normal(0.0, size_jitter, len(radii)))
    return np.clip(radii, r_min, r_max)


# -----------------------------------------------------------------------------
# Feature 3: positional jitter + imperfect (wobbly) dot outlines
# -----------------------------------------------------------------------------
def apply_position_jitter(points, sigma, rng=None):
    """Add isotropic Gaussian noise (std ``sigma``, density-pixel units)."""
    if sigma <= 0:
        return points
    if rng is None:
        rng = np.random.default_rng()
    return points + rng.normal(0.0, sigma, points.shape)


def dot_polygons(points, radii, edge_segments=16, edge_noise=0.0, rng=None):
    """Return one wobbly closed polygon per dot approximating a circle.

    Each dot is an ``edge_segments``-gon whose vertex angles are slightly
    jittered and whose per-vertex radius is perturbed by ``edge_noise`` (a
    fraction of the dot radius). With ``edge_noise == 0`` and a high segment
    count the dots are effectively perfect circles; small values give the
    organic, hand-inked edge.

    Returns a list of (edge_segments, 2) float arrays.
    """
    if rng is None:
        rng = np.random.default_rng()

    base = np.linspace(0, 2 * np.pi, edge_segments, endpoint=False)
    polygons = []
    for (cx, cy), r in zip(points, radii):
        ang = base + rng.normal(0.0, np.pi / edge_segments * edge_noise,
                                edge_segments)
        rad = r * (1.0 + rng.normal(0.0, edge_noise, edge_segments))
        rad = np.maximum(rad, 0.0)
        xs = cx + rad * np.cos(ang)
        ys = cy + rad * np.sin(ang)
        polygons.append(np.column_stack([xs, ys]))
    return polygons


# -----------------------------------------------------------------------------
# End-to-end pipeline
# -----------------------------------------------------------------------------
class StippleResult(object):
    """Plain container for the geometry produced by :func:`stipple`."""

    def __init__(self, points, radii, polygons, density, curves=None):
        self.points = points        # (n, 2) float, y-up, density-pixel coords
        self.radii = radii          # (n,)  float, density-pixel units
        self.polygons = polygons    # list of (edge_segments, 2) float arrays
        self.density = density       # (H, W) float density field used
        self.curves = curves or []   # list of ((x0,y0),(x1,y1)) line segments

    @property
    def width(self):
        return self.density.shape[1]

    @property
    def height(self):
        return self.density.shape[0]


def stipple(filename, n_point=5000, n_iter=50, threshold=255, gamma=1.0,
            epsilon=0.0, r_min=1.0, r_max=1.0, size_jitter=0.0,
            position_jitter=0.0, edge_segments=16, edge_noise=0.0,
            seed=None, progress=False,
            illustration=None, normal_map=None, depth_map=None):
    """Run the full grayscale-image -> stipple-geometry pipeline.

    All length parameters (`r_min`, `r_max`, `position_jitter`, `epsilon`) are
    in density-pixel units of the internally resized image. See module
    docstring for what each control does. Returns a :class:`StippleResult`;
    rendering to a file is a separate step
    (:func:`render_matplotlib` / :func:`render_svg`).

    Optional scientific-illustration controls (Lu et al.) are enabled by
    passing an :class:`IllustrationParams` instance as ``illustration``, plus
    optional ``normal_map`` / ``depth_map`` image paths when silhouette,
    lighting or depth attenuation is requested.
    """
    rng = np.random.default_rng(seed)
    if illustration is None:
        illustration = IllustrationParams()

    density, density_P, density_Q, context = prepare_density(
        filename,
        n_point,
        threshold,
        gamma,
        illustration=illustration,
        normal_map=normal_map,
        depth_map=depth_map,
    )
    if illustration.gradient_size and context["grad_mag"] is None:
        gx, gy, grad_mag = compute_image_gradient(
            context["tone"], illustration.gradient_sigma)
        context["grad_mag"] = grad_mag
        context["gx"] = gx
        context["gy"] = gy

    points = initialization(n_point, density, rng)
    points = relax(points, density, density_P, density_Q,
                   n_iter=n_iter, epsilon=epsilon, progress=progress)

    grad_mag = context["grad_mag"]
    grad_size_strength = (
        illustration.gradient_size_strength
        if illustration.gradient_size
        else 0.0
    )
    # Radii are sampled before positional jitter so dot size still reflects the
    # tone the dot actually settled on.
    radii = assign_radii(
        points, density, r_min, r_max, size_jitter, rng,
        grad_mag=grad_mag, gradient_size_strength=grad_size_strength,
    )
    points = apply_position_jitter(points, position_jitter, rng)
    polygons = dot_polygons(points, radii, edge_segments, edge_noise, rng)

    curves = []
    if illustration.silhouette_curves:
        gx = context["gx"]
        gy = context["gy"]
        if gx is None or gy is None:
            gx, gy, grad_mag = compute_image_gradient(
                context["tone"], illustration.gradient_sigma)
        curves = extract_silhouette_curves(
            context["tone"], gx, gy, grad_mag, illustration,
            normals=context["normals"],
            normals_from_map=context["normals_from_map"],
        )

    return StippleResult(points, radii, polygons, density, curves=curves)


# -----------------------------------------------------------------------------
# Rendering (matplotlib only; not needed by the compute core)
# -----------------------------------------------------------------------------
def render_matplotlib(result, filename, figsize=8, dpi=300, color="black",
                      background="white", curve_color=None, curve_width=0.6):
    """Rasterize/vectorize the dots as filled wobbly polygons.

    The file extension of ``filename`` chooses the format (.png, .pdf, .svg).
    Dots are drawn as polygons (not scatter markers) so the imperfect edges
    from ``edge_noise`` are preserved. Optional silhouette curves from
    ``result.curves`` are drawn on top.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection, PolyCollection

    if curve_color is None:
        curve_color = color

    W, H = result.width, result.height
    ratio = W / H
    fig = plt.figure(figsize=(figsize, figsize / ratio), facecolor=background)
    ax = fig.add_axes([0, 0, 1, 1], frameon=False)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")

    collection = PolyCollection(result.polygons, facecolors=color,
                                edgecolors="none", antialiased=True)
    ax.add_collection(collection)

    if result.curves:
        lines = LineCollection(result.curves, colors=curve_color,
                               linewidths=curve_width, capstyle="round")
        ax.add_collection(lines)

    fig.savefig(filename, dpi=dpi, facecolor=background)
    plt.close(fig)
    return filename


def render_svg(result, filename, color="black", background="white",
               curve_color=None, curve_width=0.6):
    """Write a minimal standalone SVG of the wobbly dot polygons.

    Dependency-free (no matplotlib); handy for the Rhino-bound workflow where
    the geometry, not a raster, is the deliverable. y is flipped so the SVG
    matches the y-up point space visually. Silhouette curves are emitted as
    ``<line>`` elements when present.
    """
    if curve_color is None:
        curve_color = color

    W, H = result.width, result.height
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<svg xmlns="http://www.w3.org/2000/svg" '
             'width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H),
             '<rect width="%d" height="%d" fill="%s"/>' % (W, H, background)]
    for poly in result.polygons:
        pts = " ".join("%.2f,%.2f" % (x, H - y) for x, y in poly)
        lines.append('<polygon points="%s" fill="%s"/>' % (pts, color))
    for (x0, y0), (x1, y1) in result.curves:
        lines.append(
            '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" '
            'stroke="%s" stroke-width="%.2f" stroke-linecap="round"/>' % (
                x0, H - y0, x1, H - y1, curve_color, curve_width))
    lines.append("</svg>")
    with open(filename, "w") as fh:
        fh.write("\n".join(lines))
    return filename


def save_points(result, filename):
    """Persist points + radii as a (n, 3) .npy array (x, y, radius)."""
    data = np.column_stack([result.points, result.radii])
    np.save(filename, data)
    return filename


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def _parse_vec3(text):
    parts = [float(x.strip()) for x in text.split(",")]
    if len(parts) != 3:
        raise ValueError("expected three comma-separated values")
    return tuple(parts)


def _illustration_from_args(args):
    """Build :class:`IllustrationParams` from parsed CLI flags."""
    return IllustrationParams(
        boundary=args.boundary,
        boundary_kgc=args.boundary_kgc,
        boundary_kgs=args.boundary_kgs,
        boundary_kge=args.boundary_kge,
        silhouette_density=args.silhouette_density,
        silhouette_ksc=args.silhouette_ksc,
        silhouette_kss=args.silhouette_kss,
        silhouette_kse=args.silhouette_kse,
        interior=args.interior,
        interior_kte=args.interior_kte,
        lighting=args.lighting,
        light=_parse_vec3(args.light),
        lighting_kle=args.lighting_kle,
        depth=args.depth and args.depth_map is not None,
        depth_kde=args.depth_kde,
        gradient_sigma=args.gradient_sigma,
        gradient_size=args.gradient_size,
        gradient_size_strength=args.gradient_size_strength,
        silhouette_curves=args.silhouette_curves,
        curve_threshold_log=args.curve_threshold_log,
        curve_threshold_eye=args.curve_threshold_eye,
        curve_threshold_grad=args.curve_threshold_grad,
        curve_length=args.curve_length,
        curve_stride=args.curve_stride,
        view=_parse_vec3(args.view),
    )


def _add_illustration_args(p):
    g = p.add_argument_group(
        "illustration (optional Lu et al. enhancements; all off by default)")
    g.add_argument("--boundary", action="store_true",
                   help="Boost stipple density on high-gradient edges")
    g.add_argument("--boundary-kgc", type=float, default=0.4, metavar="f",
                   help="Boundary tone floor (default: 0.4)")
    g.add_argument("--boundary-kgs", type=float, default=0.5, metavar="f",
                   help="Boundary gradient strength (default: 0.5)")
    g.add_argument("--boundary-kge", type=float, default=1.0, metavar="f",
                   help="Boundary gradient exponent (default: 1.0)")
    g.add_argument("--silhouette-density", action="store_true",
                   help="Boost density on view-facing silhouette regions")
    g.add_argument("--silhouette-ksc", type=float, default=0.3, metavar="f")
    g.add_argument("--silhouette-kss", type=float, default=0.5, metavar="f")
    g.add_argument("--silhouette-kse", type=float, default=1.0, metavar="f")
    g.add_argument("--interior", action="store_true",
                   help="Sparse stipples in low-gradient (flat) regions")
    g.add_argument("--interior-kte", type=float, default=0.5, metavar="f")
    g.add_argument("--lighting", action="store_true",
                   help="Modulate density from inferred or mapped normals")
    g.add_argument("--light", type=str, default="1,1,1", metavar="x,y,z",
                   help="Light direction (default: 1,1,1)")
    g.add_argument("--lighting-kle", type=float, default=2.0, metavar="f")
    g.add_argument("--depth", action="store_true",
                   help="Attenuate far regions (requires --depth-map)")
    g.add_argument("--depth-map", type=str, default=None, metavar="path",
                   help="Grayscale depth image aligned with the beauty pass")
    g.add_argument("--depth-kde", type=float, default=1.0, metavar="f")
    g.add_argument("--normal-map", type=str, default=None, metavar="path",
                   help="RGB normal map aligned with the beauty pass")
    g.add_argument("--gradient-sigma", type=float, default=1.0, metavar="s",
                   help=(
                    "Gaussian sigma for gradient/LOG features (default: 1)"
                    ))
    g.add_argument("--gradient-size", action="store_true",
                   help="Scale dot radius by local gradient magnitude")
    g.add_argument("--gradient-size-strength", type=float, default=1.0,
                   metavar="f")
    g.add_argument("--silhouette-curves", action="store_true",
                   help="Extract and draw silhouette/feature line segments")
    g.add_argument("--curve-threshold-log", type=float, default=0.12,
                   metavar="f")
    g.add_argument("--curve-threshold-eye", type=float, default=0.35,
                   metavar="f")
    g.add_argument("--curve-threshold-grad", type=float, default=0.2,
                   metavar="f")
    g.add_argument("--curve-length", type=float, default=3.0, metavar="L",
                   help="Silhouette stroke half-length in pixels (default: 3)")
    g.add_argument("--curve-stride", type=int, default=2, metavar="n",
                   help="Sample every n pixels for curves (default: 2)")
    g.add_argument("--view", type=str, default="0,0,1", metavar="x,y,z",
                   help="Camera/view direction (default: 0,0,1)")
    g.add_argument("--curve-width", type=float, default=0.6, metavar="w",
                   help="Silhouette stroke width (default: 0.6)")


def _build_parser():
    import argparse
    p = argparse.ArgumentParser(
        description="Hand-drawn weighted Voronoi stippler "
                    "(grayscale image -> stipple output)")
    p.add_argument("filename", metavar="image", type=str,
                   help="Grayscale density image")
    p.add_argument("--n_point", metavar="n", type=int, default=5000,
                   help="Number of stipple dots")
    p.add_argument("--n_iter", metavar="n", type=int, default=50,
                   help="Max relaxation iterations. Lower = looser, more "
                        "uneven (hand-drawn) spacing")
    p.add_argument("--epsilon", metavar="d", type=float, default=0.0,
                   help="Early-stop when mean point movement < d "
                        "(<=0 disables; n_iter alone governs)")
    p.add_argument("--threshold", metavar="n", type=int, default=255,
                   help="Grey level threshold (brighter = white)")
    p.add_argument("--gamma", metavar="g", type=float, default=1.0,
                   help="Contrast curve on density. >1 = denser blacks / "
                        "higher contrast, <1 = flatter, 1 = linear")
    p.add_argument("--pointsize", metavar=("min", "max"), type=float, nargs=2,
                   default=(1.0, 1.0),
                   help="Min/max dot radius (density-pixel units)")
    p.add_argument("--size_jitter", metavar="f", type=float, default=0.0,
                   help="Per-dot radius noise as a fraction (e.g. 0.15)")
    p.add_argument("--position_jitter", metavar="s", type=float, default=0.0,
                   help="Gaussian positional noise std (density-pixel units)")
    p.add_argument("--edge_segments", metavar="n", type=int, default=16,
                   help="Vertices per dot outline")
    p.add_argument("--edge_noise", metavar="f", type=float, default=0.0,
                   help="Dot-edge wobble as a fraction of radius (e.g. 0.08)")
    p.add_argument("--figsize", metavar="w", type=float, default=8,
                   help="Output figure width (inches)")
    p.add_argument("--dpi", metavar="n", type=int, default=300,
                   help="Raster output DPI")
    p.add_argument("--seed", metavar="n", type=int, default=None,
                   help="Random seed for reproducibility")
    p.add_argument("--out", metavar="path", type=str, default=None,
                   help="Output path (.png/.pdf/.svg). Default: "
                        "<image>-stipple.png next to the input")
    p.add_argument("--save_points", action="store_true",
                   help="Also save <out>.npy with (x, y, radius)")
    _add_illustration_args(p)
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    illustration = _illustration_from_args(args)

    if args.depth and args.depth_map is None:
        raise SystemExit("--depth requires --depth-map")

    result = stipple(
        args.filename,
        n_point=args.n_point,
        n_iter=args.n_iter,
        threshold=args.threshold,
        gamma=args.gamma,
        epsilon=args.epsilon,
        r_min=args.pointsize[0],
        r_max=args.pointsize[1],
        size_jitter=args.size_jitter,
        position_jitter=args.position_jitter,
        edge_segments=args.edge_segments,
        edge_noise=args.edge_noise,
        seed=args.seed,
        progress=True,
        illustration=illustration,
        normal_map=args.normal_map,
        depth_map=args.depth_map,
    )

    out = args.out
    if out is None:
        dirname = os.path.dirname(args.filename)
        base = os.path.basename(args.filename).split(".")[0]
        out = os.path.join(dirname, base + "-stipple.png")

    ext = os.path.splitext(out)[1].lower()
    if ext == ".svg":
        render_svg(result, out, curve_width=args.curve_width)
    else:
        render_matplotlib(result, out, figsize=args.figsize, dpi=args.dpi,
                          curve_width=args.curve_width)
    print("Wrote %s (%d dots, %d curves, %dx%d)" % (
        out, len(result.points), len(result.curves),
        result.width, result.height))

    if args.save_points:
        npy = os.path.splitext(out)[0] + ".npy"
        save_points(result, npy)
        print("Wrote %s" % npy)


if __name__ == "__main__":
    main()
