import argparse
import fitz


def stitch_pages(pdf_path: str, left_index: int, right_index: int, out_path: str) -> None:
    doc = fitz.open(pdf_path)
    left_page = doc[left_index]
    right_page = doc[right_index]

    left_rect = left_page.rect
    right_rect = right_page.rect

    output = fitz.open()
    page = output.new_page(width=left_rect.width + right_rect.width, height=max(left_rect.height, right_rect.height))
    page.show_pdf_page(fitz.Rect(0, 0, left_rect.width, left_rect.height), doc, left_index)
    page.show_pdf_page(
        fitz.Rect(left_rect.width, 0, left_rect.width + right_rect.width, right_rect.height),
        doc,
        right_index,
    )

    output.save(out_path)
    output.close()
    doc.close()
    print(f"Stitched pages {left_index} and {right_index} to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Stitch two PDF pages side-by-side.")
    parser.add_argument("pdf_path", help="PDF file path")
    parser.add_argument("left_index", type=int, help="Left page index (0-based)")
    parser.add_argument("right_index", type=int, help="Right page index (0-based)")
    parser.add_argument("out_path", help="Output PDF path")
    args = parser.parse_args()
    stitch_pages(args.pdf_path, args.left_index, args.right_index, args.out_path)


if __name__ == "__main__":
    main()
