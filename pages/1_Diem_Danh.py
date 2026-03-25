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

# Setup đường dẫn để import navigation
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation import make_sidebar 
import core.db_manager as db 
from core.ai_engine import FaceAttendanceSystem
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
os.makedirs(EVIDENCE_DIR, exist_ok=True)
UNKNOWN_DIR = 'dataset/unknown_faces'
os.makedirs(UNKNOWN_DIR, exist_ok=True)

# CLASS ĐỌC CAMERA REAL-TIME
class CameraStream:
    def __init__(self, src=0):
        self.stream = cv2.VideoCapture(src)
        self.stream.set(cv2.CAP_PROP_BUFFERSIZE, 1) 
        (self.grabbed, self.frame) = self.stream.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
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
            if not self.grabbed: return False, None
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

# --- CACHE THÔNG MINH ---
@st.cache_resource(show_spinner=False)
def load_ai(class_id, update_time):
    sys = FaceAttendanceSystem()
    sys.load_gallery_from_db(db.DB_PATH, class_id=class_id)
    return sys

st.title(f"📸 Đang điểm danh: {cname}")

db_mtime = os.path.getmtime(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0

with st.spinner(f"Đang tải dữ liệu khuôn mặt lớp {cname}..."):
    sys = load_ai(cid, db_mtime)

st.sidebar.markdown(f"**Lớp:** {cname}")
st.sidebar.info(f"Sĩ số gallery: {len(sys.gallery_info)} SV")
st.sidebar.divider()
st.sidebar.caption("Cấu hình phiên này")
frame_skip = DEFAULT_FRAME_SKIP
threshold = DEFAULT_THRESHOLD

# --- HÀM XỬ LÝ AI 2 CHIỀU (Dọn rác & Check chéo) ---
def background_ai_processor(frame, class_id, class_name, thresh, current_unknown_embs, current_recognized_embs, force_save_group=False):
    results, _ = sys.process_attendance(frame, is_bytes=False, threshold=thresh)
    toast_messages = []
    new_unknown_embs = []
    new_recognized_embs = [] # Bộ đệm người quen
    
    disp_frame = None 
    safe_cname = re.sub(r'[\\/*?:"<>|]', "", class_name).strip()
    date_str = datetime.now().strftime("%Y-%m-%d")
    has_new_checkin = False
    
    for item in results:
        name = item['info']['name']
        sid = item['info']['id']
        emb = item.get('embedding', []) 
        x1, y1, x2, y2 = map(int, item['box'])
        
        # ==========================================
        # 1. LOGIC XỬ LÝ SINH VIÊN QUEN
        # ==========================================
        if name != "Người lạ":
            # Lưu embedding vào bộ đệm để check chéo người lạ sau này
            if len(emb) > 0:
                new_recognized_embs.append(emb)
                
            if disp_frame is None:
                disp_frame = draw_results(frame.copy(), results)
                
            class_date_dir = os.path.join(EVIDENCE_DIR, safe_cname, date_str)
            os.makedirs(class_date_dir, exist_ok=True) 
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(class_date_dir, f"{ts}_{sid}.jpg")
            
            is_new = db.log_attendance_db(sid, class_id, save_path)
            
            if is_new:
                has_new_checkin = True
                is_success, im_buf_arr = cv2.imencode(".jpg", disp_frame)
                if is_success: im_buf_arr.tofile(save_path)
                toast_messages.append((f"Đã điểm danh: {name}", "🎉"))
                
            # AI DỌN RÁC QUÁ KHỨ: Quét database xem trước đây có nhận nhầm không
            try:
                df_unknown = db.get_unknown_faces(class_id, date_str)
                if not df_unknown.empty and len(emb) > 0:
                    similar_ids = []
                    for _, row_u in df_unknown.iterrows():
                        u_id, u_path = row_u['id'], row_u['image_path']
                        if not os.path.exists(u_path): continue
                        u_img = sys.read_image_robust(u_path)
                        if u_img is None: continue
                        u_emb = sys.get_single_embedding(u_img)
                        if u_emb is not None:
                            sim = cosine_similarity([emb], [u_emb])[0][0]
                            if sim >= 0.45: similar_ids.append(u_id)
                    
                    for dup_id in similar_ids: db.delete_unknown_face(dup_id)
                    if similar_ids: toast_messages.append((f"Đã dọn {len(similar_ids)} ảnh lạ của {name}", "🧹"))
            except Exception as e: 
                print(f"Lỗi dọn rác: {e}")
                
        # ==========================================
        # 2. LOGIC XỬ LÝ NGƯỜI LẠ (Có Check chéo)
        # ==========================================
        else:
            is_duplicate = False
            
            # CHECK CHÉO VỚI NGƯỜI QUEN VỪA ĐIỂM DANH (Ngăn chặn lưu rác tương lai)
            all_rec_embs = current_recognized_embs + new_recognized_embs
            if len(all_rec_embs) > 0 and len(emb) > 0:
                sims_rec = cosine_similarity([emb], all_rec_embs)[0]
                if max(sims_rec) > 0.55: # Vượt ngưỡng thì thực chất là người quen bị lẹm góc
                    is_duplicate = True
            
            # Check trùng lặp với bộ đệm người lạ hiện tại
            if not is_duplicate and len(current_unknown_embs) > 0 and len(emb) > 0:
                sims = cosine_similarity([emb], current_unknown_embs)[0]
                if max(sims) > 0.6: is_duplicate = True
            
            if not is_duplicate and len(new_unknown_embs) > 0 and len(emb) > 0:
                sims_new = cosine_similarity([emb], new_unknown_embs)[0]
                if max(sims_new) > 0.6: is_duplicate = True
            
            # Nếu hoàn toàn mới lạ thì mới cắt ảnh lưu DB
            if not is_duplicate:
                if len(emb) > 0: new_unknown_embs.append(emb)
                padding = 20
                h_frame, w_frame = frame.shape[:2]
                cx1 = max(0, x1 - padding); cy1 = max(0, y1 - padding)
                cx2 = min(w_frame, x2 + padding); cy2 = min(h_frame, y2 + padding)
                face_crop = frame[cy1:cy2, cx1:cx2]
                
                if face_crop.size > 0:
                    unknown_date_dir = os.path.join(UNKNOWN_DIR, safe_cname, date_str)
                    os.makedirs(unknown_date_dir, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_path = os.path.join(unknown_date_dir, f"unknown_{ts}.jpg")
                    is_success, im_buf_arr = cv2.imencode(".jpg", face_crop)
                    if is_success: im_buf_arr.tofile(save_path)
                    db.log_unknown_face(class_id, date_str, save_path)
                    toast_messages.append(("Đã chụp mặt người lạ mới!", "📸"))

    # 3. Logic lưu ảnh Tập thể
    if disp_frame is None and force_save_group:
        disp_frame = draw_results(frame.copy(), results)
        
    if (has_new_checkin or force_save_group) and disp_frame is not None:
        group_photos_dir = os.path.join(EVIDENCE_DIR, safe_cname, date_str, "group_photos")
        os.makedirs(group_photos_dir, exist_ok=True)
        ts_group = datetime.now().strftime("%H%M%S_%f")[:10] 
        group_save_path = os.path.join(group_photos_dir, f"TapThe_{ts_group}.jpg")
        is_success, im_buf_arr = cv2.imencode(".jpg", disp_frame)
        if is_success: im_buf_arr.tofile(group_save_path)
                    
    return results, toast_messages, new_unknown_embs, new_recognized_embs

# HÀM VẼ GIAO DIỆN (CÓ STT)
def draw_results(frame, results):
    disp_frame = frame.copy()
    for item in results:
        name = item['info']['name']
        x1, y1, x2, y2 = map(int, item['box'])
        color_bgr = (0, 0, 255) if name == "Người lạ" else (0, 255, 0)
        cv2.rectangle(disp_frame, (x1, y1), (x2, y2), color_bgr, 2)
        cv2.rectangle(disp_frame, (x1, max(0, y1 - 30)), (x2, y1), color_bgr, -1)
        
    if len(results) > 0:
        img_pil = Image.fromarray(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        try: font = ImageFont.truetype("arial.ttf", 20) 
        except IOError: font = ImageFont.load_default()
            
        for item in results:
            name, sim = item['info']['name'], item['similarity']
            x1, y1, x2, y2 = map(int, item['box'])
            stt = item['info'].get('stt', '?') 
            label = f"[{stt}] {name} ({sim:.2f})" if name != "Người lạ" else f"{name} ({sim:.2f})"
            draw.text((x1 + 5, max(0, y1 - 28)), label, font=font, fill=(255, 255, 255))
            
        disp_frame = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    return disp_frame

# === GIAO DIỆN ===
tab_cam, tab_snap, tab_upload = st.tabs(["🎥 CAMERA TRỰC TIẾP", "📸 CHỤP ẢNH TỨC THÌ", "📥 TẢI FILE HÀNG LOẠT"])

# === TAB 1: CAMERA TRỰC TIẾP ===
with tab_cam:
    col1, col2 = st.columns([3, 1])
    with col2:
        run_cam = st.toggle("BẬT CAMERA", value=True)
        st.caption("Trạng thái: " + ("Đang chạy..." if run_cam else "Đã dừng"))
        if st.button("Reset bộ nhớ Người lạ"):
            st.session_state.unknown_embeddings = []
            st.session_state.recognized_embeddings = []
            st.success("Đã reset!")
    
    with col1:
        st_frame = st.empty()
        if run_cam:
            cap = CameraStream(DEFAULT_CAM_IDX).start()
            cnt = 0
            active_results = [] 
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            ai_future = None
            
            # Khởi tạo 2 bộ nhớ
            if 'unknown_embeddings' not in st.session_state: st.session_state.unknown_embeddings = []
            if 'recognized_embeddings' not in st.session_state: st.session_state.recognized_embeddings = []
            
            time.sleep(0.5) 
            while run_cam:
                ret, frame = cap.read()
                if not ret or frame is None: continue
                cnt += 1
                if ai_future is not None and ai_future.done():
                    res, toasts, new_u_embs, new_r_embs = ai_future.result()
                    active_results = res
                    for msg, icon in toasts: st.toast(msg, icon=icon)
                    
                    # Cộng dồn bộ nhớ và giới hạn 50 người gần nhất
                    if new_u_embs: st.session_state.unknown_embeddings = (st.session_state.unknown_embeddings + new_u_embs)[-50:]
                    if new_r_embs: st.session_state.recognized_embeddings = (st.session_state.recognized_embeddings + new_r_embs)[-50:]
                    ai_future = None 
                
                if cnt % frame_skip == 0 and ai_future is None:
                    c_u_embs = st.session_state.unknown_embeddings.copy()
                    c_r_embs = st.session_state.recognized_embeddings.copy()
                    ai_future = executor.submit(background_ai_processor, frame.copy(), cid, cname, threshold, c_u_embs, c_r_embs, False)
                
                disp_frame = draw_results(frame, active_results)
                st_frame.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
                
            cap.stop()
            executor.shutdown(wait=False)
        else:
            st_frame.info("💤 Camera đang tạm nghỉ")

# === TAB 2: CHỤP ẢNH TỨC THÌ ===
with tab_snap:
    st.markdown("### Chụp ảnh nhanh bằng Webcam")
    st.info("💡 Điểm danh 1 bức ảnh tĩnh: AI sẽ điểm danh và lưu 1 ảnh tập thể có vẽ khung làm bằng chứng.")
    snap_buffer = st.camera_input("Bấm nút 'Take Photo' bên dưới...")
    
    if snap_buffer:
        with st.spinner("AI đang xử lý ảnh vừa chụp..."):
            image_pil = Image.open(snap_buffer)
            frame = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)
            
            if 'snap_u_embs' not in st.session_state: st.session_state.snap_u_embs = []
            if 'snap_r_embs' not in st.session_state: st.session_state.snap_r_embs = []
            
            res, toasts, new_u_embs, new_r_embs = background_ai_processor(
                frame, cid, cname, threshold, 
                st.session_state.snap_u_embs, 
                st.session_state.snap_r_embs,
                force_save_group=True 
            )
            for msg, icon in toasts: st.toast(msg, icon=icon)
            
            if new_u_embs: st.session_state.snap_u_embs = (st.session_state.snap_u_embs + new_u_embs)[-50:]
            if new_r_embs: st.session_state.snap_r_embs = (st.session_state.snap_r_embs + new_r_embs)[-50:]
            
            disp_frame = draw_results(frame, res)
            st.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
            st.success("✅ Đã lưu minh chứng tập thể thành công!")

# === TAB 3: UPLOAD ===
with tab_upload:
    uploaded_files = st.file_uploader("Chọn Video hoặc nhiều Ảnh tập thể:", type=['mp4', 'avi', 'jpg', 'png'], accept_multiple_files=True)
    
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_type = uploaded_file.name.split('.')[-1].lower()
            
            if file_type in ['mp4', 'avi']:
                st.markdown(f"### 🎬 Đang xử lý Video: `{uploaded_file.name}`")
                tfile = tempfile.NamedTemporaryFile(delete=False) 
                tfile.write(uploaded_file.read())
                cap = cv2.VideoCapture(tfile.name)
                fps = cap.get(cv2.CAP_PROP_FPS)
                sleep_time = 1 / fps if fps > 0 else 0.033 
                
                st_vid = st.empty()
                stop_btn = st.button("⏹ Dừng xử lý", key=f"stop_{uploaded_file.name}")
                progress_bar = st.progress(0)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                current_frame = 0
                
                active_results = []
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                ai_future = None
                
                if 'bulk_u_embs' not in st.session_state: st.session_state.bulk_u_embs = []
                if 'bulk_r_embs' not in st.session_state: st.session_state.bulk_r_embs = []
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret or stop_btn: break
                    current_frame += 1
                    
                    if ai_future is not None and ai_future.done():
                        res, toasts, new_u_embs, new_r_embs = ai_future.result()
                        active_results = res
                        for msg, icon in toasts: st.toast(msg, icon=icon)
                        
                        if new_u_embs: st.session_state.bulk_u_embs = (st.session_state.bulk_u_embs + new_u_embs)[-50:]
                        if new_r_embs: st.session_state.bulk_r_embs = (st.session_state.bulk_r_embs + new_r_embs)[-50:]
                        ai_future = None
                    
                    if current_frame % frame_skip == 0 and ai_future is None:
                        c_u_embs = st.session_state.bulk_u_embs.copy()
                        c_r_embs = st.session_state.bulk_r_embs.copy()
                        ai_future = executor.submit(background_ai_processor, frame.copy(), cid, cname, threshold, c_u_embs, c_r_embs, False)
                    
                    disp_frame = draw_results(frame, active_results)
                    st_vid.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
                    time.sleep(sleep_time)
                    if total_frames > 0: progress_bar.progress(min(current_frame / total_frames, 1.0))
                
                cap.release()
                executor.shutdown(wait=False)
                st.success(f"Đã xử lý xong video: {uploaded_file.name}!")

            elif file_type in ['jpg', 'png']:
                st.markdown(f"### 📸 Kết quả Ảnh: `{uploaded_file.name}`")
                file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
                frame = cv2.imdecode(file_bytes, 1)
                
                if 'bulk_u_embs' not in st.session_state: st.session_state.bulk_u_embs = []
                if 'bulk_r_embs' not in st.session_state: st.session_state.bulk_r_embs = []
                    
                res, toasts, new_u_embs, new_r_embs = background_ai_processor(
                    frame, cid, cname, threshold, 
                    st.session_state.bulk_u_embs,
                    st.session_state.bulk_r_embs,
                    force_save_group=True
                )
                
                for msg, icon in toasts: st.toast(msg, icon=icon)
                if new_u_embs: st.session_state.bulk_u_embs = (st.session_state.bulk_u_embs + new_u_embs)[-50:]
                if new_r_embs: st.session_state.bulk_r_embs = (st.session_state.bulk_r_embs + new_r_embs)[-50:]
                    
                disp_frame = draw_results(frame, res)
                st.image(cv2.cvtColor(disp_frame, cv2.COLOR_BGR2RGB), use_container_width=True)
                st.caption(f"✅ Đã lưu ảnh minh chứng tập thể cho: {uploaded_file.name}")
                
        if len(uploaded_files) > 1: st.balloons()