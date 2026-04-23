import numpy as np
from PIL import Image

p21 = np.array(Image.open('p21_orig.jpg').convert('L'))
p22 = np.array(Image.open('p22_orig.jpg').convert('L'))

def edge_brightness(img):
    h, w = img.shape
    return {
        'top': img[:int(h*0.05), :].mean(),
        'bottom': img[int(h*0.95):, :].mean(),
        'left': img[:, :int(w*0.05)].mean(),
        'right': img[:, int(w*0.95):].mean()
    }

print('p21:', edge_brightness(p21))
print('p22:', edge_brightness(p22))
