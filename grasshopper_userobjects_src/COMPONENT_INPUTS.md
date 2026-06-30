# StippledViewCapture — Grasshopper inputs

Paste `STIPPLER_StippledViewCapture.py` into the Python 3 script component,
then ensure inputs appear **in this order** (types and nicknames). All
illustration inputs are optional booleans/paths with safe defaults (off).

| # | NickName | Type hint | Default | Group |
|---|----------|-----------|---------|-------|
| 0 | Toggle | bool | false | |
| 1 | OpenFile | bool | false | |
| 2 | Width | int | 1920 | |
| 3 | Height | int | 1080 | |
| 4 | BackgroundColor | Color | white | |
| 5 | Grid | bool | false | |
| 6 | WorldAxes | bool | false | |
| 7 | CPlaneAxes | bool | false | |
| 8 | OutputFormat | int | 0 | 0=PNG, 1=SVG, 2=PDF |
| 9 | NumDots | int | 5000 | hand stipple |
| 10 | Iterations | int | 8 | hand stipple |
| 11 | Gamma | float | 2.5 | hand stipple |
| 12 | RMin | float | 1.2 | hand stipple |
| 13 | RMax | float | 4.0 | hand stipple |
| 14 | SizeJitter | float | 0.28 | hand stipple |
| 15 | PositionJitter | float | 0.75 | hand stipple |
| 16 | EdgeNoise | float | 0.12 | hand stipple |
| 17 | Seed | int | 42 | |
| 18 | Dpi | int | 300 | |
| 19 | Boundary | bool | false | illustration |
| 20 | SilhouetteDensity | bool | false | illustration |
| 21 | Interior | bool | false | illustration |
| 22 | Lighting | bool | false | illustration |
| 23 | DepthAttenuation | bool | false | illustration |
| 24 | GradientSize | bool | false | illustration |
| 25 | SilhouetteCurves | bool | false | illustration |
| 26 | NormalMap | str | (empty) | optional RGB normal pass |
| 27 | DepthMap | str | (empty) | required when DepthAttenuation on |
| 28 | LightDir | Vector3d | 1,1,1 | for Lighting |
| 29 | CurveWidth | float | 0.6 | silhouette stroke width |

## Outputs

| # | NickName | Type |
|---|----------|------|
| 0 | StippledPath | generic tree |
| 1 | CapturePath | generic tree |

## Notes

- **View direction** for silhouette features is taken automatically from the
  active Rhino viewport camera (no extra input).
- Wire **NormalMap** / **DepthMap** to paths of auxiliary captures exported
  from Rhino (same resolution/framing as the beauty pass).
- Recommended illustration starter for statue/insect references:
  `Boundary`, `SilhouetteDensity`, `Interior`, `SilhouetteCurves` on; add
  `NormalMap` when available.

