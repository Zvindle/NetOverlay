# ============ SERVER ============ #

import socket
import json
import time
import math
import random

UDP_IP_CLIENT = "YOUR-IP-HERE"  # client ip
UDP_PORT_RECV = 6000  # client => server fov [ settings ]
UDP_PORT_SEND = 6001  # server => client [ data ]

sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_recv.bind(("0.0.0.0", UDP_PORT_RECV))
sock_recv.setblocking(False)

sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

current_fov_radius = 150
packet_count = 0

def generate_points_in_circle(radius, max_points=10):
    points = []
    for _ in range(random.randint(3, max_points)):
        r = random.uniform(0, radius)
        angle = random.uniform(0, 2 * math.pi)
        x = int(r * math.cos(angle))
        y = int(r * math.sin(angle))
        points.append([x, y])
    return points

print("[+] server started, waiting for updates...")

while True:
    # recv fov radius from client
    try:
        data, _ = sock_recv.recvfrom(1024)
        msg = json.loads(data.decode())
        # print(f"[+] Received FOV update: [ {msg} ] === [ {msg.get("fov_radius")} ]")
        print(f"[+] received update: [ {msg.get("fov_radius")} ]")
        current_fov_radius = msg.get("fov_radius", current_fov_radius)
    except BlockingIOError:
        pass

    # mock points based on current fov
    mock_points = generate_points_in_circle(current_fov_radius)

    # send back to client
    packet_count += 1
    send_msg = json.dumps({
        "points": mock_points,
        "timestamp": time.time(),
        "packet_count": packet_count
    })
    # print(f"Server sending data to {UDP_IP_CLIENT}:{UDP_PORT_SEND} -> {send_msg}")
    sock_send.sendto(send_msg.encode(), (UDP_IP_CLIENT, UDP_PORT_SEND))

    time.sleep(0.05)
