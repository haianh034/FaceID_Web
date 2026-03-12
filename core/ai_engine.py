import cv2
import numpy as np
import os
import sqlite3
from sklearn.metrics.pairwise import cosine_similarity
from insightface.app import FaceAnalysis

class FaceAttendanceSystem:
    def __init__(self, db_path='database/attendance.db'):
        # 1. Cấu hình InsightFace
        current_dir = os.path.dirname(os.path.abspath(__file__)) 
        project_root = os.path.dirname(current_dir)              
        
        print(f"Đang tải model InsightFace (Buffalo_S) tại root: {project_root}...")
        
        # Tải model (Detect + Rec)
        # providers=['CPUExecutionProvider'] được truyền vào kwargs để cấu hình ONNX Runtime
        self.app = FaceAnalysis(name='buffalo_s', root=project_root, providers=['CPUExecutionProvider'])
        
        # det_size: Kích thước đầu vào cho detector (640x640 là chuẩn cho tốc độ/chính xác)
        self.app.prepare(ctx_id=0, det_size=(640, 640))
        
        self.gallery_embeddings = [] 
        self.gallery_info = []
        
        print("Hệ thống FaceID (InsightFace + Slicing) đã sẵn sàng!")

    # PHẦN 1: UTILS & NMS (Xử lý trùng lặp)
    
    def decode_image_from_bytes(self, image_bytes):
        nparr = np.frombuffer(image_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def read_image_robust(self, path):
        try:
            stream = open(path, "rb")
            bytes_data = bytearray(stream.read())
            numpyarray = np.asarray(bytes_data, dtype=np.uint8)
            return cv2.imdecode(numpyarray, cv2.IMREAD_UNCHANGED)
        except:
            return None

    def simple_nms_insightface(self, faces, iou_threshold=0.4):
        """
        Lọc các khuôn mặt trùng nhau sau khi gộp từ các mảnh cắt.
        Input: List các object 'Face' của InsightFace.
        """
        if not faces: return []
        
        # Lấy danh sách bbox và score để đưa vào hàm NMS của OpenCV
        boxes = []
        scores = []
        for f in faces:
            # bbox trong InsightFace là [x1, y1, x2, y2]
            x1, y1, x2, y2 = f.bbox
            boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)]) # format [x, y, w, h]
            scores.append(f.det_score) # det_score là độ tin cậy detection
            
        indices = cv2.dnn.NMSBoxes(boxes, scores, score_threshold=0.3, nms_threshold=iou_threshold)
        
        if len(indices) > 0:
            return [faces[i] for i in indices.flatten()]
        return []

    # PHẦN 2: LOGIC SLICING (CẮT ẢNH) 

    def detect_faces_with_slicing(self, image, overlap_ratio=0.2):
        """
        Chiến thuật: Cắt ảnh làm 4 phần -> Detect trên từng phần -> Gộp lại.
        Giúp phát hiện mặt nhỏ tốt hơn detect cả ảnh to.
        """
        img_h, img_w = image.shape[:2]
        
        crop_h = int(img_h / 2 * (1 + overlap_ratio))
        crop_w = int(img_w / 2 * (1 + overlap_ratio))
        
        # 4 vùng cắt (Top-Left, Top-Right, Bot-Left, Bot-Right)
        crops_coords = [
            (0, 0, crop_w, crop_h),
            (img_w - crop_w, 0, img_w, crop_h),
            (0, img_h - crop_h, crop_w, img_h),
            (img_w - crop_w, img_h - crop_h, img_w, img_h)
        ]
        
        all_faces = []
        edge_margin = 10 # Pixel biên để lọc mặt bị cắt đôi

        for (x_s, y_s, x_e, y_e) in crops_coords:
            crop_img = image[y_s:y_e, x_s:x_e]
            
            # Gọi InsightFace trên mảnh cắt
            # Nó tự động Detect -> Align -> Embed luôn
            faces_in_crop = self.app.get(crop_img)
            
            for face in faces_in_crop:
                bx1, by1, bx2, by2 = face.bbox
                
                # --- LOGIC LỌC BIÊN ---
                # Nếu box chạm vào đường cắt nội bộ -> Bỏ qua
                if x_s > 0 and bx1 < edge_margin: continue
                if y_s > 0 and by1 < edge_margin: continue
                if x_e < img_w and bx2 > (crop_img.shape[1] - edge_margin): continue
                if y_e < img_h and by2 > (crop_img.shape[0] - edge_margin): continue

                # Map tọa độ về ảnh gốc
                face.bbox[0] += x_s
                face.bbox[1] += y_s
                face.bbox[2] += x_s
                face.bbox[3] += y_s
                
                # Map cả landmark (mắt mũi miệng) về ảnh gốc (quan trọng để vẽ đúng)
                if face.kps is not None:
                    face.kps[:, 0] += x_s
                    face.kps[:, 1] += y_s

                all_faces.append(face)
                    
        # Lọc trùng (NMS) lần cuối
        return self.simple_nms_insightface(all_faces)

    # PHẦN 3: LOGIC CHÍNH & EMBEDDING

    def get_single_embedding(self, img):
        # Hàm này dùng khi đăng ký (chỉ cần lấy 1 mặt to nhất)
        faces = self.app.get(img)
        if not faces: return None
        best_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
        return best_face.embedding

    def load_gallery_from_db(self, db_path='database/attendance.db', class_id=None):
        print(f"Đang tải Gallery từ DB (InsightFace)...")
        self.gallery_embeddings = []
        self.gallery_info = []

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # --- Query dùng JOIN bảng enrollments ---
        if class_id:
            # Nếu chọn lớp cụ thể -> Chỉ lấy SV trong lớp đó qua bảng enrollments
            query = """
                SELECT s.id, s.name, s.image_path 
                FROM students s
                JOIN enrollments e ON s.id = e.student_id
                WHERE e.class_id = ?
            """
            cursor.execute(query, (class_id,))
        else:
            # Nếu không chọn lớp -> Lấy tất cả
            query = "SELECT id, name, image_path FROM students"
            cursor.execute(query)
            
        students = cursor.fetchall()
        conn.close()

        for s_id, s_name, img_path in students:
            # Đọc ảnh từ đường dẫn
            img = self.read_image_robust(img_path)
            if img is None: continue
            
            # Tính embedding
            emb = self.get_single_embedding(img)
            if emb is not None:
                self.gallery_embeddings.append(emb)
                self.gallery_info.append({"id": s_id, "name": s_name})
        
        if self.gallery_embeddings:
            self.gallery_embeddings = np.array(self.gallery_embeddings)
        print(f"Đã nạp {len(self.gallery_info)} sinh viên.")

    def process_attendance(self, image_input, is_bytes=False, threshold=0.5):
        if is_bytes:
            img = self.decode_image_from_bytes(image_input)
        else:
            img = self.read_image_robust(image_input)
            if not isinstance(image_input, str): img = image_input 
        if img is None: return [], None

        h_img, w_img = img.shape[:2]

        # QUYẾT ĐỊNH CHIẾN THUẬT:
        # Nếu ảnh to (>1000px) -> Dùng Slicing (Cắt 4) để bắt mặt nhỏ
        # Nếu ảnh nhỏ -> Dùng detect thường cho nhanh
        if max(h_img, w_img) > 1000:
            faces = self.detect_faces_with_slicing(img, overlap_ratio=0.25)
        else:
            faces = self.app.get(img)

        attendance_list = []
        
        for face in faces:
            emb = face.embedding
            match_info = {"id": "Unknown", "name": "Người lạ"}
            max_sim = 0.0
            
            if len(self.gallery_embeddings) > 0:
                sims = cosine_similarity([emb], self.gallery_embeddings)[0]
                best_idx = np.argmax(sims)
                max_sim = float(sims[best_idx])
                
                if max_sim >= threshold:
                    match_info = self.gallery_info[best_idx]
            
            attendance_list.append({
                "box": face.bbox.astype(int), 
                "info": match_info,
                "similarity": max_sim,
                "embedding": emb
            })
        
        return attendance_list, img