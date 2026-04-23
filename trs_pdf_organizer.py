"""
TRS PDF Organizer (v3)
======================
Improvements over v2:
- Uses BOTH edge NCC AND perceptual hash similarity for smarter split-page pairing
- Sequential bias: pages that are already consecutive in the original are preferred as pairs
- Confidence-gated orientation correction

Usage:
    python trs_pdf_organizer.py [input.pdf] [output.pdf]
"""

import fitz  # PyMuPDF
import cv2
import numpy as np
import imagehash
from PIL import Image
import io
import os
import sys


# ─────────────────────────── CONFIGURATION ───────────────────────────────────

DPI = 150
DUPLICATE_HASH_THRESHOLD = 8        # pHash hamming distance for duplicate detection
ORIENTATION_CONFIDENCE_RATIO = 1.15 # ratio of best/2nd-best projection variance to apply rotation
SEQUENTIAL_BONUS = 0.12             # bonus added to pairing score if pages are consecutive

# ─────────────────────────── HELPERS ─────────────────────────────────────────

def page_to_pil(page: fitz.Page, dpi: int = DPI) -> Image.Image:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def perceptual_hash(img: Image.Image) -> imagehash.ImageHash:
    return imagehash.phash(img, hash_size=16)


def phash_similarity(h1: imagehash.ImageHash, h2: imagehash.ImageHash) -> float:
    """pHash similarity in [0,1]; 1 = identical."""
    max_bits = len(h1.hash.flatten())
    dist = h1 - h2
    return 1.0 - dist / max_bits


# ─────────────────────────── ORIENTATION DETECTION ───────────────────────────

def detect_rotation_needed(img_pil: Image.Image) -> int:
    """
    Returns CW rotation (0/90) needed to make the page upright.
    Uses horizontal projection profile variance — higher variance = clearer text rows.
    Only returns non-zero when confidence ratio is high enough.
    """
    gray = np.array(img_pil.convert("L"), dtype=np.uint8)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    def variance(img):
        return float(np.var(img.sum(axis=1).astype(float)))

    v0 = variance(binary)
    v90 = variance(cv2.rotate(binary, cv2.ROTATE_90_CLOCKWISE))

    if v90 > v0:
        ratio = v90 / v0 if v0 > 0 else 999
        if ratio >= ORIENTATION_CONFIDENCE_RATIO:
            return 90
    return 0


# ─────────────────────────── SPLIT-PAGE PAIRING ──────────────────────────────

def is_landscape(page: fitz.Page) -> bool:
    r = page.rect
    return r.width > r.height * 1.05


def extract_edge_strip(img_pil: Image.Image, side: str, frac: float = 0.20) -> np.ndarray:
    w, h = img_pil.size
    strip_w = max(int(w * frac), 10)
    box = (w - strip_w, 0, w, h) if side == "right" else (0, 0, strip_w, h)
    return np.array(img_pil.crop(box).convert("L"), dtype=np.float32)


def ncc(arr1: np.ndarray, arr2: np.ndarray) -> float:
    """Normalised cross-correlation mapped to [0,1]."""
    h = min(arr1.shape[0], arr2.shape[0])
    w = min(arr1.shape[1], arr2.shape[1])
    a = cv2.resize(arr1, (w, h))
    b = cv2.resize(arr2, (w, h))
    an = a - a.mean()
    bn = b - b.mean()
    denom = (np.linalg.norm(an) * np.linalg.norm(bn)) + 1e-8
    return (float(np.dot(an.flatten(), bn.flatten()) / denom) + 1) / 2


def pairing_score(info_i: dict, info_j: dict) -> float:
    """
    Combined score for i being the LEFT half and j being the RIGHT half.
      - Edge NCC: right-edge of i vs left-edge of j
      - pHash similarity: pages from the same original doc page look similar
      - Sequential bonus: if they were adjacent in the original PDF
    """
    r_strip = extract_edge_strip(info_i["img"], "right")
    l_strip = extract_edge_strip(info_j["img"], "left")
    edge_score = ncc(r_strip, l_strip)

    ph_sim = phash_similarity(info_i["phash"], info_j["phash"])

    seq_bonus = SEQUENTIAL_BONUS if abs(info_i["idx"] - info_j["idx"]) == 1 else 0

    # Weighted combination
    score = 0.5 * edge_score + 0.4 * ph_sim + seq_bonus
    return score


# ─────────────────────────── MAIN PROCESSING ─────────────────────────────────

def process_pdf(input_path: str, output_path: str):
    doc = fitz.open(input_path)
    n = len(doc)
    print(f"[INFO] Opened '{os.path.basename(input_path)}' -- {n} pages total")

    # ── Step 1: Render pages & compute metadata ─────────────────────────────
    print("[INFO] Rendering pages...")
    pages_info = []
    for i in range(n):
        page = doc[i]
        img = page_to_pil(page)
        pages_info.append({
            "idx": i,
            "img": img,
            "phash": perceptual_hash(img),
            "landscape": is_landscape(page),
            "rotation_needed": 0,
        })

    # ── Step 2: Orientation detection ──────────────────────────────────────
    print("[INFO] Detecting page orientation...")
    for info in pages_info:
        rot = detect_rotation_needed(info["img"])
        info["rotation_needed"] = rot
        if rot != 0:
            # Apply correction to the image for downstream analysis steps
            # PIL rotate is CCW; we need CW rotation, so negate
            info["img"] = info["img"].rotate(-rot, expand=True)
            print(f"  Page {info['idx']+1}: will rotate {rot} degrees CW")

    # ── Step 3: Duplicate removal ───────────────────────────────────────────
    print("[INFO] Removing duplicate pages...")
    kept = []
    removed = set()
    for i, info in enumerate(pages_info):
        if i in removed:
            continue
        dup = False
        for prev in kept:
            if (info["phash"] - prev["phash"]) <= DUPLICATE_HASH_THRESHOLD:
                print(f"  Page {info['idx']+1} is a duplicate of page "
                      f"{prev['idx']+1} -- skipped")
                removed.add(i)
                dup = True
                break
        if not dup:
            kept.append(info)
    print(f"  Kept {len(kept)} / {n} pages after duplicate removal")

    # ── Step 4: Pair landscape (split) pages ──────────────────────────────
    print("[INFO] Detecting and pairing split-page halves...")
    landscape = [p for p in kept if p["landscape"]]
    portrait  = [p for p in kept if not p["landscape"]]

    print(f"  Landscape pages (input#): {[p['idx']+1 for p in landscape]}")
    print(f"  Portrait pages  (input#): {[p['idx']+1 for p in portrait]}")

    pairs = []        # list of (left_info, right_info_or_None)
    used  = set()

    if len(landscape) >= 2:
        ls_n = len(landscape)

        # Build full score matrix
        score_matrix = np.zeros((ls_n, ls_n))
        for i in range(ls_n):
            for j in range(ls_n):
                if i != j:
                    score_matrix[i, j] = pairing_score(landscape[i], landscape[j])

        # Greedy optimal pairing (Hungarian-lite)
        while True:
            # Find global maximum in remaining un-used entries
            max_score = -1
            best_i = best_j = -1
            for i in range(ls_n):
                if i in used:
                    continue
                for j in range(ls_n):
                    if j in used or i == j:
                        continue
                    if score_matrix[i, j] > max_score:
                        max_score = score_matrix[i, j]
                        best_i, best_j = i, j

            if best_i < 0:
                break

            # Pair i (left) with j (right)
            pairs.append((landscape[best_i], landscape[best_j]))
            used.add(best_i)
            used.add(best_j)
            print(f"  Pair: input p{landscape[best_i]['idx']+1} + "
                  f"input p{landscape[best_j]['idx']+1}  "
                  f"[score={max_score:.3f}]")

        # Any remaining unpaired landscape pages
        for i in range(ls_n):
            if i not in used:
                pairs.append((landscape[i], None))
                print(f"  Standalone landscape: input p{landscape[i]['idx']+1}")
    else:
        for p in landscape:
            pairs.append((p, None))

    # Build lookup structures
    right_half_idxs  = {right["idx"] for _, right in pairs if right is not None}
    pair_map         = {left["idx"]: (left, right) for left, right in pairs}

    # ── Step 5: Determine final page order ─────────────────────────────────
    final_order = []
    seen = set()

    for info in kept:
        idx = info["idx"]
        if idx in seen or idx in right_half_idxs:
            continue

        if not info["landscape"]:
            final_order.append(info)
            seen.add(idx)
        else:
            left, right = pair_map[idx]
            final_order.append(left)
            seen.add(left["idx"])
            if right is not None:
                final_order.append(right)
                seen.add(right["idx"])

    # Safety: add anything missed
    for info in kept:
        if info["idx"] not in seen:
            final_order.append(info)
            seen.add(info["idx"])

    # ── Step 6: Build output PDF ────────────────────────────────────────────
    print("[INFO] Building output PDF...")
    out_doc = fitz.open()

    for info in final_order:
        out_doc.insert_pdf(doc, from_page=info["idx"], to_page=info["idx"])
        new_page = out_doc[-1]
        rot = info["rotation_needed"]
        if rot != 0:
            new_page.set_rotation((new_page.rotation + rot) % 360)

    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n[DONE] Output saved: {output_path}")
    print(f"  Input pages       : {n}")
    print(f"  Duplicates removed: {len(removed)}")
    print(f"  Output pages      : {len(final_order)}")
    print("\n[INFO] Final page order (Output <- Input):")
    for out_i, info in enumerate(final_order):
        tags = []
        if info["landscape"]:
            tags.append("landscape/split")
        if info["rotation_needed"] != 0:
            tags.append(f"rotated {info['rotation_needed']}deg CW")
        tag_str = "  [" + ", ".join(tags) + "]" if tags else ""
        print(f"  Output p{out_i+1:02d} <- Input p{info['idx']+1:02d}{tag_str}")


# ─────────────────────────── ENTRY POINT ─────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        input_pdf  = r"d:\TRS_organizer\30 year doc loc 63.pdf"
        output_pdf = r"d:\TRS_organizer\30 year doc loc 63_organized.pdf"
    else:
        input_pdf  = sys.argv[1]
        output_pdf = sys.argv[2] if len(sys.argv) > 2 else \
                     input_pdf.replace(".pdf", "_organized.pdf")

    process_pdf(input_pdf, output_pdf)
