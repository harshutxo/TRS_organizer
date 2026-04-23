import fitz

def stitch_pages(pdf_path, p1_idx, p2_idx, out_path):
    doc = fitz.open(pdf_path)
    p1 = doc[p1_idx]
    p2 = doc[p2_idx]
    
    r1 = p1.rect
    r2 = p2.rect
    
    # Create new document and page
    new_doc = fitz.open()
    new_page = new_doc.new_page(width=r1.width + r2.width, height=max(r1.height, r2.height))
    
    # Draw left page
    new_page.show_pdf_page(fitz.Rect(0, 0, r1.width, r1.height), doc, p1_idx)
    # Draw right page
    new_page.show_pdf_page(fitz.Rect(r1.width, 0, r1.width + r2.width, r2.height), doc, p2_idx)
    
    new_doc.save(out_path)
    new_doc.close()
    doc.close()
    print(f"Stitched {p1_idx} and {p2_idx} to {out_path}")

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stitch two PDF pages side-by-side.")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    parser.add_argument("p1_idx", type=int, help="Index of the first page (left side, 0-indexed)")
    parser.add_argument("p2_idx", type=int, help="Index of the second page (right side, 0-indexed)")
    parser.add_argument("out_path", help="Path to the output stitched PDF file")
    
    args = parser.parse_args()
    stitch_pages(args.pdf_path, args.p1_idx, args.p2_idx, args.out_path)
