from fastapi import FastAPI, UploadFile, File, Form
import uvicorn
import cv2
import numpy as np
import os
from datetime import datetime
from core.ai_engine import FaceAttendanceSystem
import core.db_manager as db

app = FastAPI()
EVIDENCE_DIR = 'dataset/attendance_images'
if not os.path.exists(EVIDENCE_DIR): os.makedirs(EVIDENCE_DIR)

# Khởi tạo hệ thống AI và load dữ liệu từ DB để sẵn sàng phục vụ API ngay khi server chạy 
print("Đang khởi tạo AI Server...")
system = FaceAttendanceSystem() 

# Load dữ liệu khuôn mặt đã học từ DB để sẵn sàng nhận diện ngay
system.load_gallery_from_db(db.DB_PATH)

@app.get("/classes")
def get_classes_api():
    data = db.get_all_classes()
    return [{"id": x[0], "name": x[1]} for x in data]

@app.post("/mobile-attendance")
async def checkin_api(file: UploadFile = File(...), class_id: int = Form(...)):
    try:
        content = await file.read()
        # Hàm process_attendance mới vẫn trả về (results, img) -> Tương thích
        results, img_cv2 = system.process_attendance(content, is_bytes=True)
        
        checked = []
        for item in results:
            name = item['info']['name']
            sid = item['info']['id']
            
            if name != "Người lạ": # Hoặc check item['similarity']
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = os.path.join(EVIDENCE_DIR, f"mobile_{ts}_{sid}.jpg")
                
                is_new = db.log_attendance_db(sid, class_id, save_path)
                
                if is_new:
                    cv2.imwrite(save_path, img_cv2)
                    checked.append(name)
        
        return {"status": "success", "new_checkin": checked}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)