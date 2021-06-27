#!/usr/bin/env python3
# Pipe output to file, pipe output to serial with device running
import socket
ip = "127.0.0.1"
port = 6454

udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
udp_socket.bind((ip, port))

print("hidden_nonechowrite")
while True:
    data, adr = udp_socket.recvfrom(1024 * 1024)
    if data[0:8] == b"Art-Net\0":
        length = (data[16] << 8) | data[17]
        universe = data[14] + (data[15] << 8)
        for i in range(length//3):
            adr = 18 + i * 3
            rgb = data[adr] + (int(data[adr + 1]) << 8) + (data[adr + 2] << 16)
            print("write " + hex(0x40200000 + (universe * 170 + i) * 4) + " " + hex(rgb))

print("Bye")
