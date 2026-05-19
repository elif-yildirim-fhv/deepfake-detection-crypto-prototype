"""Test-Matrix fuer die Evaluierung der Hash-basierten Manipulationserkennung."""

from __future__ import annotations
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageEnhance
import imagehash
import numpy as np

ORIGINALS_DIR = Path("testbilder/originals")
FACESWAP_DIR = Path("testbilder/face_swaps")
OUTPUT_CSV = Path("evaluation_results.csv")

PHASH_THRESHOLD = 3


def sha256_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def phash(path: Path) -> imagehash.ImageHash:
    return imagehash.phash(Image.open(path))


def t_jpeg_quality(quality: int):
    def inner(src: Path, dst: Path):
        img = Image.open(src).convert("RGB")
        img.save(dst, "JPEG", quality=quality)
    return inner


def t_png_to_jpeg(src: Path, dst: Path):
    Image.open(src).convert("RGB").save(dst, "JPEG", quality=92)


def t_resize(factor: float):
    def inner(src: Path, dst: Path):
        img = Image.open(src)
        w, h = img.size
        img = img.resize((int(w * factor), int(h * factor)), Image.LANCZOS)
        img.save(dst)
    return inner


def t_crop(percent: float):
    def inner(src: Path, dst: Path):
        img = Image.open(src)
        w, h = img.size
        pad_w, pad_h = int(w * percent), int(h * percent)
        img.crop((pad_w, pad_h, w - pad_w, h - pad_h)).save(dst)
    return inner


def t_brightness(factor: float):
    def inner(src: Path, dst: Path):
        img = Image.open(src)
        ImageEnhance.Brightness(img).enhance(factor).save(dst)
    return inner


def t_pixel_flip(num_pixels: int):
    def inner(src: Path, dst: Path):
        img = Image.open(src).convert("RGB")
        arr = np.array(img)
        rng = np.random.default_rng(seed=42)
        h, w, _ = arr.shape
        for _ in range(num_pixels):
            y, x = rng.integers(0, h), rng.integers(0, w)
            arr[y, x] = rng.integers(0, 256, size=3)
        Image.fromarray(arr).save(dst)
    return inner


TRANSFORMATIONS: list[tuple[str, str, Callable]] = [
    ("jpeg_q95",               "harmlos",            t_jpeg_quality(95)),
    ("jpeg_q75",               "harmlos",            t_jpeg_quality(75)),
    ("jpeg_q50",               "harmlos",            t_jpeg_quality(50)),
    ("png_to_jpeg",            "harmlos",            t_png_to_jpeg),
    ("resize_50pct",           "harmlos",            t_resize(0.5)),
    ("resize_150pct",          "harmlos",            t_resize(1.5)),
    ("crop_5pct",              "harmlos",            t_crop(0.05)),
    ("crop_10pct",             "harmlos",            t_crop(0.10)),
    ("brightness_plus20",      "harmlos",            t_brightness(1.20)),
    ("brightness_minus20",     "harmlos",            t_brightness(0.80)),
    ("pixel_flip_1",           "boesartig_minimal",  t_pixel_flip(1)),
    ("pixel_flip_100",         "boesartig_minimal",  t_pixel_flip(100)),
]


@dataclass
class Result:
    original: str
    transformation: str
    kategorie: str
    sha_changed: bool
    phash_distance: int
    detected: bool
    correct: bool

    def as_row(self):
        return [self.original, self.transformation, self.kategorie,
                int(self.sha_changed), self.phash_distance,
                int(self.detected), int(self.correct)]


def ground_truth(kategorie: str) -> bool:
    return kategorie in ("boesartig_minimal", "faceswap")


def run_one(original: Path, name: str, kategorie: str,
            transformed_path: Path) -> Result:
    sha_orig = sha256_hash(original)
    sha_new = sha256_hash(transformed_path)
    p_orig = phash(original)
    p_new = phash(transformed_path)
    dist = p_orig - p_new
    detected = dist > PHASH_THRESHOLD
    truth = ground_truth(kategorie)
    correct = (detected == truth)
    return Result(original.name, name, kategorie,
                  sha_orig != sha_new, dist, detected, correct)


def main():
    if not ORIGINALS_DIR.exists():
        print(f"FEHLER: {ORIGINALS_DIR} existiert nicht.")
        return
    originals = sorted([p for p in ORIGINALS_DIR.iterdir()
                        if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    if not originals:
        print(f"FEHLER: keine Originale in {ORIGINALS_DIR}.")
        return

    tmp_dir = Path("_tmp_transformed")
    tmp_dir.mkdir(exist_ok=True)

    results: list[Result] = []
    for orig in originals:
        print(f"\nVerarbeite Original: {orig.name}")
        for name, kategorie, fn in TRANSFORMATIONS:
            ext = ".jpg" if "jpeg" in name else orig.suffix
            out = tmp_dir / f"{orig.stem}__{name}{ext}"
            try:
                fn(orig, out)
                results.append(run_one(orig, name, kategorie, out))
            except Exception as e:
                print(f"  [SKIP] {name}: {e}")
        if FACESWAP_DIR.exists():
            for fs in FACESWAP_DIR.iterdir():
                if fs.stem.startswith(orig.stem + "__faceswap_"):
                    tool = fs.stem.split("__faceswap_")[1]
                    name = f"faceswap_{tool}"
                    results.append(run_one(orig, name, "faceswap", fs))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["original", "transformation", "kategorie",
                    "sha_changed", "phash_distance", "detected", "correct"])
        for r in results:
            w.writerow(r.as_row())

    print("\n" + "=" * 60)
    print(f"ERGEBNIS-ZUSAMMENFASSUNG (n={len(results)} Tests)")
    print("=" * 60)

    by_cat: dict[str, list[Result]] = {}
    for r in results:
        by_cat.setdefault(r.kategorie, []).append(r)

    for cat, rs in by_cat.items():
        correct = sum(1 for r in rs if r.correct)
        false_pos = sum(1 for r in rs
                        if r.detected and not ground_truth(r.kategorie))
        false_neg = sum(1 for r in rs
                        if not r.detected and ground_truth(r.kategorie))
        dists = [r.phash_distance for r in rs]
        print(f"\n  {cat} (n={len(rs)}):")
        print(f"    korrekte Entscheidungen: {correct}/{len(rs)}"
              f"  ({100*correct/len(rs):.1f}%)")
        print(f"    False Positives:         {false_pos}")
        print(f"    False Negatives:         {false_neg}")
        print(f"    pHash-Distanz min/median/max: "
              f"{min(dists)}/{int(np.median(dists))}/{max(dists)}")

    print(f"\nCSV gespeichert: {OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
