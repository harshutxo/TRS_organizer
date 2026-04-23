import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

p21 = Image.open('p21_orig.jpg')
p22 = Image.open('p22_orig.jpg')

try:
    osd21 = pytesseract.image_to_osd(p21)
    print('p21 OSD:\n', osd21)
except Exception as e:
    print('p21 OSD error:', e)

try:
    osd22 = pytesseract.image_to_osd(p22)
    print('p22 OSD:\n', osd22)
except Exception as e:
    print('p22 OSD error:', e)
