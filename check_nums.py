import trs_pdf_organizer as tpo
import fitz
import pytesseract
import re
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
doc = fitz.open(r'input\Item no. 3.pdf')

def get_nums(p_idx):
    page = doc[p_idx]
    img = tpo.page_to_pil(page)
    # Get OSD rotation
    rot = tpo.detect_rotation_needed(img)
    if rot != 0:
        img = img.rotate(-rot, expand=True, resample=Image.BICUBIC)
    
    img.thumbnail((1000, 1000))
    text = pytesseract.image_to_string(img, config='--psm 6 digits')
    nums = sorted(list(set([int(n) for n in re.findall(r'\d+', text) if len(n) <= 3])))
    return nums

for i in range(19, 23):
    print(f"p{i+1}:", get_nums(i))
