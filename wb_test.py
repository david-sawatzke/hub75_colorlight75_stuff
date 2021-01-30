#!/usr/bin/env python3

import time
from litex import RemoteClient

wb = RemoteClient()
wb.open()

# Shift palette
# wb.write(0x90000000, 0xFF)
# time.sleep(1)
# wb.write(0x90000000, 0xFF00)
# time.sleep(1)
# wb.write(0x90000000, 0xFF0000)
# time.sleep(1)
# wb.write(0x90000000, 0x000000)

base_ram_adr = 0x40000000
cols = 64
width = 64
height = 7
on = 7
off = 0
for i in range(height):
    for j in range(width):
        wb.write(base_ram_adr + (j + i *cols) * 4, off)
        time.sleep(0.01)

time.sleep(1)
print("hi")
for i in range(height):
    for j in range(width):
        wb.write(base_ram_adr + (j + i *cols) * 4, on)
        time.sleep(0.01)


wb.close()
