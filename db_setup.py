import sqlite3
import os
from datetime import datetime

DB_PATH = 'database/attendance.db'

def setup_database():
    # 1. Tạo thư mục cần thiết
    folders = ['database', 'dataset/gallery', 'dataset/attendance_images', 'dataset/unknown_faces']
    for f in folders:
        if not os.path.exists(f):
            os.makedirs(f)
            print(f"Đã tạo folder: {f}")

    # 2. Xóa DB cũ để tránh xung đột
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print("Đã xóa Database cũ để khởi tạo lại sạch sẽ.")
        except PermissionError:
            print("Lỗi: Database đang được sử dụng. Hãy tắt App đang chạy trước khi setup!")
            return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    print("Đang khởi tạo Schema mới...")

    # --- TẠO BẢNG (SCHEMA MỚI ĐẦY ĐỦ 5 BẢNG) ---
    
    # 1. Bảng SINH VIÊN (Thêm email)
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    image_path TEXT,
                    created_at TEXT,
                    email TEXT
                )''')

    # 2. Bảng LỚP HỌC
    c.execute('''CREATE TABLE IF NOT EXISTS classes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    created_at TEXT
                )''')

    # 3. Bảng GHI DANH (Thêm stt)
    c.execute('''CREATE TABLE IF NOT EXISTS enrollments (
                    student_id TEXT,
                    class_id INTEGER,
                    joined_at TEXT,
                    stt INTEGER,
                    FOREIGN KEY(student_id) REFERENCES students(id),
                    FOREIGN KEY(class_id) REFERENCES classes(id),
                    PRIMARY KEY (student_id, class_id)
                )''')

    # 4. Bảng ĐIỂM DANH
    c.execute('''CREATE TABLE IF NOT EXISTS attendance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT,
                    class_id INTEGER,
                    checkin_time TEXT,
                    image_evidence TEXT
                )''')

    # 5. Bảng NGƯỜI LẠ (Dùng cho tính năng nhận diện Unknown)
    c.execute('''CREATE TABLE IF NOT EXISTS unknown_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    class_id INTEGER, 
                    session_date TEXT, 
                    image_path TEXT, 
                    created_at TEXT
                )''')

    # --- TẠO DỮ LIỆU MẪU (SEEDING) ---
    print("Đang tạo dữ liệu mẫu...")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Tạo 2 lớp học
    c.execute("INSERT INTO classes (name, created_at) VALUES (?, ?)", ('Lập trình Python', now))
    py_id = c.lastrowid
    c.execute("INSERT INTO classes (name, created_at) VALUES (?, ?)", ('Thị giác máy tính', now))
    cv_id = c.lastrowid

    # Tạo Sinh viên mẫu (Kèm Email)
    students_data = [
        ("SV001", "Nguyễn Văn A", "nva@test.com"),
        ("SV002", "Trần Thị B", "ttb@test.com"),
        ("SV003", "Lê Văn C", "lvc@test.com")
    ]

    for sid, sname, email in students_data:
        c.execute("INSERT INTO students (id, name, image_path, created_at, email) VALUES (?, ?, ?, ?, ?)", 
                  (sid, sname, "dataset/gallery/sample.jpg", now, email))

    # Ghi danh (Kèm STT giả định)
    c.execute("INSERT INTO enrollments (student_id, class_id, joined_at, stt) VALUES (?, ?, ?, ?)", ("SV001", py_id, now, 1))
    c.execute("INSERT INTO enrollments (student_id, class_id, joined_at, stt) VALUES (?, ?, ?, ?)", ("SV001", cv_id, now, 15))
    c.execute("INSERT INTO enrollments (student_id, class_id, joined_at, stt) VALUES (?, ?, ?, ?)", ("SV002", py_id, now, 2))
    c.execute("INSERT INTO enrollments (student_id, class_id, joined_at, stt) VALUES (?, ?, ?, ?)", ("SV003", cv_id, now, 16))

    conn.commit()
    conn.close()
    print(f"HOÀN TẤT! Database mới đã sẵn sàng tại: {DB_PATH}")
    print("Hãy chạy 'streamlit run Dashboard.py' để bắt đầu.")

if __name__ == "__main__":
    setup_database()