#!/usr/bin/env python3

import time
from litex import RemoteClient

wb = RemoteClient()
wb.open()

wb.write(0x90000000, 0xFF)
time.sleep(1)
wb.write(0x90000000, 0xFF00)
time.sleep(1)
wb.write(0x90000000, 0xFF0000)
time.sleep(1)
wb.write(0x90000000, 0x000000)
wb.close()
