# TRS PDF Organizer

A robust Python utility to automatically clean up, organize, and reconstruct scanned land record PDFs or similar document collections.

## Features

- **Auto-Rotation & Structural Deskew:** Detects page text orientation using projection profiles and deskews pages using Hough line detection to align the baseline/grid structure.
- **Duplicate Removal:** Identifies and removes duplicate pages using Perceptual Hashing (pHash) with a customizable similarity threshold.
- **Split-Page Reconstruction:** Intelligently pairs halves of landscape pages that have been split across multiple portrait pages. Uses a combination of edge Normalized Cross-Correlation (NCC), perceptual hashing, and OCR-extracted numbers to find the perfect match.
- **Sequential Context:** Prioritizes keeping originally consecutive pages together when rebuilding the document.
- **Hybrid OCR:** Extracts page numbers using Tesseract for clean text, with fallbacks to EasyOCR and OpenAI GPT-4o for handwritten or blurry images, improving pairing accuracy.
- **Batch Processing:** Supports processing entire directories of PDFs with automatic output organization.

## Dependencies

The script relies on the following Python packages:
- `PyMuPDF` (fitz)
- `opencv-python` (cv2)
- `numpy`
- `Pillow`
- `ImageHash`
- `pytesseract`
- `easyocr`
- `openai` (optional, for LLM-based OCR fallback)

You can install them via pip:
```bash
pip install PyMuPDF opencv-python numpy Pillow ImageHash pytesseract easyocr openai
```

Note: Tesseract OCR must be installed separately. Download from [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) and update the path in the script if necessary.

For OpenAI LLM support, set your API key as an environment variable: `OPENAI_API_KEY=your_key_here`

## Usage

Run the main script via the command line, providing an input PDF or directory and optionally an output path:

```bash
# Process a single PDF
python trs_pdf_organizer.py "path/to/input.pdf" -o "path/to/output.pdf"

# Process all PDFs in a directory
python trs_pdf_organizer.py "path/to/input_directory" -o "path/to/output_directory"
```

If the output path is omitted, the script will automatically create organized PDFs in an 'output' folder.

## How it works (v3 Pipeline)

1. **Render & Hash:** Extracts each page as an image and computes a perceptual hash.
2. **Orientation & Deskew:** Checks 4 possible rotations (0, 90, 180, 270) and deskews pages using Hough line detection to align text and structure.
3. **OCR Number Extraction:** Extracts page numbers using Tesseract, with EasyOCR and OpenAI GPT-4o fallbacks for handwritten or blurry text.
4. **De-duplication:** Compares hashes of all pages to eliminate redundant scans.
5. **Landscape Pairing:** Groups portrait pages back into their original landscape spread if they were split during scanning, using edge similarity, hashes, and OCR numbers.
6. **PDF Assembly:** Compiles the clean, ordered, and oriented pages into a fresh, optimized PDF file.
