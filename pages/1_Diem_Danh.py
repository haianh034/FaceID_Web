import streamlit as st
import cv2
import numpy as np
import tempfile
import sys
import os
import re
import json
import time
from datetime import datetime
import concurrent.futures 
import threading 
from PIL import Image, ImageDraw, ImageFont

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.ai_engine import FaceAttendanceSystem
from navigation import make_sidebar
import core.db_manager as db 
from sklearn.metrics.pairwise import cosine_similarity

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Điểm danh Camera", layout="wide", page_icon="📸")
st.session_state["current_page"] = "Điểm Danh"
make_sidebar()

# --- LOAD CONFIG ---
CONFIG_FILE = 'config.json'
def load_config():
    default = {"camera_index": 0, "frame_skip": 10, "recognition_threshold": 0.5}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f: return json.load(f)
        except: pass
    return default

config = load_config()
DEFAULT_CAM_IDX = config.get('camera_index', 0)
DEFAULT_FRAME_SKIP = config.get('frame_skip', 10)
DEFAULT_THRESHOLD = config.get('recognition_threshold', 0.5)

EVIDENCE_DIR = 'dataset/attendance_images'
if not os.path.exists(EVIDENCE_DIR): os.makedirs(EVIDENCE_DIR)

UNKNOWN_DIR = 'dataset/unknown_faces'
if not os.path.exists(UNKNOWN_DIR): os.makedirs(UNKNOWN_DIR)



# CLASS ĐỌC CAMERA REAL-TIME VỚI BUFFER CHỈ LƯU FRAME MỚI NHẤT (KHÔNG KẸT LAG)
class CameraStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Ép buffer nhỏ nhất có thể
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        # Chạy luồng đọc camera song song dưới nền
        threading.Thread(target=self.update, args=(), daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            grabbed, frame = self.stream.read()
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame

    def read(self):
        with self.lock:
            # Luôn trả về khung hình MỚI NHẤT, bỏ qua các khung hình cũ bị kẹt lại
            if not self.grabbed:
                return False, None
            return True, self.frame.copy()

    def stop(self):
        self.stopped = True
        self.stream.release()

# --- XỬ LÝ CHỌN LỚP ---
if 'active_class_id' not in st.session_state or st.session_state.active_class_id is None:
    st.warning("Bạn chưa chọn lớp từ Dashboard.")
    classes = db.get_all_classes()
    if classes:
        c_opts = {name: id for id, name in classes}
        selected_name = st.selectbox("Chọn lớp để điểm danh ngay:", list(c_opts.keys()))
        if st.button("Xác nhận vào lớp"):
            st.session_state.active_class_id = c_opts[selected_name]
            st.session_state.active_class_name = selected_name
            st.rerun()
    else:
        st.error("Chưa có lớp học nào.")
    st.stop() 

cid = st.session_state.active_class_id
cname = st.session_state.active_class_name

st.title(f"📸 Đang điểm danh: {cname}")

@st.cache_resource(show_spinner=False)
def load_ai(class_id):
    sys = FaceAttendanceSystem()
    sys.load_gallery_from_db(db.DB_PATH, class_id=class_id)
    return sys

with st.spinner(f"Đang tải dữ liệu khuôn mặt lớp {cname}..."):
    sys = load_ai(cid)

st.sidebar.markdown(f"**Lớp:** {cname}")
st.sidebar.info(f"Sĩ số gallery: {len(sys.gallery_info)} SV")
st.sidebar.divider()

st.sidebar.caption("Cấu hình phiên này")
frame_skip = DEFAULT_FRAME_SKIP
threshold = DEFAULT_THRESHOLD

def background_ai_processor(frame, class_id, class_name, thresh, current_unknown_embs):
    results, _ = sys.process_attendance(frame, is_bytes=False, threshold=thresh)
    toast_messages = []
    new_unknown_embs = []
    
    # Lọc ký tự đặc biệt trong tên lớp để tránh lỗi khi tạo thư mục hệ điều hành
    safe_cname = re.sub(r'[\\/*?:"<>|]', "", class_name).strip()
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    for item in results:
        name = item['info']['name']
        sid = item['info']['id']
        emb = item.get('embedding', []) 
        x1, y1, x2, y2 = map(int, item['box'])
        
        # 1. Logic xử lý sinh viên quen
        if name != "Người lạ":
            # --- TẠO THƯ MỤC: dataset/attendance_images/TenLop/YYYY-MM-DD ---
            class_date_dir = os.path.join(EVIDENCE_DIR, safe_cname, date_str)
            os.makedirs(class_date_dir, exist_ok=True) # Tự động tạo nếu chưa có
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(class_date_dir, f"{ts}_{sid}.jpg")
            
            is_new = db.log_attendance_db(sid, class_id, save_path)
            
            if is_new:
                # Xử lý lưu ảnh đường dẫn Tiếng Việt
                is_success, im_buf_arr = cv2.imencode(".jpg", frame)
                if is_success:
                    im_buf_arr.tofile(save_path)
                    
                toast_messages.append((f"Đã điểm danh: {name}", "🎉"))
                
        # 2. Logic xử lý người lạ
        else:
            is_duplicate = False
            
            if len(current_unknown_embs) > 0 and len(emb) > 0:
                sims = cosine_similarity([emb], current_unknown_embs)[0]
                if max(sims) > 0.6: 
                    is_duplicate = True
            
            if not is_duplicate and len(new_unknown_embs) > 0 and len(emb) > 0:
                sims_new = cosine_similarity([emb], new_unknown_embs)[0]
                if max(sims_new) > 0.6:
                    is_duplicate = True
            
            if not is_duplicate:
                if len(emb) > 0:
                    new_unknown_embs.append(emb)
                
                padding = 20
                h_frame, w_frame = frame.shape[:2]
                cx1 = max(0, x1 - padding); cy1 = max(0, y1 - padding)
                cx2 = min(w_frame, x2 + padding); cy2 = min(h_frame, y2 + padding)
                face_crop = frame[cy1:cy2, cx1:cx2]
                
                if face_crop.size > 0:
                    # --- TẠO THƯ MỤC: dataset/unknown_faces/TenLop/YYYY-MM-DD ---
                    unknown_date_dir = os.path.join(UNKNOWN_DIR, safe_cname, date_str)
                    os.makedirs(unknown_date_dir, exist_ok=True)
                    
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(unknown_date_dir, f"unknown_{ts}.jpg")
                    
                    is_success, im_buf_arr = cv2.imencode(".jpg", face_crop)
                    if is_success:
                        im_buf_arr.tofile(save_path)
                        
                    db.log_unknown_face(class_id, date_str, save_path)
                    toast_messages.append(("Đã chụp mặt người lạ mới!", "📸"))
                    
    return results, toast_messages, new_unknown_embs

# HÀM VẼ GIAO DIỆN 
def draw_results(frame, results):
    disp_frame = frame.copy()
    
    # 1. Vẽ các khung vuông (box) bằng OpenCV trước vì nó xử lý rất nhanh
    for item in results:
        name = item['info']['name']
        x1, y1, x2, y2 = map(int, item['box'])
        
        color_bgr = (0, 0, 255) if name == "Người lạ" else (0, 255, 0)
        
        cv2.rectangle(disp_frame, (x1, y1), (x2, y2), color_bgr, 2)
        cv2.rectangle(disp_frame, (x1, max(0, y1 - 30)), (x2, y1), color_bgr, -1)
        
    # 2. Vẽ Text tiếng Việt bằng thư viện Pillow (PIL)
    if len(results) > 0:
        # Chuyển hệ màu từ OpenCV (BGR) sang Pillow (RGB)
        img_pil = Image.fromarray(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        
        # Load font hỗ trợ Unicode (Arial có sẵn trên hầu hết các máy Windows)
        try:
            font = ImageFont.truetype("arial.ttf", 20) 
        except IOError:
            font = ImageFont.load_default()
            
        for item in results:
            name = item['info']['name']
            sim = item['similarity']
            x1, y1, x2, y2 = map(int, item['box'])
            label = f"{name} ({sim:.2f})"
            
            # Ghi chữ lên ảnh
            draw.text((x1 + 5, max(0, y1 - 28)), label, font=font, fill=(255, 255, 255))
            
        # Chuyển ngược ảnh lại hệ màu của OpenCV
        disp_frame = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
        
    return disp_frame


tab_cam, tab_upload = st.tabs(["CAMERA TRỰC TIẾP", "UPLOAD FILE (Ảnh/Video)"])

# === TAB 1: CAMERA TRỰC TIẾP ===
with tab_cam:
    col1, col2 = st.columns([3, 1])
    with col2:
        run_cam = st.toggle("BẬT CAMERA", value=True)
        st.caption("Trạng thái: " + ("Đang chạy..." if run_cam else "Đã dừng"))
        
        if st.button("Reset bộ nhớ Người lạ"):
            st.session_state.unknown_embeddings = []
            st.success("Đã reset!")
    
    with col1:
        st_frame = st.empty()
        
        if run_cam:
            # SỬ DỤNG CLASS CAMERA STREAM MỚI TẠO ĐỂ LẤY REAL-TIME
            cap = CameraStream(DEFAULT_CAM_IDX).start()
            
            cnt = 0
            active_results = [] 
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            ai_future = None
            
            if 'unknown_embeddings' not in st.session_state:
                st.session_state.unknown_embeddings = []
            
            # Thời gian chờ nhỏ giữa các frame để tránh Streamlit quá tải UI (giữ UI mượt)
            time.sleep(0.5) # Chờ camera khởi động
            
            while run_cam:
                ret, frame = cap.read()
                if not ret or frame is None: 
                    continue
                    
                cnt += 1
                
                # Cập nhật kết quả AI lên giao diện
                if ai_future is not None and ai_future.done():
                    res, toasts, new_embs = ai_future.result()
                    active_results = res
                    for msg, icon in toasts:
                        st.toast(msg, icon=icon)
                    if new_embs:
                        st.session_state.unknown_embeddings.extend(new_embs)
                    ai_future = None 
                
                # Gửi frame cho AI xử lý ngầm (dùng frame copy để tránh lỗi luồng)
                if cnt % frame_skip == 0 and ai_future is None:
                    current_embs = st.session_state.unknown_embeddings.copy()
                    ai_future = executor.submit(background_ai_processor, frame.copy(), cid, cname, threshold, current_embs)
                
                # Vẽ hình (Khung hình lấy trực tiếp không độ trễ)
                disp_frame = draw_results(frame, active_results)
                st_frame.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
                
            cap.stop()
            executor.shutdown(wait=False)
        else:
            st_frame.info("💤 Camera đang tạm nghỉ")


# === TAB 2: UPLOAD ===
with tab_upload:
    uploaded_file = st.file_uploader("Chọn video quay lớp học hoặc ảnh tập thể:", type=['mp4', 'avi', 'jpg', 'png'])
    
    if uploaded_file:
        file_type = uploaded_file.name.split('.')[-1].lower()
        
        if file_type in ['mp4', 'avi']:
            tfile = tempfile.NamedTemporaryFile(delete=False) 
            tfile.write(uploaded_file.read())
            
            cap = cv2.VideoCapture(tfile.name)
            fps = cap.get(cv2.CAP_PROP_FPS)
            sleep_time = 1 / fps if fps > 0 else 0.033 
            
            st_vid = st.empty()
            stop_btn = st.button("⏹ Dừng xử lý")
            progress_bar = st.progress(0)
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            current_frame = 0
            
            active_results = []
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            ai_future = None
            if 'unknown_embeddings' not in st.session_state:
                st.session_state.unknown_embeddings = []
            
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret or stop_btn: break
                current_frame += 1
                
                if ai_future is not None and ai_future.done():
                    res, toasts, new_embs = ai_future.result()
                    active_results = res
                    for msg, icon in toasts:
                        st.toast(msg, icon=icon)
                    if new_embs:
                        st.session_state.unknown_embeddings.extend(new_embs)
                    ai_future = None
                
                if current_frame % frame_skip == 0 and ai_future is None:
                    current_embs = st.session_state.unknown_embeddings.copy()
                    ai_future = executor.submit(background_ai_processor, frame.copy(), cid, cname, threshold, current_embs)
                
                disp_frame = draw_results(frame, active_results)
                st_vid.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
                
                time.sleep(sleep_time)
                
                if total_frames > 0:
                    progress_bar.progress(min(current_frame / total_frames, 1.0))
            
            cap.release()
            executor.shutdown(wait=False)
            st.success("Đã xử lý xong video!")

        elif file_type in ['jpg', 'png']:
            file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
            frame = cv2.imdecode(file_bytes, 1)
            
            st.write("Kết quả nhận diện:")
            if 'unknown_embeddings' not in st.session_state:
                st.session_state.unknown_embeddings = []
                
            res, toasts, new_embs = background_ai_processor(frame, cid, cname, threshold, st.session_state.unknown_embeddings)
            for msg, icon in toasts:
                st.toast(msg, icon=icon)
            if new_embs:
                st.session_state.unknown_embeddings.extend(new_embs)
                
            disp_frame = draw_results(frame, res)
            st.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)