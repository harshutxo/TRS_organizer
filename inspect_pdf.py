
import argparse
import fitz  # pymupdf


def inspect_pdf(pdf_path: str) -> None:
    doc = fitz.open(pdf_path)
    print(f"Total pages: {len(doc)}")
    print(f"PDF metadata: {doc.metadata}\n")

    for index, page in enumerate(doc):
        rect = page.rect
        print(f"Page {index + 1}: width={rect.width:.1f}, height={rect.height:.1f}, rotation={page.rotation}")

    doc.close()


def main():
    parser = argparse.ArgumentParser(description="Inspect a PDF for page size and rotation metadata.")
    parser.add_argument("pdf_path", help="Path to the input PDF file")
    args = parser.parse_args()
    inspect_pdf(args.pdf_path)


if __name__ == "__main__":
    main()
