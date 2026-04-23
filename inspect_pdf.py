
import fitz  # pymupdf
import sys

if len(sys.argv) > 1:
    pdf_path = sys.argv[1]
else:
    pdf_path = r"d:\TRS_organizer\30 year doc loc 63.pdf"
doc = fitz.open(pdf_path)

print(f"Total pages: {len(doc)}")
print(f"PDF metadata: {doc.metadata}")
print()

for i, page in enumerate(doc):
    rect = page.rect
    print(f"Page {i+1}: width={rect.width:.1f}, height={rect.height:.1f}, rotation={page.rotation}")
