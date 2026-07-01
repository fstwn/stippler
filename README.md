
# Rhino Grasshopper-Compatible Stippling Processor

![](data/original/donut.png)
![](data/donut_stippled.png)


This is a replication of the following article:

*Weighted Voronoi Stippling*, Adrian Secord. In: Proceedings of the 2nd
International Symposium on Non-photorealistic Animation and
Rendering. NPAR ’02. ACM, 2002, pp. 37– 43.

where the author introduced a *techniques for generating stipple drawings from
grayscale images using weighted centroidal Voronoi diagrams* as in *the
traditional artistic technique of stippling that places small dots of ink onto
paper such that their density give the impression of tone*.

## Authors and credits

* **Original replication** — Nicolas P. Rougier (BSD license, 2017), replicating
  Adrian Secord, *Weighted Voronoi Stippling*, NPAR 2002.
* **Python 3.9.10 port, revised hand-drawn stippling pipeline, Lu et al.
  scientific-illustration extensions, and Grasshopper / Rhino integration** —
  Max Benjamin Eschenbach.


## Pre-requisites

The original replication was written and tested on OSX 10.12 (Sierra) using
Python 3.6, Numpy 1.12, Scipy 0.18, Matplotlib 2.0 and tqdm 4.10.

This revision ports and extends that code for **Python 3.9.10**, matching the
Rhino 8 / Grasshopper CPython runtime. The port replaces the removed
`scipy.misc.imread` with a small Pillow-based loader; the compute core remains
plain numpy / `scipy.spatial`. It has been verified with:

 * Python 3.9.10
 * Numpy 2.0
 * Scipy 1.13
 * Pillow 11.3
 * Matplotlib 3.9
 * tqdm 4.x

Create the environment with conda:

```
conda create -n stippler -c conda-forge python=3.9.10 numpy scipy matplotlib pillow tqdm
```

Original data is in the data directory and you can also obtain it from
[Adrian Secord homepage](http://cs.nyu.edu/~ajsecord/npar2002/StipplingOriginals.zip).

## Installation

The package lives in the `code/` subdirectory and is pip-installable as
`stippler`. Install it from GitHub with the `subdirectory` fragment, pinning
the branch after `@`:

```
pip install "git+https://github.com/fstwn/stippler.git@python39-rhino-port#subdirectory=code"
```

(Replace the owner with your own fork if you pushed the branch there.) Or, from
a local clone:

```
pip install ./code            # or: pip install -e ./code   (editable)
```

This installs the dependencies (numpy, scipy, Pillow, tqdm, matplotlib), the
importable package `stippler`, and a `stippler` console command.

## Usage (classic stippler)

The original replication CLI is preserved as the `stippler.classic` module
(run it with `python -m stippler.classic ...`):

```
 usage: python -m stippler.classic
                    [--n_iter n] [--n_point n] [--save] [--force]
                    [--pointsize min,max] [--figsize w,h]
                    [--display] [--interactive] file

 Weighted Vororonoi Stippler

 positional arguments:
   file                  Density image filename

 optional arguments:
   -h, --help            show this help message and exit
   --n_iter n            Maximum number of iterations
   --n_point n           Number of points
   --pointsize (min,max) (min,max)
                         Point mix/max size for final display
   --figsize w,h         Figure size
   --force               Force recomputation
   --save                Save computed points
   --display             Display final result
   --interactive         Display intermediate results (slower)
```

## Hand-drawn pipeline (`stippler` command)

The `stippler` console command (module `stippler.pipeline`) wraps the relaxation
in a grayscale-image → stipple-output pipeline and adds three controls that make
the result read as *hand drawn* rather than machine generated. The compute core
depends only on numpy, scipy and Pillow (Rhino-friendly); matplotlib is used
only for preview rendering.

1. **Early-stopped relaxation** — fewer Lloyd iterations means the points never
   settle into the regular hexagonal lattice, so spacing stays organically
   uneven. This is the single biggest dial.
   * `--n_iter n` — hard cap on iterations (lower = looser).
   * `--epsilon d` — optional: stop when mean point movement drops below `d`.

To control **contrast** (denser blacks / cleaner whites), use `--gamma g`. It
applies a power curve `d ** g` to the density that drives point placement,
relaxation and dot size, so `g > 1` (e.g. `2.0`–`2.5`) concentrates the same
`n_point` dots into the dark areas and thins the light ones; `g < 1` flattens
the tonal range; `g = 1` is the original linear mapping. (`--threshold` is a
blunter, hard cutoff that forces lighter greys to pure white.)
2. **Varying dot size** — a min/max radius spread plus per-dot random jitter
   breaks the constant-radius "machine stipple" giveaway.
   * `--pointsize min max` — radius range (density drives the base size).
   * `--size_jitter f` — per-dot multiplicative radius noise, e.g. `0.15`.
3. **Imperfect placement & edges** — Gaussian positional jitter plus wobbly,
   non-circular dot outlines.
   * `--position_jitter s` — Gaussian noise std on final positions.
   * `--edge_noise f` — dot-edge wobble as a fraction of radius, e.g. `0.08`.
   * `--edge_segments n` — vertices per dot outline.

Output format follows the `--out` extension (`.png`, `.pdf`, `.svg`).

```
stippler data/boots.jpg --n_point 12000 --n_iter 8 \
         --pointsize 0.8 3.0 --size_jitter 0.2 --position_jitter 0.5 \
         --edge_noise 0.09 --seed 3 --out data/boots-stipple.png
```

The pipeline can also be imported as a library: `stippler.stipple(...)` returns
a `StippleResult` carrying `points`, `radii` and per-dot `polygons` (handy for
feeding geometry into Rhino later), which `render_matplotlib`, `render_svg` and
`save_points` consume.

## Scientific-illustration pipeline (Lu et al.)

The hand-drawn pipeline is further extended with optional controls adapted from
Lu et al., *Non-Photorealistic Volume Rendering Using Stippling Techniques*
([`resources/vis_stipple.pdf`](resources/vis_stipple.pdf)). Each feature is
independently toggled via `IllustrationParams` (library) or the CLI
`illustration` argument group (`stippler --help`):

* **Boundary** — boost stipple density on high-gradient edges.
* **Silhouette density** — concentrate dots on view-facing silhouette regions
  (uses an optional normal map).
* **Interior** — sparse stipples in flat, low-gradient areas.
* **Lighting** — modulate density from inferred or supplied normals.
* **Depth attenuation** — thin stipples in far regions (requires a depth map).
* **Gradient size** — scale dot radius by local gradient magnitude.
* **Silhouette curves** — extract and draw feature-line strokes over the dots.

Normal and depth maps should be aligned with the beauty-pass image. In Rhino,
the Grasshopper component can capture these automatically when the options that
need them are enabled.

## Grasshopper / Rhino integration

Max Benjamin Eschenbach integrated the revised pipeline into Grasshopper for
Rhino 8 CPython 3.9.10:

* **`grasshopper_userobjects/STIPPLER_StippledViewCapture.ghuser`** — drop-in
  user object that captures the active viewport and writes a `_stippled` output
  (PNG, SVG, or PDF), including hand-drawn controls and the Lu et al. options
  above.
* **`grasshopper_userobjects_src/`** — Python 3 script source and input/output
  reference. Re-export the user object from Grasshopper after editing the script
  (right-click → **Save User Object…**).

Install the `stippler` package into the Rhino CPython environment the component
uses (see Installation above), then paste or sync the script into a GH Python 3
component.
