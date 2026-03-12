import streamlit as st
import cv2
import json
import sys
import os

# Vì file này nằm trong thư mục con, ta cần thêm sys.path để tìm thấy file navigation.py ở thư mục cha
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation import make_sidebar 

CONFIG_FILE = 'config.json'

def load_config():
    # Giữ lại các giá trị mặc định ngầm định trong file config để hệ thống không lỗi
    default = {"camera_index": 0, "frame_skip": 5, "recognition_threshold": 0.5}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                # Đảm bảo có các key mặc định nếu file json bị thiếu
                for k, v in default.items():
                    if k not in data: data[k] = v
                return data
        except: pass
    return default

def save_config(conf):
    with open(CONFIG_FILE, 'w') as f: json.dump(conf, f)

# Hàm check camera available (quét từ 0 đến 3)
def get_available_cameras():
    arr = []
    for i in range(4):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            arr.append(i)
            cap.release()
    return arr

st.set_page_config(page_title="Cài đặt", layout="centered")
st.session_state["current_page"] = "Cài Đặt"
make_sidebar()
st.title("Cài đặt Hệ thống")

config = load_config()

# --- CAMERA SELECTION ---
st.subheader("Cấu hình Camera")
avail_cams = get_available_cameras()
cam_options = {i: f"Camera {i} {'(Webcam máy)' if i==0 else '(Ngoài)'}" for i in avail_cams}

if not avail_cams:
    st.error("Không tìm thấy Camera nào được kết nối!")
else:
    current_idx = config.get('camera_index', 0)
    if current_idx not in avail_cams: current_idx = avail_cams[0]
    
    selected_idx = st.selectbox(
        "Chọn Camera nguồn:", 
        options=list(cam_options.keys()),
        format_func=lambda x: cam_options[x],
        index=avail_cams.index(current_idx)
    )
    
    if selected_idx != config.get('camera_index'):
        config['camera_index'] = selected_idx
        save_config(config)
        st.success("Đã lưu cấu hình Camera mới!")