#!/usr/bin/env python3

import png


def _get_image_array():
    r = png.Reader(file=open("../demo_img.png", "rb"))
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
    return out_array


def _get_indexed_image_arrays():
    r = png.Reader(file=open("../demo_img_indexed.png", "rb"))
    img = r.read()
    assert img[0] == 64
    assert img[1] == 64
    pixels = list(img[2])
    out_array = []
    # Get image data
    for arr in pixels:
        for i in range(64):
            out_array.append(arr[i])
    # Get palette data
    # rgbrgbrgb
    palette = []
    # Probably rgb?
    png_palette = img[3]["palette"]
    for a in png_palette:
        palette.append(a[0] | a[1] << 8 | a[2] << 16)
    return (out_array, palette)


img = _get_image_array()
img_indexed = _get_indexed_image_arrays()

f = open("img_data.c", "w")
f.write("#include <stdint.h>\n")

f.write("uint32_t img_data[] = {")
first_byte = True
for data_byte in img:
    if first_byte:
        f.write(hex(data_byte) + "\n")
        first_byte = False
    else:
        f.write("   ," + hex(data_byte) + "\n")

f.write("};")
f.write("uint32_t img_data_len = " + hex(len(img)) + ";")

f.write("uint32_t img_indexed_data[] = {")
first_byte = True
for data_byte in img_indexed[0]:
    if first_byte:
        f.write(hex(data_byte) + "\n")
        first_byte = False
    else:
        f.write("   ," + hex(data_byte) + "\n")

f.write("};")

f.write("uint32_t img_indexed_data_len = " + hex(len(img_indexed[0])) + ";")

f.write("uint32_t palette_data[] = {")
first_byte = True
for data_byte in img_indexed[1]:
    if first_byte:
        f.write(hex(data_byte) + "\n")
        first_byte = False
    else:
        f.write("   ," + hex(data_byte) + "\n")


f.write("};")

f.write("uint32_t palette_data_len = " + hex(len(img_indexed[1])) + ";")

f.close()
