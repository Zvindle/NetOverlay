# ============ CLIENT ============ #

import sys
import json
import time
import socket
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QSlider, QLabel, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QFont

UDP_IP_SERVER = "YOUR-IP-HERE"  # server ip
UDP_PORT_SEND = 6000  # client => server fov [ settings ]
UDP_PORT_RECV = 6001  # server => client [ data ]


class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.packet_history = []
        self.last_packet_count = 0
        self.total_packets = 0
        self.packet_loss = 0
        self.packet_rate = 0
        self._last_packet_rate_calc_time = time.time()
        self._packets_in_last_second = 0

        self.fov_radius = 150
        self.mock_points = []
        self.latency_ms = 0
        self.packet_count = 0
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(800, 600)
        self.center = QPoint(self.width() // 2, self.height() // 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # fov circle [ translucent red ]
        painter.setBrush(QColor(255, 0, 0, 50))
        painter.setPen(QColor(255, 0, 0, 150))
        painter.drawEllipse(self.center, self.fov_radius, self.fov_radius)
        # server points [ green dots ]
        painter.setBrush(QColor(0, 255, 0, 200))
        for pt in self.mock_points:
            pos = QPoint(self.center.x() + pt[0], self.center.y() + pt[1])
            painter.drawEllipse(pos, 5, 5)

        # debug text 
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Cascadia Code", 12))
        debug_text = (
            # KNOWN ISSUE WITH LATENCY: DESYNCED WINDOWS CLOCK WILL INCREASE LATENCY SHOWN
            f"latency: {self.latency_ms:.1f} ms\n"
            f"packets: {self.total_packets}\n"
            f"packet loss: {self.packet_loss}\n"
            f"jitter: {self.jitter_ms():.1f} ms\n"
            f"packet rate: {self.packet_rate:.1f}\n"
            f"fov radius: {self.fov_radius}"
        )
        painter.drawText(QRect(10, 10, 300, 150), Qt.AlignmentFlag.AlignLeft, debug_text)

    def resizeEvent(self, event):
        self.center = QPoint(self.width() // 2, self.height() // 2)
        self.update()

    def jitter_ms(self):
        if len(self.packet_history) < 2:
            return 0.0
        diffs = [abs(self.packet_history[i] - self.packet_history[i-1]) for i in range(1, len(self.packet_history))]
        return sum(diffs) / len(diffs)

class ControlWindow(QWidget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.setWindowTitle("Network DMA Debug")
        self.setFixedSize(350, 150)
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.label = QLabel(f"FOV Radius: {self.overlay.fov_radius}")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(300)
        self.slider.setValue(self.overlay.fov_radius)
        self.slider.valueChanged.connect(self.slider_changed)
        self.layout.addWidget(self.slider)

        self.toggle_overlay_btn = QPushButton("Toggle Overlay")
        self.toggle_overlay_btn.clicked.connect(self.toggle_overlay)
        self.layout.addWidget(self.toggle_overlay_btn)

        # clear button
        self.clear_btn = QPushButton("Clear Points")
        self.clear_btn.clicked.connect(self.clear_points)
        self.layout.addWidget(self.clear_btn)

        self.sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_recv.bind(("0.0.0.0", UDP_PORT_RECV))
        self.sock_recv.setblocking(False)

        self.timer_send = QTimer()
        self.timer_send.timeout.connect(self.send_fov_update)
        self.timer_send.start(100) 

        self.timer_recv = QTimer()
        self.timer_recv.timeout.connect(self.receive_data)
        self.timer_recv.start(20)

        self.last_sent_time = 0

    def clear_points(self):
        self.overlay.mock_points = []
        self.overlay.update()

    def slider_changed(self, val):
        self.label.setText(f"FOV Radius: {val}")
        self.overlay.fov_radius = val
        self.overlay.update()

    def toggle_overlay(self):
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show()

    def send_fov_update(self):
        msg = json.dumps({"fov_radius": self.overlay.fov_radius, "timestamp": time.time()})
        # print(f"Client sending FOV to {UDP_IP_SERVER}:{UDP_PORT_SEND} -> {msg}")
        print(f"[+] sending settings -> {UDP_IP_SERVER}:{UDP_PORT_SEND}")
        self.sock_send.sendto(msg.encode(), (UDP_IP_SERVER, UDP_PORT_SEND))
        self.last_sent_time = time.time()

    def receive_data(self):
        try:
            data, _ = self.sock_recv.recvfrom(1024)
            msg = json.loads(data.decode())
            # {"points": [[x,y],...], "timestamp": ..., "packet_count": int}

            self.overlay.mock_points = msg.get("points", [])
            packet_ts = msg.get("timestamp", 0)
            packet_count = msg.get("packet_count", 0)

            # calculation blah blah math shit
            latency = (time.time() - packet_ts) * 1000
            self.overlay.latency_ms = latency

            # Packet counting & loss
            if self.overlay.last_packet_count != 0:
                lost = packet_count - self.overlay.last_packet_count - 1
                if lost > 0:
                    self.overlay.packet_loss += lost
            self.overlay.last_packet_count = packet_count
            self.overlay.total_packets = packet_count

            self.overlay.packet_history.append(latency)
            if len(self.overlay.packet_history) > 50:
                self.overlay.packet_history.pop(0)

            # packet rate math shit blah blah
            now = time.time()
            self.overlay._packets_in_last_second += 1
            if now - self.overlay._last_packet_rate_calc_time >= 1.0:
                self.overlay.packet_rate = self.overlay._packets_in_last_second / (now - self.overlay._last_packet_rate_calc_time)
                self.overlay._last_packet_rate_calc_time = now
                self.overlay._packets_in_last_second = 0

            self.overlay.update()

        except BlockingIOError:
            pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    overlay = OverlayWidget()
    overlay.show()
    ctrl = ControlWindow(overlay)
    ctrl.show()
    sys.exit(app.exec())
