# ============ CLIENT ============ #

import sys
import json
import time
import socket
import threading
import struct
import ctypes
import math
import requests

import pymem
import pymem.process

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QSlider, QLabel, QCheckBox, QGroupBox
)
from PyQt6.QtCore import Qt, QPoint, QRect, QObject, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

# PLEASE change this to your server's IP
# PLEASE change this to your server's IP
# PLEASE change this to your server's IP
UDP_SERVER_IP = "YOUR_SERVER_IP_HERE"
UDP_SEND_PORT = 6000
UDP_RECEIVE_PORT = 6001

process_memory = None
client_dll_address = None
game_offsets = {}

user32 = ctypes.windll.user32
SCREEN_WIDTH = user32.GetSystemMetrics(0)
SCREEN_HEIGHT = user32.GetSystemMetrics(1)

MAX_PLAYERS = 64
BONE_SIZE_IN_BYTES = 0x20

BONE_IDS = {
    "head": 6, "neck": 5, "spine": 4, "pelvis": 0,
    "left_shoulder": 8, "left_elbow": 9, "left_hand": 10,
    "right_shoulder": 13, "right_elbow": 14, "right_hand": 15,
    "left_hip": 22, "left_knee": 23, "left_foot": 24,
    "right_hip": 26, "right_knee": 27, "right_foot": 28
}


def initialize_memory_reader():
    global process_memory, client_dll_address, game_offsets
    try:
        print("[?] Searching for cs2.exe...")
        process_memory = pymem.Pymem("cs2.exe")
        print(f"[+] Process found! {process_memory.process_id}")

        client_dll_address = pymem.process.module_from_name(
            process_memory.process_handle, "client.dll"
        ).lpBaseOfDll
        print(f"[+] client.dll found at: {hex(client_dll_address)}")
        print(f"[+] Client resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")

        print("[?] Fetching offsets...")
        try:
            offsets_url = "https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/offsets.json"
            response = requests.get(offsets_url)
            response.raise_for_status()
            offset_data = response.json()['client.dll']

            client_dll_url = "https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/client_dll.json"
            response = requests.get(client_dll_url)
            response.raise_for_status()
            client_data = response.json()['client.dll']['classes']

            game_offsets = {
                'dwEntityList': offset_data['dwEntityList'],
                'dwLocalPlayerPawn': offset_data['dwLocalPlayerPawn'],
                'dwViewMatrix': offset_data['dwViewMatrix'],
                'm_iTeamNum': client_data['C_BaseEntity']['fields']['m_iTeamNum'],
                'm_lifeState': client_data['C_BaseEntity']['fields']['m_lifeState'],
                'm_hPlayerPawn': client_data['CCSPlayerController']['fields']['m_hPlayerPawn'],
                'm_iHealth': client_data['C_BaseEntity']['fields']['m_iHealth'],
                'm_pGameSceneNode': client_data['C_BaseEntity']['fields']['m_pGameSceneNode'],
                'm_modelState': client_data['CSkeletonInstance']['fields']['m_modelState']
            }
            print("[+] Offsets loaded successfully!")
            return True
        except (requests.RequestException, KeyError) as e:
            print(f"[!] Could not fetch or parse offsets {e}")
            return False
    except (pymem.exception.ProcessNotFound, TypeError):
        return False


class DataWorker(QObject):
    data_updated = pyqtSignal(dict, dict)
    status_changed = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self.is_running = True
        self.settings = {}
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receive_socket.bind(("0.0.0.0", UDP_RECEIVE_PORT))
        self.receive_socket.setblocking(False)

    def update_settings(self, new_settings):
        self.settings = new_settings

    def _clean_json_data(self, obj):
        if isinstance(obj, float):
            return None if math.isnan(obj) or math.isinf(obj) else obj
        if isinstance(obj, dict):
            return {k: self._clean_json_data(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._clean_json_data(i) for i in obj]
        return obj

    def _get_bone_position(self, bone_matrix_ptr, bone_id):
        base_address = bone_matrix_ptr + bone_id * BONE_SIZE_IN_BYTES
        try:
            x = process_memory.read_float(base_address)
            y = process_memory.read_float(base_address + 0x4)
            z = process_memory.read_float(base_address + 0x8)
            return (x, y, z)
        except pymem.exception.MemoryReadError:
            return None

    def read_game_data(self):
        game_data = {
            "view_matrix": [],
            "entities": [],
            "settings": self.settings,
            "width": SCREEN_WIDTH,
            "height": SCREEN_HEIGHT
        }

        if not process_memory or not client_dll_address:
            return game_data

        try:
            view_matrix_bytes = process_memory.read_bytes(
                client_dll_address + game_offsets['dwViewMatrix'], 64
            )
            game_data["view_matrix"] = list(struct.unpack('f' * 16, view_matrix_bytes))

            local_player_pawn = process_memory.read_longlong(
                client_dll_address + game_offsets['dwLocalPlayerPawn']
            )
            if not local_player_pawn:
                return game_data
            local_team = process_memory.read_int(local_player_pawn + game_offsets['m_iTeamNum'])

            entity_list_ptr = process_memory.read_longlong(
                client_dll_address + game_offsets['dwEntityList']
            )

            for i in range(1, MAX_PLAYERS + 1):
                list_entry = process_memory.read_longlong(entity_list_ptr + (8 * (i & 0x7FF) >> 9) + 16)
                if not list_entry: continue

                entity_controller = process_memory.read_longlong(list_entry + 120 * (i & 0x1FF))
                if not entity_controller: continue

                controller_pawn_handle = process_memory.read_longlong(entity_controller + game_offsets['m_hPlayerPawn'])
                if not controller_pawn_handle: continue

                list_entry2 = process_memory.read_longlong(entity_list_ptr + (0x8 * ((controller_pawn_handle & 0x7FFF) >> 9) + 16))
                if not list_entry2: continue

                entity_pawn = process_memory.read_longlong(list_entry2 + 120 * (controller_pawn_handle & 0x1FF))
                if not entity_pawn or entity_pawn == local_player_pawn: continue

                if process_memory.read_int(entity_pawn + game_offsets['m_lifeState']) != 256:
                    continue

                entity_team = process_memory.read_int(entity_pawn + game_offsets['m_iTeamNum'])

                # cancer
                game_scene_node = process_memory.read_longlong(entity_pawn + game_offsets['m_pGameSceneNode'])
                bone_matrix_ptr = process_memory.read_longlong(game_scene_node + game_offsets['m_modelState'] + 0x80)

                entity_data = {
                    "hp": process_memory.read_int(entity_pawn + game_offsets['m_iHealth']),
                    "is_enemy": entity_team != local_team,
                    "bones": {},
                    "head_pos": self._get_bone_position(bone_matrix_ptr, BONE_IDS["head"]),
                    "foot_pos": self._get_bone_position(bone_matrix_ptr, BONE_IDS["left_foot"])
                }

                if self.settings.get("show_skeletons"):
                    for name, bone_id in BONE_IDS.items():
                        entity_data["bones"][name] = self._get_bone_position(bone_matrix_ptr, bone_id)

                game_data["entities"].append(entity_data)

            return game_data
        except pymem.exception.MemoryReadError:
            return game_data

    def run(self):
        last_packet_received_time = time.time()
        is_connected = False

        last_packet_id = 0
        total_packets_received = 0
        packets_lost = 0
        packet_rate = 0.0
        
        rate_calc_time = time.time()
        packets_in_second = 0

        while self.is_running:
            try:
                raw_game_data = self.read_game_data()

                sanitized_data = self._clean_json_data(raw_game_data)
                if sanitized_data and UDP_SERVER_IP != "YOUR_SERVER_IP_HERE":
                    packet = json.dumps(sanitized_data).encode()
                    self.send_socket.sendto(packet, (UDP_SERVER_IP, UDP_SEND_PORT))

                if is_connected and (time.time() - last_packet_received_time > 2.0):
                    is_connected = False
                    self.status_changed.emit("Disconnected", "orange")
                    last_packet_id = 0; total_packets_received = 0; packets_lost = 0; packet_rate = 0.0

                try:
                    data, _ = self.receive_socket.recvfrom(8192)
                    if not data: continue

                    last_packet_received_time = time.time()
                    if not is_connected:
                        is_connected = True
                        self.status_changed.emit("Connected", "lightgreen")

                    message = json.loads(data.decode())
                    
                    if not message.get("entities"):
                        self.status_changed.emit("Connected (No data)", "lightblue")
                    else:
                        self.status_changed.emit("Connected", "lightgreen")
                        
                    latency = (time.time() - message.get("timestamp", 0)) * 1000
                    packet_id = message.get("packet_count", 0)

                    if last_packet_id != 0:
                        lost_count = packet_id - last_packet_id - 1
                        if lost_count > 0:
                            packets_lost += lost_count
                    last_packet_id = packet_id
                    total_packets_received = packet_id
                    
                    packets_in_second += 1
                    now = time.time()
                    if now - rate_calc_time >= 1.0:
                        packet_rate = packets_in_second / (now - rate_calc_time)
                        rate_calc_time = now
                        packets_in_second = 0
                        
                    debug_info = {
                        "latency": latency,
                        "total_packets": total_packets_received,
                        "packet_loss": packets_lost,
                        "packet_rate": packet_rate,
                        "fov_radius": self.settings.get("fov_radius", 150)
                    }

                    self.data_updated.emit(message, debug_info)

                except BlockingIOError:
                    pass
            except Exception as e:
                print(f"[!] {e}")
                self.status_changed.emit("Thread error", "red")
                time.sleep(3)
            
            time.sleep(0.001)


class OverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.render_data = {"entities": []}
        self.debug_info = {}
        self.settings = {}

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.center_point = QPoint(self.width() // 2, self.height() // 2)

    def update_settings(self, settings):
        self.settings = settings
        self.update()

    def update_data(self, data, debug_info):
        self.render_data = data
        self.debug_info = debug_info
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.settings.get("show_fov_circle", True):
            radius = self.debug_info.get("fov_radius", 150)
            painter.setBrush(QColor(255, 0, 0, 20))
            painter.setPen(QPen(QColor(255, 0, 0, 100), 1.5))
            painter.drawEllipse(self.center_point, radius, radius)

        for entity in self.render_data.get("entities", []):
            color = QColor(255, 0, 0, 255) if entity["is_enemy"] else QColor(0, 255, 0, 255)
            
            box = entity.get("box")
            if box and self.settings.get("show_boxes", True):
                painter.setPen(QPen(color, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                box_rect = QRect(box["left"], box["top"], box["right"] - box["left"], box["bottom"] - box["top"])
                painter.drawRect(box_rect)
            
            # This is broken due to packet size limits
            skeleton = entity.get("skeleton")
            if skeleton and self.settings.get("show_skeletons", True):
                 painter.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
                 # ???????????????
                 for i in range(0, len(skeleton), 4):
                     point1 = QPoint(skeleton[i], skeleton[i+1])
                     point2 = QPoint(skeleton[i+2], skeleton[i+3])
                     painter.drawLine(point1, point2)

            if box and self.settings.get("show_health_bars", True):
                health = entity.get("hp", 100)
                health_percentage = max(0, min(100, health)) / 100.0

                bar_height = box["bottom"] - box["top"]
                bar_width = 4
                bar_x_position = box["left"] - bar_width - 3

                painter.setBrush(QColor(0, 0, 0, 150))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(bar_x_position, box["top"], bar_width, bar_height)

                if health_percentage < 0.3:
                    hp_color = QColor(255, 0, 0)
                elif health_percentage < 0.7:
                    hp_color = QColor(255, 255, 0) # yleow
                else:
                    hp_color = QColor(0, 255, 0) 
                
                current_hp_height = int(bar_height * health_percentage)
                painter.setBrush(hp_color)
                painter.drawRect(
                    bar_x_position, box["bottom"] - current_hp_height,
                    bar_width, current_hp_height
                )
        if self.settings.get("show_debug_info", True):
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Cascadia Code", 10))
            debug_text = (
                f"Latency: {self.debug_info.get('latency', 0):.1f} ms\n"
                f"Packets: {self.debug_info.get('total_packets', 0)}\n"
                f"Loss: {self.debug_info.get('packet_loss', 0)}\n"
                f"Rate: {self.debug_info.get('packet_rate', 0):.1f}/s"
            )
            painter.drawText(QRect(10, 10, 300, 150), Qt.AlignmentFlag.AlignLeft, debug_text)


class ControlWindow(QWidget):
    def __init__(self, overlay_widget, data_worker):
        super().__init__()
        self.overlay = overlay_widget
        self.worker = data_worker
        self.setWindowTitle("Control Panel")
        self.setFixedSize(350, 320)
        self.layout = QVBoxLayout(self)

        self.status_label = QLabel("Status: Connecting...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.layout.addWidget(self.status_label)

        features_group = QGroupBox("Features")
        features_layout = QVBoxLayout()
        self.show_boxes_cb = QCheckBox("Show Boxes")
        self.show_boxes_cb.setChecked(True)
        self.show_skeletons_cb = QCheckBox("This shit is BROCKEN!!!💔")
        self.show_skeletons_cb.setChecked(False)
        self.show_health_bars_cb = QCheckBox("Show Health Bars")
        self.show_health_bars_cb.setChecked(True)
        
        features_layout.addWidget(self.show_boxes_cb)
        features_layout.addWidget(self.show_skeletons_cb)
        features_layout.addWidget(self.show_health_bars_cb)
        features_group.setLayout(features_layout)
        self.layout.addWidget(features_group)

        debug_group = QGroupBox("Debug")
        debug_layout = QVBoxLayout()
        self.fov_label = QLabel(f"Aim FOV Radius: {150}")
        self.fov_slider = QSlider(Qt.Orientation.Horizontal)
        self.fov_slider.setMinimum(10)
        self.fov_slider.setMaximum(500)
        self.fov_slider.setValue(150)
        self.show_fov_circle_cb = QCheckBox("Show FOV Circle")
        self.show_fov_circle_cb.setChecked(False)
        self.show_debug_info_cb = QCheckBox("Show Debug Info")
        self.show_debug_info_cb.setChecked(False)

        debug_layout.addWidget(self.fov_label)
        debug_layout.addWidget(self.fov_slider)
        debug_layout.addWidget(self.show_fov_circle_cb)
        debug_layout.addWidget(self.show_debug_info_cb)
        debug_group.setLayout(debug_layout)
        self.layout.addWidget(debug_group)
        self.show_boxes_cb.stateChanged.connect(self.update_all_settings)
        self.show_skeletons_cb.stateChanged.connect(self.update_all_settings)
        self.show_health_bars_cb.stateChanged.connect(self.update_all_settings)
        self.show_fov_circle_cb.stateChanged.connect(self.update_all_settings)
        self.show_debug_info_cb.stateChanged.connect(self.update_all_settings)
        self.fov_slider.valueChanged.connect(self.update_all_settings)
        self.fov_slider.valueChanged.connect(lambda value: self.fov_label.setText(f"Aim FOV Radius: {value}"))
        
        self.update_all_settings()

    def update_all_settings(self):
        settings = {
            "show_boxes": self.show_boxes_cb.isChecked(),
            "show_skeletons": self.show_skeletons_cb.isChecked(),
            "show_health_bars": self.show_health_bars_cb.isChecked(),
            "show_fov_circle": self.show_fov_circle_cb.isChecked(),
            "show_debug_info": self.show_debug_info_cb.isChecked(),
            "fov_radius": self.fov_slider.value()
        }
        self.worker.update_settings(settings)
        self.overlay.update_settings(settings)

    def set_status(self, text, color):
        self.status_label.setText(f"Status: {text}")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")


def main():
    if UDP_SERVER_IP == "YOUR_SERVER_IP_HERE":
        print("[!] UDP_SERVER_IP variable.")
        sys.exit(1)

    if not initialize_memory_reader():
        print("[!] Could not find the CS2 process or fetch offsets.")
        sys.exit(1)

    app = QApplication(sys.argv)
    data_worker = DataWorker()
    worker_thread = threading.Thread(target=data_worker.run, daemon=True)
    overlay_window = OverlayWidget()
    control_window = ControlWindow(overlay_window, data_worker)
    data_worker.data_updated.connect(overlay_window.update_data)
    data_worker.status_changed.connect(control_window.set_status)
    worker_thread.start()
    overlay_window.show()
    control_window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()