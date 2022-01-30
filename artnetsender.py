#!/usr/bin/env python3
# Hacky test script to generate individual packets

import socket
import time


def prepare_artnet_packet(universe, a):
    color_data = [[255, 000, a] for _ in range(170)]

    color_data[0] = [0, 255, 0]
    color_data[1] = [0, 0, 255]
    color_data[2] = [0, 255, 255]
    color_data[universe] = [255, 255, 255]
    # color_data[2] = [0, 0, 0]
    # color_data[3] = [0, 0, 0]
    # color_data[4] = [0, 0, 0]
    # color_data[5] = [0, 0, 0]
    length = len(color_data)

    header = bytearray(b"Art-Net\0\0\x50\x00\x0e\x00\00")
    # print(len(header))

    header.append(universe & 0xFF)
    header.append((universe >> 8) & 0xFF)
    header.append((length >> 8) & 0xFF)
    header.append(length & 0xFF)
    data = bytearray()
    for color in color_data:
        for val in color:
            data.append(val)
    return header + data


def send_udp_packet(data):
    destination = "192.168.1.49"
    # destination = "127.0.0.1"
    port = 6454
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
    sock.sendto(data, (destination, port))


while True:
    for a in range(255):
        for universe in range(49):
            color = a & 0x80
            data = prepare_artnet_packet(universe, color)
            send_udp_packet(data)
            # time.sleep(0.1)
