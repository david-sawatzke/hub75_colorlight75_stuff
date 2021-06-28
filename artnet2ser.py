#!/usr/bin/env python3
# Pipe output to file, pipe output to serial with device running
import socket
ip = "127.0.0.1"
port = 6454

udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
udp_socket.bind((ip, port))
f = open("artnetdata", "wb")
f.write(b"\nhidden_nonechowrite\n")
while True:
    data, adr = udp_socket.recvfrom(1024 * 1024)
    if data[0:8] == b"Art-Net\0":
        f.write(b"nb")
        f.write(bytearray([len(data) & 0xFF, (len(data) >> 8) & 0xFF]))
        f.write(data)
