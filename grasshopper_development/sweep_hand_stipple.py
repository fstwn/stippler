#!/usr/bin/env python3
"""Sweep stippler parameters to tune hand-drawn stippling on a capture.

Holds the best-known hand-stipple settings fixed (gamma, jitters, iterations)
and sweeps dot count plus r_min / r_max. Writes PNG outputs with encoded
filenames plus sweep_log.csv / sweep_log.json in the output folder.

Usage (from repo root, with stippler installed or on PYTHONPATH):

    python grasshopper_development/sweep_hand_stipple.py
    python grasshopper_development/sweep_hand_stipple.py --mode quick
    python grasshopper_development/sweep_hand_stipple.py --mode full
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# Allow running without pip install when executed from the repo checkout.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from stippler import render_matplotlib, stipple  # NOQA: E402

DEFAULT_INPUT = (
    _REPO_ROOT
    / "grasshopper_development"
    / "Captures"
    / "260629"
    / "Stippler_Grasshopperdevelopment_DEV_113838.png"
)

# Best hand-stipple settings from the first sweep (held fixed here).
FIXED = {
    "gamma": 2.5,
    "n_iter": 8,
    "size_jitter": 0.28,
    "position_jitter": 0.75,
    "edge_noise": 0.12,
    "seed": 42,
    "dpi": 300,
    "background": "white",
}

# Swept axes: dot count and point-size range around the winning 1.2 / 4.0 pair.
SWEEP_PRESETS = {
    "quick": {
        "n_point": [25000, 50000, 100000],
        "r_min": [1.0, 1.2, 1.4],
        "r_max": [3.5, 4.0, 4.5],
    },
    "default": {
        "n_point": [25000, 40000, 50000, 65000, 80000, 100000],
        "r_min": [0.8, 1.0, 1.2, 1.4],
        "r_max": [3.0, 3.5, 4.0, 4.5, 5.0],
    },
    "full": {
        "n_point": [
            25000, 30000, 40000, 50000, 60000, 70000, 80000, 90000, 100000
        ],
        "r_min": [0.6, 0.8, 1.0, 1.2, 1.4, 1.6],
        "r_max": [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5],
    },
}


@dataclass(frozen=True)
class SweepRun:
    run_id: int
    output_file: str
    n_point: int
    n_iter: int
    gamma: float
    r_min: float
    r_max: float
    size_jitter: float
    position_jitter: float
    edge_noise: float
    seed: int
    dpi: int
    dot_count: int
    density_width: int
    density_height: int
    elapsed_sec: float


def _fmt_num(value: float) -> str:
    """Compact, filename-safe number (2.5 -> 2p5)."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def build_output_name(
    stem: str,
    n_point: int,
    r_min: float,
    r_max: float
) -> str:
    return (
        f"{stem}_np{n_point}"
        f"_ps{_fmt_num(r_min)}-{_fmt_num(r_max)}.png"
    )


def iter_combinations(mode: str):
    preset = SWEEP_PRESETS[mode]
    for n_point in preset["n_point"]:
        for r_min in preset["r_min"]:
            for r_max in preset["r_max"]:
                if r_min < r_max:
                    yield n_point, r_min, r_max


def run_sweep(input_path: Path, output_dir: Path, mode: str) -> list[SweepRun]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Input image not found: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    runs: list[SweepRun] = []
    combos = list(iter_combinations(mode))
    total = len(combos)

    try:
        from tqdm import tqdm
        iterator = tqdm(combos, desc="sweep", unit="img")
    except ImportError:
        iterator = combos

    for run_id, (n_point, r_min, r_max) in enumerate(iterator, start=1):
        out_name = build_output_name(stem, n_point, r_min, r_max)
        out_path = output_dir / out_name

        t0 = time.perf_counter()
        result = stipple(
            str(input_path),
            n_point=n_point,
            n_iter=FIXED["n_iter"],
            gamma=FIXED["gamma"],
            r_min=r_min,
            r_max=r_max,
            size_jitter=FIXED["size_jitter"],
            position_jitter=FIXED["position_jitter"],
            edge_noise=FIXED["edge_noise"],
            seed=FIXED["seed"],
        )
        render_matplotlib(
            result,
            str(out_path),
            dpi=FIXED["dpi"],
            background=FIXED["background"],
        )
        elapsed = time.perf_counter() - t0

        runs.append(SweepRun(
            run_id=run_id,
            output_file=str(out_path),
            n_point=n_point,
            n_iter=FIXED["n_iter"],
            gamma=FIXED["gamma"],
            r_min=r_min,
            r_max=r_max,
            size_jitter=FIXED["size_jitter"],
            position_jitter=FIXED["position_jitter"],
            edge_noise=FIXED["edge_noise"],
            seed=FIXED["seed"],
            dpi=FIXED["dpi"],
            dot_count=len(result.points),
            density_width=result.width,
            density_height=result.height,
            elapsed_sec=round(elapsed, 2),
        ))

        if not hasattr(iterator, "set_postfix"):
            print(f"[{run_id}/{total}] {out_name} ({elapsed:.1f}s)")

    return runs


def write_logs(output_dir: Path, input_path: Path, mode: str,
               runs: list[SweepRun]) -> None:
    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "input_image": str(input_path.resolve()),
        "output_dir": str(output_dir.resolve()),
        "mode": mode,
        "fixed_parameters": FIXED,
        "sweep_presets": SWEEP_PRESETS[mode],
        "run_count": len(runs),
        "total_elapsed_sec": round(sum(r.elapsed_sec for r in runs), 2),
        "runs": [asdict(r) for r in runs],
    }

    json_path = output_dir / "sweep_log.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)

    csv_path = output_dir / "sweep_log.csv"
    fieldnames = list(asdict(runs[0]).keys()) if runs else []
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            writer.writerow(asdict(run))

    readme_path = output_dir / "README.txt"
    with readme_path.open("w", encoding="utf-8") as fh:
        fh.write(
            "Hand-stipple parameter sweep (phase 2)\n"
            "======================================\n\n"
            f"Input:  {input_path}\n"
            f"Mode:   {mode} ({len(runs)} images)\n\n"
            "Fixed for every run\n"
            "-------------------\n"
            f"  gamma={FIXED['gamma']}\n"
            f"  n_iter={FIXED['n_iter']}\n"
            f"  size_jitter={FIXED['size_jitter']}\n"
            f"  position_jitter={FIXED['position_jitter']}\n"
            f"  edge_noise={FIXED['edge_noise']}\n"
            f"  seed={FIXED['seed']}\n"
            f"  dpi={FIXED['dpi']}\n\n"
            "Swept axes\n"
            "----------\n"
            "  n_point   dot count (25000-100000)\n"
            "  r_min     minimum dot radius\n"
            "  r_max     maximum dot radius\n\n"
            "Filename key\n"
            "------------\n"
            "  np*       n_point / NumDots\n"
            "  ps*-*     r_min-r_max point size range\n\n"
            "Baseline winner from phase 1: np25000, ps1p2-4\n"
            "Full parameter rows: sweep_log.csv / sweep_log.json\n"
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Sweep dot count and point size for hand-drawn tuning."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Grayscale capture to stipple (default: torus GH capture)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Folder for PNG outputs and logs "
             "(default: <input-dir>/sweep/<mode>_<timestamp>)",
    )
    parser.add_argument(
        "--mode",
        choices=sorted(SWEEP_PRESETS),
        default="default",
        help="Sweep size: quick=27, default=120, full=378 combinations",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    input_path = args.input.resolve()

    if args.output_dir is None:
        stamp = datetime.now().strftime("%y%m%d_%H%M%S")
        output_dir = input_path.parent / "sweep" / f"{args.mode}_{stamp}"
    else:
        output_dir = args.output_dir.resolve()

    combo_count = len(list(iter_combinations(args.mode)))
    print(f"Input:  {input_path}")
    print(f"Output: {output_dir}")
    print(f"Mode:   {args.mode} ({combo_count} runs)")
    print(f"Fixed:  {FIXED}")
    print("Sweep:  n_point, r_min, r_max")

    runs = run_sweep(input_path, output_dir, args.mode)
    write_logs(output_dir, input_path, args.mode, runs)

    print(f"\nDone. Wrote {len(runs)} images to {output_dir}")
    print("  sweep_log.csv")
    print("  sweep_log.json")
    print("  README.txt")


if __name__ == "__main__":
    main()
