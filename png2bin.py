#!/usr/bin/env python3
# To flash: ecpprog -o 1536k img_data.bin

import png


def _get_image_array():
    r = png.Reader(file=open("./demo_img.png", "rb"))
    img = r.read()
    assert img[0] == 128
    assert img[1] == 64
    pixels = list(img[2])
    out_array = []
    for arr in pixels:
        # Assue rgb
        for i in range(img[0]):
            red = arr[i * 3 + 0]
            green = arr[i * 3 + 1]
            blue = arr[i * 3 + 2]
            out_array.append(red | green << 8 | blue << 16)
    return (out_array, img[0], img[1])


def write_32bit(filehandler, data):
    byte_arr = [data & 0xFF, (data >> 8) & 0xFF, (data >> 16) & 0xFF, (data >> 24) & 0xFF]
    f.write(bytearray(byte_arr))

img = _get_image_array()

f = open("img_data.bin", "wb")
width = img[1]
write_32bit(f, 0 << 31 | (width & 0xFFFF))
write_32bit(f, len(img[0]))
write_32bit(f, 0xD1581A40)
write_32bit(f, 0xDA5A0001)
for _ in range(240//4):
    write_32bit(f, 0x0)
for data in img[0]:
    write_32bit(f, data)
f.close()
