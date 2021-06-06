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

base_adr = 0x80000000
f = open("romdump.bin", "w+b")
for adr in range(base_adr, base_adr + 0x200000, 512):
    print(hex(adr))
    data = wb.read(adr, length=128)
    byte_arr = []
    for byte in data:
        byte_arr += [byte & 0xFF, (byte >> 8) & 0xFF, (byte >> 16) & 0xFF, (byte >> 24) & 0xFF]
    f.write(bytearray(byte_arr))

f.close()
