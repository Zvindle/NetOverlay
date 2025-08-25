# ============ SERVER ============ #

import socket
import json
import time

HOST = "0.0.0.0"
RECEIVE_PORT = 6000
SEND_PORT = 6001


HEAD_BONE_OFFSET_Z = 8.0
MAX_SKELETONS_TO_RENDER = 2 # don't workington

# fuck myl ife
def world_to_screen(view_matrix, world_pos, screen_width, screen_height):
    if not world_pos:
        return None

    x, y, z = world_pos

    clip_w = (view_matrix[12] * x + view_matrix[13] * y + view_matrix[14] * z + view_matrix[15])
    if clip_w < 0.001:
        return None

    ndc_x = (view_matrix[0] * x + view_matrix[1] * y + view_matrix[2] * z + view_matrix[3])
    ndc_y = (view_matrix[4] * x + view_matrix[5] * y + view_matrix[6] * z + view_matrix[7])

    screen_center_x = screen_width / 2
    screen_center_y = screen_height / 2
    screen_x = screen_center_x + (screen_center_x * ndc_x / clip_w)
    screen_y = screen_center_y - (screen_center_y * ndc_y / clip_w)

    return int(screen_x), int(screen_y)


def create_skeleton_lines(bone_data, view_matrix, screen_width, screen_height):
    bone_connections = [
        ("head", "neck"), ("neck", "spine"), ("spine", "pelvis"),
        ("spine", "left_shoulder"), ("left_shoulder", "left_elbow"), ("left_elbow", "left_hand"),
        ("spine", "right_shoulder"), ("right_shoulder", "right_elbow"), ("right_elbow", "right_hand"),
        ("pelvis", "left_hip"), ("left_hip", "left_knee"), ("left_knee", "left_foot"),
        ("pelvis", "right_hip"), ("right_hip", "right_knee"), ("right_knee", "right_foot"),
    ]

    screen_positions = {
        name: world_to_screen(view_matrix, pos_3d, screen_width, screen_height)
        for name, pos_3d in bone_data.items()
        if pos_3d
    }

    skeleton_lines = []
    for start_bone, end_bone in bone_connections:
        pos1 = screen_positions.get(start_bone)
        pos2 = screen_positions.get(end_bone)
        if pos1 and pos2:
            skeleton_lines.extend([pos1[0], pos1[1], pos2[0], pos2[1]])

    return skeleton_lines


def process_incoming_data(game_data):
    view_matrix = game_data.get("view_matrix", [])
    if not view_matrix or len(view_matrix) != 16:
        return {}

    entities = game_data.get("entities", [])
    settings = game_data.get("settings", {})
    screen_width = game_data.get("width", 3440)
    screen_height = game_data.get("height", 1440)
    
    sorted_entities = []
    for entity in entities:
        foot_pos = entity.get("foot_pos")
        if not foot_pos:
            continue
        
        x, y, z = foot_pos
        distance = view_matrix[12] * x + view_matrix[13] * y + view_matrix[14] * z + view_matrix[15]
        entity['distance'] = distance
        sorted_entities.append(entity)

    sorted_entities.sort(key=lambda e: e['distance'])
    
    render_list = []
    skeletons_rendered = 0
    for entity in sorted_entities:
        head_pos_3d = entity.get("head_pos")
        foot_pos_3d = entity.get("foot_pos")
        if not head_pos_3d or not foot_pos_3d:
            continue

        head_pos_with_offset = (head_pos_3d[0], head_pos_3d[1], head_pos_3d[2] + HEAD_BONE_OFFSET_Z)
        head_pos_2d = world_to_screen(view_matrix, head_pos_with_offset, screen_width, screen_height)
        foot_pos_2d = world_to_screen(view_matrix, foot_pos_3d, screen_width, screen_height)

        if not head_pos_2d or not foot_pos_2d:
            continue
        
        box_height = abs(head_pos_2d[1] - foot_pos_2d[1])
        box_width = box_height / 2.0
        
        entity_render_data = {
            "hp": entity.get("hp", 0),
            "is_enemy": entity.get("is_enemy", False),
            "box": {
                "left": int(foot_pos_2d[0] - box_width / 2),
                "top": int(head_pos_2d[1]),
                "right": int(foot_pos_2d[0] + box_width / 2),
                "bottom": int(foot_pos_2d[1])
            },
            "skeleton": []
        }

        if (settings.get("show_skeletons", False) and entity.get("is_enemy")
                and skeletons_rendered < MAX_SKELETONS_TO_RENDER):
            raw_bones = entity.get("bones", {})
            if raw_bones:
                entity_render_data["skeleton"] = create_skeleton_lines(
                    raw_bones, view_matrix, screen_width, screen_height
                )
                skeletons_rendered += 1
        
        render_list.append(entity_render_data)

    return {"entities": render_list}


def main():
    receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receive_socket.bind((HOST, RECEIVE_PORT))
    receive_socket.setblocking(False)

    send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[+] Server started on {HOST}:{RECEIVE_PORT}. Waiting for client...")
    
    packet_count = 0
    client_ip = None

    while True:
        try:
            data, addr = receive_socket.recvfrom(8192)
            
            if client_ip is None:
                client_ip = addr[0]
                print(f"[+] Client connected from {client_ip}")

            game_data = json.loads(data.decode())
            render_payload = process_incoming_data(game_data)
            
            packet_count += 1
            render_payload["timestamp"] = time.time()
            render_payload["packet_count"] = packet_count
            
            if client_ip:
                packet = json.dumps(render_payload).encode()
                send_socket.sendto(packet, (client_ip, SEND_PORT))

        except BlockingIOError:
            pass
        except json.JSONDecodeError:
            print("[!] Received malformed JSON data.")
        except Exception as e:
            print(f"[!] Error {e}")

        time.sleep(0.001)


if __name__ == "__main__":
    main()