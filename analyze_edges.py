import argparse
import numpy as np
from PIL import Image


def edge_brightness(img: np.ndarray) -> dict:
    h, w = img.shape
    return {
        'top': img[: int(h * 0.05), :].mean(),
        'bottom': img[int(h * 0.95) :, :].mean(),
        'left': img[:, : int(w * 0.05)].mean(),
        'right': img[:, int(w * 0.95) :].mean(),
    }


def analyze_image(path: str) -> None:
    img = np.array(Image.open(path).convert('L'))
    brightness = edge_brightness(img)
    print(f"{path}: {brightness}")


def main():
    parser = argparse.ArgumentParser(description="Analyze edge brightness for scanned images.")
    parser.add_argument("images", nargs="+", help="Image paths to analyze")
    args = parser.parse_args()

    for image_path in args.images:
        analyze_image(image_path)


if __name__ == "__main__":
    main()
