#!/usr/bin/env python3

import png


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


img = _get_indexed_image_arrays()

f = open("img_indexed.c", "w")
f.write("#include <stdint.h>\n")
f.write("uint32_t img_data[] = {")
first_byte = True
for data_byte in img[0]:
    if first_byte:
        f.write(hex(data_byte) + "\n")
        first_byte = False
    else:
        f.write("   ," + hex(data_byte) + "\n")


f.write("};")

f.write("uint32_t img_data_len = " + hex(len(img[0])) + ";")

f.write("uint32_t palette_data[] = {")
first_byte = True
for data_byte in img[1]:
    if first_byte:
        f.write(hex(data_byte) + "\n")
        first_byte = False
    else:
        f.write("   ," + hex(data_byte) + "\n")


f.write("};")

f.write("uint32_t palette_data_len = " + hex(len(img[1])) + ";")

f.close()
