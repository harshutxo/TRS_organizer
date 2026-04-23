"""
Generate thumbnail previews of PDFs for visual inspection.
"""
import argparse
import io
import math
import fitz
from PIL import Image, ImageDraw


def make_grid_thumbnail(pdf_path, out_path, cols=4, thumb_w=300):
    doc = fitz.open(pdf_path)
    pages = len(doc)
    rows = math.ceil(pages / cols)

    thumbs = []
    for page_index, page in enumerate(doc):
        mat = fitz.Matrix(thumb_w / page.rect.width, thumb_w / page.rect.width)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, img.width - 1, 28], fill=(30, 30, 80))
        draw.text((6, 4), f"Page {page_index + 1}", fill=(255, 220, 0))
        thumbs.append(img)

    if not thumbs:
        raise ValueError("No pages found in PDF")

    thumb_h = thumbs[0].height
    grid_w = cols * thumb_w + (cols - 1) * 4
    grid_h = rows * thumb_h + (rows - 1) * 4
    grid = Image.new("RGB", (grid_w, grid_h), (60, 60, 60))

    for index, thumb in enumerate(thumbs):
        row = index // cols
        col = index % cols
        x = col * (thumb_w + 4)
        y = row * (thumb_h + 4)
        grid.paste(thumb, (x, y))

    grid.save(out_path)
    doc.close()
    print(f"Saved: {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate a grid preview image for a PDF file.")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument("out_path", help="Output preview image path")
    parser.add_argument("--cols", type=int, default=4, help="Number of columns in the grid")
    parser.add_argument("--thumb-width", type=int, default=300, help="Width of each thumbnail")
    args = parser.parse_args()

    make_grid_thumbnail(args.pdf_path, args.out_path, cols=args.cols, thumb_w=args.thumb_width)


if __name__ == "__main__":
    main()
