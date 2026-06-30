#! /usr/bin/env python3
# -----------------------------------------------------------------------------
# Scientific-illustration density and silhouette-curve helpers.
#
# Optional enhancements adapted from Lu et al., "Non-Photorealistic Volume
# Rendering Using Stippling Techniques" (vis_stipple.pdf). Each feature is
# independently toggled via :class:`IllustrationParams`.
# -----------------------------------------------------------------------------
from __future__ import annotations

import numpy as np
import scipy.ndimage
from PIL import Image


def _unit3(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    if n < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    return v / n


def _normalize01(field):
    lo, hi = float(field.min()), float(field.max())
    if hi - lo > 1e-8:
        return (field - lo) / (hi - lo)
    return np.zeros_like(field)


class IllustrationParams(object):
    """Optional Lu et al. illustration controls (all off by default)."""

    def __init__(
        self,
        boundary=False,
        boundary_kgc=0.4,
        boundary_kgs=0.5,
        boundary_kge=1.0,
        silhouette_density=False,
        silhouette_ksc=0.3,
        silhouette_kss=0.5,
        silhouette_kse=1.0,
        interior=False,
        interior_kte=0.5,
        lighting=False,
        light=(1.0, 1.0, 1.0),
        lighting_kle=2.0,
        depth=False,
        depth_kde=1.0,
        gradient_sigma=1.0,
        gradient_size=False,
        gradient_size_strength=1.0,
        silhouette_curves=False,
        curve_threshold_log=0.12,
        curve_threshold_eye=0.35,
        curve_threshold_grad=0.2,
        curve_length=3.0,
        curve_stride=2,
        view=(0.0, 0.0, 1.0),
    ):
        self.boundary = boundary
        self.boundary_kgc = boundary_kgc
        self.boundary_kgs = boundary_kgs
        self.boundary_kge = boundary_kge
        self.silhouette_density = silhouette_density
        self.silhouette_ksc = silhouette_ksc
        self.silhouette_kss = silhouette_kss
        self.silhouette_kse = silhouette_kse
        self.interior = interior
        self.interior_kte = interior_kte
        self.lighting = lighting
        self.light = _unit3(light)
        self.lighting_kle = lighting_kle
        self.depth = depth
        self.depth_kde = depth_kde
        self.gradient_sigma = gradient_sigma
        self.gradient_size = gradient_size
        self.gradient_size_strength = gradient_size_strength
        self.silhouette_curves = silhouette_curves
        self.curve_threshold_log = curve_threshold_log
        self.curve_threshold_eye = curve_threshold_eye
        self.curve_threshold_grad = curve_threshold_grad
        self.curve_length = curve_length
        self.curve_stride = max(1, int(curve_stride))
        self.view = _unit3(view)

    @property
    def active(self):
        return (
            self.boundary
            or self.silhouette_density
            or self.interior
            or self.lighting
            or self.depth
            or self.gradient_size
            or self.silhouette_curves
        )


def load_aux_map(filename, target_shape, mode="L"):
    """Load and resize an auxiliary image to ``target_shape`` (H, W)."""
    img = Image.open(filename)
    if mode == "RGB":
        img = img.convert("RGB")
    else:
        img = img.convert("L")
    arr = np.asarray(img, dtype=np.float64)
    if arr.shape[:2] != target_shape:
        zoom_y = target_shape[0] / arr.shape[0]
        zoom_x = target_shape[1] / arr.shape[1]
        if mode == "RGB":
            arr = scipy.ndimage.zoom(arr, (zoom_y, zoom_x, 1.0), order=1)
        else:
            arr = scipy.ndimage.zoom(arr, zoom_y, order=1)
    return arr


def normals_from_rgb(rgb):
    """Decode an RGB normal map (0–255) into unit normals (H, W, 3)."""
    n = rgb / 127.5 - 1.0
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    length = np.maximum(length, 1e-8)
    return n / length


def normals_from_gradient(gx, gy):
    """Infer approximate normals from a 2D tone gradient (H, W)."""
    nx = -gx
    ny = -gy
    nz = np.sqrt(np.maximum(1.0 - np.clip(nx * nx + ny * ny, 0.0, 1.0), 0.0))
    n = np.stack([nx, ny, nz], axis=-1)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    length = np.maximum(length, 1e-8)
    return n / length


def compute_image_gradient(field, sigma=1.0):
    """Return smoothed ``(gx, gy, magnitude)`` for a tone/density field."""
    work = field
    if sigma > 0:
        work = scipy.ndimage.gaussian_filter(field, sigma)
    gy, gx = np.gradient(work)
    mag = np.hypot(gx, gy)
    return gx, gy, _normalize01(mag)


def compute_log(field, sigma=1.0):
    """Laplacian-of-Gaussian response (used for silhouette-curve detection)."""
    blurred = scipy.ndimage.gaussian_filter(field, sigma) if sigma > 0 else field
    return scipy.ndimage.laplace(blurred)


def resolve_normals(tone, gx, gy, normal_map_rgb=None):
    """Return unit normals, using a normal map when provided."""
    if normal_map_rgb is not None:
        return normals_from_rgb(normal_map_rgb)
    return normals_from_gradient(gx, gy)


def boundary_factor(tone, grad_mag, kgc, kgs, kge):
    """Lu et al. boundary emphasis (Eq. 5), normalized to [0, 1]."""
    raw = tone * (kgc + kgs * np.power(grad_mag, kge))
    return _normalize01(raw)


def silhouette_factor(tone, silhouette_strength, ksc, kss, kse):
    """Lu et al. silhouette emphasis (Eq. 6), normalized to [0, 1].

    ``silhouette_strength`` is ``1 - |n·view|`` when a normal map is available,
    otherwise a high-gradient edge proxy in ``[0, 1]``.
    """
    raw = tone * (ksc + kss * np.power(silhouette_strength, kse))
    return _normalize01(raw)


def interior_factor(grad_mag, kte):
    """Lu et al. interior/sparsity factor (Eq. 9), normalized to [0, 1]."""
    return _normalize01(np.power(np.clip(grad_mag, 0.0, 1.0), kte))


def lighting_factor(normals, light, kle):
    """Shading modulation from surface normals, normalized to [0, 1]."""
    ndotl = np.sum(normals * light, axis=-1)
    raw = np.power(np.clip(1.0 - ndotl, 0.0, 1.0), kle)
    return _normalize01(raw)


def depth_factor(depth01, kde):
    """Depth attenuation: far regions sparser (simplified from Eq. 8)."""
    raw = np.power(np.clip(1.0 - depth01, 0.0, 1.0), max(kde, 1e-3))
    return _normalize01(raw)


def build_illustration_density(
    tone,
    params,
    grad_mag=None,
    gx=None,
    gy=None,
    normals=None,
    normals_from_map=False,
    depth01=None,
):
    """Combine tone with optional illustration factors into one density field."""
    if not params.active:
        return tone

    if grad_mag is None or gx is None or gy is None:
        gx, gy, grad_mag = compute_image_gradient(tone, params.gradient_sigma)
    if normals is None and (
        params.silhouette_density or params.lighting or params.silhouette_curves
    ):
        normals = normals_from_gradient(gx, gy)

    density = tone.copy()
    if params.boundary:
        density *= boundary_factor(
            tone, grad_mag, params.boundary_kgc, params.boundary_kgs, params.boundary_kge
        )
    if params.silhouette_density:
        if normals_from_map:
            sil = 1.0 - np.clip(np.abs(np.sum(normals * params.view, axis=-1)), 0.0, 1.0)
        else:
            sil = grad_mag
        density *= silhouette_factor(
            tone, sil, params.silhouette_ksc, params.silhouette_kss, params.silhouette_kse
        )
    if params.interior:
        density *= interior_factor(grad_mag, params.interior_kte)
    if params.lighting:
        density *= lighting_factor(normals, params.light, params.lighting_kle)
    if params.depth and depth01 is not None:
        density *= depth_factor(depth01, params.depth_kde)

    return np.clip(density, 0.0, 1.0)


def gradient_size_scale(grad_mag, strength):
    """Per-pixel radius multiplier from gradient magnitude."""
    if strength <= 0:
        return None
    return 1.0 + strength * grad_mag


def extract_silhouette_curves(tone, gx, gy, grad_mag, params, normals=None,
                              normals_from_map=False):
    """Return line segments ``[((x0,y0),(x1,y1)), ...]`` in y-up coords."""
    if not params.silhouette_curves:
        return []

    log = compute_log(tone, params.gradient_sigma)

    grad_dot_view = gx * params.view[0] + gy * params.view[1]
    if np.linalg.norm(params.view[:2]) < 1e-6:
        grad_dot_view = gy

    mask = (
        (tone * log < params.curve_threshold_log)
        & (grad_dot_view < params.curve_threshold_eye)
        & (grad_mag > params.curve_threshold_grad)
    )
    if normals_from_map and normals is not None:
        ndv = np.abs(np.sum(normals * params.view, axis=-1))
        mask &= ndv < params.curve_threshold_eye

    dir_x = gy
    dir_y = -gx
    length = np.hypot(dir_x, dir_y)
    length = np.maximum(length, 1e-8)
    dir_x = dir_x / length
    dir_y = dir_y / length

    ys, xs = np.where(mask)
    if params.curve_stride > 1:
        keep = (xs % params.curve_stride == 0) & (ys % params.curve_stride == 0)
        xs = xs[keep]
        ys = ys[keep]

    half = params.curve_length * 0.5
    segments = []
    for x, y in zip(xs, ys):
        dx = dir_x[y, x] * half
        dy = dir_y[y, x] * half
        segments.append(((x - dx, y - dy), (x + dx, y + dy)))
    return segments
