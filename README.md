# TRS PDF Organizer

A robust Python utility to automatically clean up, organize, and reconstruct scanned land record PDFs or similar document collections.

## Features

- **Auto-Rotation & Structural Deskew:** Detects page text orientation using projection profiles and deskews pages using Hough line detection to align the baseline/grid structure.
- **Duplicate Removal:** Identifies and removes duplicate pages using Perceptual Hashing (pHash) with a customizable similarity threshold.
- **Split-Page Reconstruction:** Intelligently pairs halves of landscape pages that have been split across multiple portrait pages. Uses a combination of edge Normalized Cross-Correlation (NCC) and perceptual hashing to find the perfect match.
- **Sequential Context:** Prioritizes keeping originally consecutive pages together when rebuilding the document.

## Dependencies

The script relies on the following Python packages:
- `PyMuPDF` (fitz)
- `opencv-python` (cv2)
- `numpy`
- `Pillow`
- `ImageHash`

You can install them via pip:
```bash
pip install PyMuPDF opencv-python numpy Pillow ImageHash
```

## Usage

Run the main script via the command line, providing an input PDF and optionally an output path:

```bash
python trs_pdf_organizer.py "path/to/input.pdf" "path/to/output.pdf"
```

If the output path is omitted, the script will automatically create a file named `[original_name]_organized.pdf`.

## How it works (v3 Pipeline)

1. **Render & Hash:** Extracts each page as an image and computes a perceptual hash.
2. **Orientation Fix:** Checks 4 possible rotations (0, 90, 180, 270) and rotates the page so text rows align horizontally.
3. **De-duplication:** Compares hashes of all pages to eliminate redundant scans.
4. **Landscape Pairing:** Groups portrait pages back into their original landscape spread if they were split during scanning.
5. **PDF Assembly:** Compiles the clean, ordered, and oriented pages into a fresh, optimized PDF file.
