"""
Generate thumbnail previews of both input and output PDFs for visual inspection.
"""
import fitz
from PIL import Image
import os
import math

def make_grid_thumbnail(pdf_path, out_path, cols=4, thumb_w=300):
    doc = fitz.open(pdf_path)
    n = len(doc)
    rows = math.ceil(n / cols)
    
    thumbs = []
    for i, page in enumerate(doc):
        mat = fitz.Matrix(thumb_w / page.rect.width, thumb_w / page.rect.width)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        # Add page number label
        from PIL import ImageDraw, ImageFont
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, img.width-1, 28], fill=(30, 30, 80))
        draw.text((6, 4), f"Page {i+1}", fill=(255, 220, 0))
        thumbs.append(img)
    
    thumb_h = int(thumbs[0].height) if thumbs else 400
    grid_w = cols * thumb_w + (cols - 1) * 4
    grid_h = rows * thumb_h + (rows - 1) * 4
    grid = Image.new("RGB", (grid_w, grid_h), (60, 60, 60))
    
    for i, thumb in enumerate(thumbs):
        row = i // cols
        col = i % cols
        x = col * (thumb_w + 4)
        y = row * (thumb_h + 4)
        grid.paste(thumb, (x, y))
    
    grid.save(out_path)
    print(f"Saved: {out_path}")
    doc.close()

make_grid_thumbnail(
    r"d:\TRS_organizer\30 year doc loc 63.pdf",
    r"d:\TRS_organizer\preview_input.jpg"
)
make_grid_thumbnail(
    r"d:\TRS_organizer\30 year doc loc 63_organized.pdf",
    r"d:\TRS_organizer\preview_output.jpg"
)
