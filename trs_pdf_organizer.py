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

import argparse
import fitz  # PyMuPDF
import cv2
import numpy as np
import imagehash
from PIL import Image
import io
import os
import pytesseract
import re

# Configure Tesseract path (update if necessary)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


# ─────────────────────────── CONFIGURATION ───────────────────────────────────

DPI = 150
DUPLICATE_HASH_THRESHOLD = 8        # pHash hamming distance for duplicate detection
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


def detect_crease(img_pil: Image.Image) -> str:
    """
    Detects if a dark vertical shadow (book crease) exists on the left or right edge.
    Returns 'left', 'right', or 'none'.
    """
    w, h = img_pil.size
    # Sample narrow strips from the extreme left and right
    l_strip = np.array(img_pil.crop((0, 0, max(1, int(w*0.05)), h)).convert("L"))
    r_strip = np.array(img_pil.crop((max(0, int(w*0.95)), 0, w, h)).convert("L"))
    
    l_val = l_strip.mean()
    r_val = r_strip.mean()
    
    # If one edge is significantly darker (crease shadow)
    if l_val < r_val - 8:
        return "left"
    elif r_val < l_val - 8:
        return "right"
    return "none"


def detect_skew_hough(img_pil: Image.Image) -> float:
    """
    Uses Hough Line Transform to find the primary angle of lines in the page.
    Returns the skew angle in degrees (usually between -45 and 45).
    """
    gray = np.array(img_pil.convert("L"), dtype=np.uint8)
    # Thresholding to emphasize lines
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Detect edges
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)
    
    # Hough Line Transform (Probabilistic)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, 
                            minLineLength=int(img_pil.width * 0.2), 
                            maxLineGap=20)
    
    if lines is None:
        return 0.0

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Map to range [-45, 45] around the nearest 90-degree increment
        # This helps find the "straightness" regardless of 0/90/180/270 orientation
        angle = (angle + 45) % 90 - 45
        angles.append(angle)
    
    if not angles:
        return 0.0
        
    return float(np.median(angles))

def create_pdf_page_from_image(doc: fitz.Document, img_pil: Image.Image) -> fitz.Page:
    """Insert a processed PIL image into a new PDF page, preserving deskew and rotation."""
    buf = io.BytesIO()
    img_pil.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    page = doc.new_page(width=img_pil.width, height=img_pil.height)
    page.insert_image(fitz.Rect(0, 0, img_pil.width, img_pil.height), stream=img_bytes)
    return page


def stitch_pages(left_img: Image.Image, right_img: Image.Image) -> Image.Image:
    """Compose two page halves side-by-side into one combined image."""
    width = left_img.width + right_img.width
    height = max(left_img.height, right_img.height)
    stitched = Image.new("RGB", (width, height), color=(255, 255, 255))
    stitched.paste(left_img, (0, 0))
    stitched.paste(right_img, (left_img.width, 0))
    return stitched

# ─────────────────────────── ORIENTATION DETECTION ───────────────────────────

def detect_rotation_needed(img_pil: Image.Image) -> int:
    """
    Returns CW rotation (0/90/180/270) needed to make the page upright.
    Combines structural line analysis with Tesseract OSD.
    """
    # 1. Structural approach: Check if most lines are vertical or horizontal
    # This helps distinguish 0 from 90/270
    gray = np.array(img_pil.convert("L"), dtype=np.uint8)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    def line_strength(img):
        # Measure variance of projections
        return float(np.var(img.sum(axis=1).astype(float)))

    v0 = line_strength(binary)
    v90 = line_strength(cv2.rotate(binary, cv2.ROTATE_90_CLOCKWISE))
    
    structural_orientation = 0
    if v90 > v0 * 1.1:
        structural_orientation = 90
        
    # 2. Tesseract OSD (to confirm "Up" vs "Down" and refine 90 vs 270)
    try:
        osd = pytesseract.image_to_osd(img_pil)
        for line in osd.splitlines():
            if 'Rotate:' in line:
                tess_rot = int(line.split(':')[1].strip())
                return tess_rot
    except Exception:
        pass

    return structural_orientation


# ─────────────────────────── SPLIT-PAGE PAIRING ──────────────────────────────

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
      - Crease matching: i should have crease on right, j on left
      - pHash similarity: pages from same original doc page look similar
      - Sequential bonus: if they were adjacent in original PDF
      - OCR Sequence: if numbers on i transition logically to j
    """
    r_strip = extract_edge_strip(info_i["img"], "right")
    l_strip = extract_edge_strip(info_j["img"], "left")
    edge_score = ncc(r_strip, l_strip)

    ph_sim = phash_similarity(info_i["phash"], info_j["phash"])
    seq_bonus = SEQUENTIAL_BONUS if abs(info_i["idx"] - info_j["idx"]) == 1 else 0

    # Crease consistency (Huge boost for Left-Right spine alignment)
    crease_bonus = 0
    c_i = info_i.get("crease", "none")
    c_j = info_j.get("crease", "none")
    if c_i == "right" and c_j == "left":
        crease_bonus = 0.4
    elif c_i == "right" or c_j == "left":
        crease_bonus = 0.1

    # OCR sequence bonus
    ocr_bonus = 0
    if info_i.get("numbers") and info_j.get("numbers"):
        if min(info_i["numbers"]) < min(info_j["numbers"]):
            ocr_bonus = 0.05
        max_i = max(info_i["numbers"])
        min_j = min(info_j["numbers"])
        if abs(max_i + 1 - min_j) <= 1:
            ocr_bonus += 0.15

    # Weighted combination
    score = 0.5 * edge_score + 0.3 * ph_sim + seq_bonus + crease_bonus + ocr_bonus
    return score


# ─────────────────────────── MAIN PROCESSING ─────────────────────────────────

def process_pdf(input_path: str, output_path: str):
    doc = fitz.open(input_path)
    n = len(doc)
    print(f"[INFO] Opened '{os.path.basename(input_path)}' -- {n} pages total", flush=True)

    # ── Step 1: Render pages & compute metadata ─────────────────────────────
    print("[INFO] Rendering pages...", flush=True)
    pages_info = []
    for i in range(n):
        page = doc[i]
        img = page_to_pil(page)
        pages_info.append({
            "idx": i,
            "img": img,
            "phash": perceptual_hash(img),
            "landscape": img.width > img.height * 1.05,
            "rotation_needed": 0,
            "numbers": [],
            "crease": "none",
        })

    # ── Step 2: Orientation, OCR & Crease Detection ────────────────────────
    print("[INFO] Applying structural deskew, orientation, and crease detection...", flush=True)
    for info in pages_info:
        # Optimization: Resize for analysis
        ana_img = info["img"].copy()
        ana_img.thumbnail((1000, 1000))

        # 1. Structural Deskew (Hough Lines)
        skew = detect_skew_hough(ana_img)
        if abs(skew) > 0.5:
            # Rotate PIL image (expand=True to avoid cropping corners)
            info["img"] = info["img"].rotate(-skew, expand=True, resample=Image.BICUBIC)
            ana_img = ana_img.rotate(-skew, expand=True)
            print(f"  Page {info['idx']+1}: deskewed {skew:.2f}°", flush=True)

        # 2. Macro Orientation (OSD + Line Projection)
        rot = detect_rotation_needed(ana_img)
        info["rotation_needed"] = rot
        if rot != 0:
            info["img"] = info["img"].rotate(-rot, expand=True)
            ana_img = ana_img.rotate(-rot, expand=True)
            print(f"  Page {info['idx']+1}: rotated {rot}° CW", flush=True)

        # 3. Detect crease shadow
        info["crease"] = detect_crease(info["img"])

        # 4. Extract digits
        try:
            text = pytesseract.image_to_string(ana_img, config='--psm 6 digits')
            nums = [int(n) for n in re.findall(r'\d+', text) if len(n) <= 3] 
            info["numbers"] = sorted(list(set(nums)))
        except Exception:
            pass

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
                      f"{prev['idx']+1} -- skipped", flush=True)
                removed.add(i)
                dup = True
                break
        if not dup:
            kept.append(info)
    print(f"  Kept {len(kept)} / {n} pages after duplicate removal", flush=True)

    # ── Step 4: Pair split pages ───────────────────────────────────────────
    print("[INFO] Detecting and pairing split-page halves...")

    pairs = []        # list of (left_info, right_info_or_None)
    used  = set()

    n_kept = len(kept)
    if n_kept >= 2:
        # Build full score matrix for all kept pages
        score_matrix = np.zeros((n_kept, n_kept))
        for i in range(n_kept):
            for j in range(n_kept):
                if i != j:
                    score_matrix[i, j] = pairing_score(kept[i], kept[j])

        # Greedy optimal pairing with a threshold
        PAIRING_THRESHOLD = 0.50
        while True:
            max_score = -1
            best_i = best_j = -1
            for i in range(n_kept):
                if i in used:
                    continue
                for j in range(n_kept):
                    if j in used or i == j:
                        continue
                    if score_matrix[i, j] > max_score:
                        max_score = score_matrix[i, j]
                        best_i, best_j = i, j

            if best_i < 0 or max_score < PAIRING_THRESHOLD:
                break

            # Pair i (left) with j (right)
            pairs.append((kept[best_i], kept[best_j]))
            used.add(best_i)
            used.add(best_j)
            print(f"  Pair: input p{kept[best_i]['idx']+1} + "
                  f"input p{kept[best_j]['idx']+1}  "
                  f"[score={max_score:.3f}]", flush=True)

    # Any remaining unpaired pages
    for i in range(n_kept):
        if i not in used:
            pairs.append((kept[i], None))

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

        if idx in pair_map and pair_map[idx][1] is not None:
            left, right = pair_map[idx]
            final_order.append({"type": "stitched", "left": left, "right": right})
            seen.add(left["idx"])
            seen.add(right["idx"])
        else:
            final_order.append({"type": "single", "info": info})
            seen.add(idx)

    # Safety: add anything missed
    for info in kept:
        if info["idx"] not in seen:
            final_order.append({"type": "single", "info": info})
            seen.add(info["idx"])

    # ── Step 6: Build output PDF ────────────────────────────────────────────
    print("[INFO] Building output PDF...", flush=True)
    out_doc = fitz.open()

    for item in final_order:
        if item["type"] == "single":
            info = item["info"]
            create_pdf_page_from_image(out_doc, info["img"])
        else:
            left_info = item["left"]
            right_info = item["right"]
            corrected = stitch_pages(left_info["img"], right_info["img"])
            new_page = create_pdf_page_from_image(out_doc, corrected)

            # Preserve the original pipeline behavior for landscape stitched pages.
            if new_page.rect.width > new_page.rect.height:
                new_page.set_rotation(90)

    out_doc.save(output_path, garbage=4, deflate=True, clean=True)
    out_doc.close()
    doc.close()

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n[DONE] Output saved: {output_path}")
    print(f"  Input pages       : {n}")
    print(f"  Duplicates removed: {len(removed)}")
    print(f"  Output pages      : {len(final_order)}")
    print("\n[INFO] Final page order (Output <- Input):")
    for out_i, item in enumerate(final_order):
        if item["type"] == "single":
            info = item["info"]
            tags = []
            if info["landscape"]:
                tags.append("landscape/unpaired")
            if info["rotation_needed"] != 0:
                tags.append(f"rotated {info['rotation_needed']}deg CW")
            tag_str = "  [" + ", ".join(tags) + "]" if tags else ""
            print(f"  Output p{out_i+1:02d} <- Input p{info['idx']+1:02d}{tag_str}")
        else:
            left_info = item["left"]
            right_info = item["right"]
            print(f"  Output p{out_i+1:02d} <- [STITCHED] Input p{left_info['idx']+1:02d} (Left) + Input p{right_info['idx']+1:02d} (Right)")


import argparse

# ─────────────────────────── ENTRY POINT ─────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TRS PDF Organizer (v3) - Clean, rotate, and pair split PDF pages.")
    parser.add_argument("input", help="Path to an input PDF file or a directory containing PDFs")
    parser.add_argument("-o", "--output", help="Output path (file or directory). Defaults to 'output' folder.")
    
    args = parser.parse_args()
    
    input_path = args.input
    
    if os.path.isfile(input_path):
        # Single file processing
        if not input_path.lower().endswith(".pdf"):
            print(f"[ERROR] '{input_path}' is not a PDF file.")
            return
            
        if args.output:
            output_path = args.output
        else:
            # Default output: output folder or same folder with suffix
            out_dir = "output"
            if not os.path.exists(out_dir):
                os.makedirs(out_dir)
            basename = os.path.basename(input_path)
            output_path = os.path.join(out_dir, basename.replace(".pdf", "_organized.pdf"))
            
        process_pdf(input_path, output_path)
        
    elif os.path.isdir(input_path):
        # Directory processing
        pdfs = [f for f in os.listdir(input_path) if f.lower().endswith(".pdf")]
        if not pdfs:
            print(f"[WARNING] No PDF files found in '{input_path}'")
            return
            
        out_dir = args.output if args.output else "output"
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
            
        print(f"[INFO] Found {len(pdfs)} PDFs in '{input_path}'. Processing...")
        for pdf in pdfs:
            in_file = os.path.join(input_path, pdf)
            out_file = os.path.join(out_dir, pdf.replace(".pdf", "_organized.pdf"))
            try:
                process_pdf(in_file, out_file)
            except Exception as e:
                print(f"[ERROR] Failed to process '{pdf}': {e}")
    else:
        print(f"[ERROR] Input path '{input_path}' does not exist.")

if __name__ == "__main__":
    main()
