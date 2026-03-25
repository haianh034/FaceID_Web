import sqlite3
import pandas as pd
import os
import shutil
import re
from datetime import datetime

DB_PATH = 'database/attendance.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Bảng Sinh viên (Đã thêm email TEXT)
    c.execute('''CREATE TABLE IF NOT EXISTS students
                 (id TEXT PRIMARY KEY, name TEXT, image_path TEXT, created_at TEXT, email TEXT)''')

    # 2. Bảng Lớp học
    c.execute('''CREATE TABLE IF NOT EXISTS classes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, created_at TEXT)''')

    # 3. Bảng Ghi danh (Đã thêm stt INTEGER)
    c.execute('''CREATE TABLE IF NOT EXISTS enrollments
                 (student_id TEXT, class_id INTEGER, joined_at TEXT, stt INTEGER,
                  FOREIGN KEY(student_id) REFERENCES students(id),
                  FOREIGN KEY(class_id) REFERENCES classes(id),
                  PRIMARY KEY (student_id, class_id))''')

    # 4. Bảng Logs điểm danh
    c.execute('''CREATE TABLE IF NOT EXISTS attendance_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  student_id TEXT, class_id INTEGER, 
                  checkin_time TEXT, image_evidence TEXT)''')
                  
    # 5. Bảng Logs Người Lạ (Giữ nguyên)
    c.execute('''CREATE TABLE IF NOT EXISTS unknown_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  class_id INTEGER, 
                  session_date TEXT, 
                  image_path TEXT, 
                  created_at TEXT)''')

    # --- NÂNG CẤP DATABASE CŨ (KHÔNG LÀM MẤT DỮ LIỆU) ---
    try:
        c.execute("ALTER TABLE students ADD COLUMN email TEXT")
    except:
        pass # Bỏ qua nếu cột email đã tồn tại
        
    try:
        c.execute("ALTER TABLE enrollments ADD COLUMN stt INTEGER")
    except:
        pass # Bỏ qua nếu cột stt đã tồn tại

    conn.commit()
    conn.close()

# --- KHỐI QUẢN LÝ LỚP HỌC (CRUD CLASS) ---
def create_class(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO classes (name, created_at) VALUES (?, ?)", (name, now))
        conn.commit()
        return True, "Tạo lớp thành công!"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_all_classes():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name FROM classes")
    data = c.fetchall()
    conn.close()
    return data # List of (id, name)

def delete_class(class_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 1. TÌM VÀ XÓA THƯ MỤC VẬT LÝ CỦA LỚP
        c.execute("SELECT name FROM classes WHERE id = ?", (class_id,))
        row = c.fetchone()
        
        if row:
            class_name = row[0]
            # Lọc ký tự giống như lúc tạo thư mục để tìm cho chuẩn xác
            safe_cname = re.sub(r'[\\/*?:"<>|]', "", class_name).strip()
            
            # Đường dẫn 2 thư mục cần dọn dẹp
            attendance_dir = os.path.join('dataset/attendance_images', safe_cname)
            unknown_dir = os.path.join('dataset/unknown_faces', safe_cname)
            
            # Dùng shutil.rmtree để xóa sổ toàn bộ thư mục và các file con bên trong
            if os.path.exists(attendance_dir):
                shutil.rmtree(attendance_dir)
            if os.path.exists(unknown_dir):
                shutil.rmtree(unknown_dir)

        # 2. XÓA DỮ LIỆU SỔ SÁCH TRONG DATABASE
        c.execute("DELETE FROM attendance_logs WHERE class_id = ?", (class_id,))
        # Lưu ý: Khi xóa lớp, ta cũng xóa luôn các log người lạ liên quan đến lớp đó để tránh dữ liệu rác
        c.execute("DELETE FROM unknown_logs WHERE class_id = ?", (class_id,)) 
        c.execute("DELETE FROM enrollments WHERE class_id = ?", (class_id,))
        c.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        
        conn.commit()
        return True, "Đã xóa lớp và dọn dẹp sạch sẽ ổ cứng!"
    except Exception as e:
        print(f"Lỗi khi xóa lớp: {e}")
        return False, str(e)
    finally:
        conn.close()

# --- KHỐI QUẢN LÝ SINH VIÊN & GHI DANH ---
def add_student_to_class(student_id, student_name, image_path, class_id):
    """
    Hàm thông minh: 
    - Nếu SV chưa có trong hệ thống -> Tạo mới SV -> Thêm vào lớp.
    - Nếu SV đã có (check theo ID) -> Chỉ thêm vào lớp mới (không tạo lại ảnh).
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Upsert Student (Nếu tồn tại thì update tên/ảnh, chưa thì insert)
        c.execute("SELECT id FROM students WHERE id = ?", (student_id,))
        exists = c.fetchone()
        
        if not exists:
            c.execute("INSERT INTO students (id, name, image_path, created_at) VALUES (?, ?, ?, ?)",
                      (student_id, student_name, image_path, now))
        else:
            # Nếu đã tồn tại -> Cập nhật tên và ảnh (nếu có ảnh mới)
            c.execute("UPDATE students SET name=?, image_path=? WHERE id=?", (student_name, image_path, student_id))
            pass

        # 2. Thêm vào bảng Enrollments (Nếu chưa có trong lớp này)
        c.execute("SELECT * FROM enrollments WHERE student_id=? AND class_id=?", (student_id, class_id))
        is_enrolled = c.fetchone()
        
        if not is_enrolled:
            c.execute("INSERT INTO enrollments (student_id, class_id, joined_at) VALUES (?, ?, ?)",
                      (student_id, class_id, now))
            msg = "Đã thêm sinh viên vào lớp!"
        else:
            msg = "Sinh viên đã có trong lớp này rồi."
            
        conn.commit()
        return True, msg
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def remove_student_from_class(student_id, class_id):
    # Chỉ xóa khỏi lớp (enrollments), KHÔNG xóa khỏi database gốc (students)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM enrollments WHERE student_id=? AND class_id=?", (student_id, class_id))
    conn.commit()
    conn.close()
    
def get_students_in_class(class_id):
    """Lấy danh sách sinh viên đầy đủ STT và Email để hiển thị lên bảng"""
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT e.stt as "STT", s.id as "Mã SV", s.name as "Họ Tên", s.email as "Email", s.image_path as "Đường dẫn Ảnh", e.joined_at as "Ngày thêm"
        FROM students s
        JOIN enrollments e ON s.id = e.student_id
        WHERE e.class_id = ?
        ORDER BY e.stt ASC, s.id ASC
    """
    df = pd.read_sql_query(query, conn, params=(class_id,))
    conn.close()
    return df

# --- KHỐI THỐNG KÊ  ---
def get_class_stats_detailed(class_id):
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Lấy danh sách SV trong lớp
    query_sv = """
        SELECT s.id, s.name 
        FROM students s
        JOIN enrollments e ON s.id = e.student_id
        WHERE e.class_id = ?
    """
    df_sv = pd.read_sql_query(query_sv, conn, params=(class_id,))
    
    if df_sv.empty:
        conn.close()
        return df_sv # Trả về empty df
    
    # 2. Lấy dữ liệu điểm danh của lớp này
    query_logs = "SELECT student_id, checkin_time FROM attendance_logs WHERE class_id = ?"
    df_logs = pd.read_sql_query(query_logs, conn, params=(class_id,))
    conn.close()
    
    # 3. Tính toán thống kê
    # Chuyển checkin_time về dạng Date (Ngày) để đếm số buổi
    if not df_logs.empty:
        df_logs['date'] = pd.to_datetime(df_logs['checkin_time']).dt.date
        
        # Đếm tổng số buổi học đã diễn ra (số ngày duy nhất có checkin của bất kỳ ai)
        total_sessions = df_logs['date'].nunique()
        
        # Đếm số lần có mặt của từng SV
        attendance_counts = df_logs.groupby('student_id')['date'].nunique()
        
        # Merge vào danh sách SV
        df_sv['present_count'] = df_sv['id'].map(attendance_counts).fillna(0).astype(int)
        df_sv['total_sessions'] = total_sessions
        df_sv['absent_count'] = total_sessions - df_sv['present_count']
        df_sv['attendance_rate'] = (df_sv['present_count'] / total_sessions * 100).round(1)
    else:
        df_sv['present_count'] = 0
        df_sv['total_sessions'] = 0
        df_sv['absent_count'] = 0
        df_sv['attendance_rate'] = 0.0
        
    return df_sv

def get_attendance_history_by_date(class_id):
    """Lấy lịch sử: Ngày nào, Giờ nào, Ai điểm danh"""
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT l.checkin_time, s.name, s.id, l.image_evidence
        FROM attendance_logs l
        JOIN students s ON l.student_id = s.id
        WHERE l.class_id = ?
        ORDER BY l.checkin_time DESC
    """
    df = pd.read_sql_query(query, conn, params=(class_id,))
    conn.close()
    return df

def get_low_attendance_students(threshold_percent=50):
    """
    Lấy danh sách sinh viên có tỉ lệ đi học < threshold_percent (mặc định 50%)
    Logic: (Số ngày đi học / Tổng số buổi của lớp) * 100 < 50
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Lấy tất cả các lớp
    classes = pd.read_sql("SELECT id, name FROM classes", conn)
    low_attendance_list = []
    
    for _, cls in classes.iterrows():
        cid = cls['id']
        cname = cls['name']
        
        # 1. Tính tổng số buổi học của lớp này (Dựa trên số ngày unique có log)
        query_total_days = "SELECT COUNT(DISTINCT date(checkin_time)) FROM attendance_logs WHERE class_id = ?"
        c = conn.cursor()
        c.execute(query_total_days, (cid,))
        total_sessions = c.fetchone()[0]
        
        if total_sessions == 0: continue # Lớp chưa học buổi nào -> Bỏ qua
        
        # 2. Lấy danh sách SV và số buổi họ đi học
        # query này đếm số ngày unique mà mỗi SV có mặt
        query_sv = f"""
            SELECT s.id, s.name, COUNT(DISTINCT date(l.checkin_time)) as attended_sessions
            FROM enrollments e
            JOIN students s ON e.student_id = s.id
            LEFT JOIN attendance_logs l ON e.student_id = l.student_id AND e.class_id = l.class_id
            WHERE e.class_id = ?
            GROUP BY s.id
        """
        df_sv = pd.read_sql(query_sv, conn, params=(cid,))
        
        # 3. Tính toán và lọc
        df_sv['attendance_rate'] = (df_sv['attended_sessions'] / total_sessions * 100)
        df_sv['total_sessions'] = total_sessions
        df_sv['class_name'] = cname
        df_sv['class_id'] = cid
        
        # Lọc những ai dưới ngưỡng (hoặc vắng > 50% tức là đi học < 50%)
        bad_students = df_sv[df_sv['attendance_rate'] < threshold_percent]
        
        if not bad_students.empty:
            low_attendance_list.append(bad_students)
    
    conn.close()
    
    if low_attendance_list:
        return pd.concat(low_attendance_list, ignore_index=True)
    return pd.DataFrame()

def manual_add_attendance(student_id, class_id, date_str):
    """
    Hiệu chỉnh: Vắng -> Có mặt
    Thêm một log giả vào DB với giờ là 00:00:00 của ngày đó
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check xem ngày đó đã có chưa (để tránh add 2 lần dù logic unique date đã lo, nhưng cứ chắc ăn)
    check_query = "SELECT id FROM attendance_logs WHERE student_id=? AND class_id=? AND date(checkin_time)=?"
    c.execute(check_query, (student_id, class_id, date_str))
    if c.fetchone():
        conn.close()
        return False, "Sinh viên này đã được tính có mặt ngày hôm đó rồi!"
    
    # Insert log thủ công
    # Lưu ý: checkin_time format YYYY-MM-DD HH:MM:SS
    fake_time = f"{date_str} 12:00:00" 
    c.execute("INSERT INTO attendance_logs (student_id, class_id, checkin_time, image_evidence) VALUES (?, ?, ?, ?)",
              (student_id, class_id, fake_time, "MANUAL_UPDATE"))
    conn.commit()
    conn.close()
    return True, "Đã cập nhật: Có mặt"

def manual_remove_attendance(student_id, class_id, date_str):
    """
    Hiệu chỉnh: Có mặt -> Vắng
    Xóa TẤT CẢ các log của sinh viên đó trong ngày hôm đó (kể cả checkin sáng/chiều)
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # SQLite hàm date(checkin_time) giúp lọc theo ngày
    c.execute("DELETE FROM attendance_logs WHERE student_id=? AND class_id=? AND date(checkin_time)=?",
              (student_id, class_id, date_str))
    rows = c.rowcount
    conn.commit()
    conn.close()
    if rows > 0:
        return True, f"Đã xóa {rows} lượt check-in. Trạng thái: Vắng"
    return False, "Không tìm thấy dữ liệu điểm danh ngày này để xóa."

# --- CÁC HÀM CHO DASHBOARD & QUẢN LÝ NÂNG CAO ---
def get_attendance_sessions(class_id=None, date_filter=None):
    """
    Lấy danh sách các phiên điểm danh (Mỗi ngày học của 1 lớp là 1 phiên).
    Trả về: STT, Tên Lớp, Ngày, Sĩ số (Hiện diện/Tổng).
    """
    conn = sqlite3.connect(DB_PATH)
    
    # Base query: Lấy danh sách lớp và ngày có log (từ cả người quen và người lạ)
    query = """
        SELECT DISTINCT combined.class_id, c.name, combined.session_date
        FROM (
            SELECT class_id, date(checkin_time) as session_date FROM attendance_logs
            UNION
            SELECT class_id, session_date FROM unknown_logs
        ) combined
        JOIN classes c ON combined.class_id = c.id
        WHERE 1=1
    """
    params = []
    if class_id:
        query += " AND combined.class_id = ?"
        params.append(class_id)
    if date_filter:
        query += " AND combined.session_date = ?"
        params.append(str(date_filter))
        
    query += " ORDER BY combined.session_date DESC"
    
    df_sessions = pd.read_sql_query(query, conn, params=params)
    
    result = []
    for idx, row in df_sessions.iterrows():
        cid = row['class_id']
        cname = row['name']
        sdate = row['session_date']
        
        # Lấy sĩ số tổng
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM enrollments WHERE class_id=?", (cid,))
        total = cur.fetchone()[0]
        
        # Lấy số người có mặt ngày hôm đó
        cur.execute(f"SELECT COUNT(DISTINCT student_id) FROM attendance_logs WHERE class_id=? AND date(checkin_time)=?", (cid, sdate))
        present = cur.fetchone()[0]
        
        result.append({
            "STT": idx + 1,
            "ID Lớp": cid,
            "Tên Lớp": cname,
            "Ngày điểm danh": sdate,
            "Sĩ số": f"{present}/{total}",
            "present_count": present,
            "total_count": total
        })
        
    conn.close()
    return pd.DataFrame(result)

def get_session_details(class_id, date_str):
    """Lấy chi tiết ai vắng, ai có mặt trong ngày cụ thể"""
    conn = sqlite3.connect(DB_PATH)
    
    # Lấy toàn bộ SV trong lớp
    df_sv = pd.read_sql_query(
        "SELECT s.id, s.name, s.image_path FROM students s JOIN enrollments e ON s.id = e.student_id WHERE e.class_id=?", 
        conn, params=(class_id,)
    )
    
    # Lấy list id đã checkin
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT student_id FROM attendance_logs WHERE class_id=? AND date(checkin_time)=?", (class_id, date_str))
    present_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Map trạng thái
    df_sv['status'] = df_sv['id'].apply(lambda x: 'Có mặt' if x in present_ids else 'Vắng')
    return df_sv

def update_student_info(student_id, new_name=None, new_image_path=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if new_name:
        cur.execute("UPDATE students SET name=? WHERE id=?", (new_name, student_id))
    if new_image_path:
        cur.execute("UPDATE students SET image_path=? WHERE id=?", (new_image_path, student_id))
    conn.commit()
    conn.close()
    return True

def delete_students_bulk(student_id_list, class_id):
    """Xóa nhiều SV khỏi lớp cùng lúc"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        # Xóa enrollments
        query = f"DELETE FROM enrollments WHERE class_id=? AND student_id IN ({','.join(['?']*len(student_id_list))})"
        cur.execute(query, [class_id] + student_id_list)
        
        # Xóa logs điểm danh liên quan
        query_log = f"DELETE FROM attendance_logs WHERE class_id=? AND student_id IN ({','.join(['?']*len(student_id_list))})"
        cur.execute(query_log, [class_id] + student_id_list)
        
        conn.commit()
        return True, f"Đã xóa {cur.rowcount} sinh viên khỏi lớp."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()
        
    # --- Hàm thêm sinh viên (Cho phép ảnh rỗng) ---
def add_student_to_class(student_id, name, image_path, class_id, email=None, stt=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT * FROM students WHERE id=?", (student_id,))
        exist = c.fetchone()
        
        if exist:
            if image_path: 
                c.execute("UPDATE students SET name=?, image_path=?, email=? WHERE id=?", (name, image_path, email, student_id))
            else:
                c.execute("UPDATE students SET name=?, email=? WHERE id=?", (name, email, student_id))
        else:
            if image_path is None: image_path = ""
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO students (id, name, image_path, created_at, email) VALUES (?, ?, ?, ?, ?)", 
                      (student_id, name, image_path, created_at, email))

        joined_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if class_id: # Thêm điều kiện an toàn
            c.execute("SELECT * FROM enrollments WHERE student_id=? AND class_id=?", (student_id, class_id))
            if c.fetchone():
                if stt is not None:
                    c.execute("UPDATE enrollments SET stt=? WHERE student_id=? AND class_id=?", (stt, student_id, class_id))
            else:
                c.execute("INSERT INTO enrollments (student_id, class_id, joined_at, stt) VALUES (?, ?, ?, ?)", 
                          (student_id, class_id, joined_at, stt))
        
        conn.commit()
        return True, f"Đã lưu thông tin {name} ({student_id}) thành công!"
    except Exception as e:
        return False, f"Lỗi DB: {str(e)}"
    finally:
        conn.close()

# --- Hàm lấy danh sách sinh viên thiếu ảnh trong 1 lớp ---
def get_students_missing_image(class_id):
    conn = sqlite3.connect(DB_PATH)
    # Lấy TOÀN BỘ sinh viên của lớp đó kèm theo đường dẫn ảnh
    query = """
        SELECT s.id, s.name, s.image_path 
        FROM students s
        JOIN enrollments e ON s.id = e.student_id
        WHERE e.class_id = ?
    """
    df = pd.read_sql_query(query, conn, params=(class_id,))
    conn.close()
    
    # Hàm logic kiểm tra thực tế
    def is_image_missing(path):
        # 1. Bị trống trong Database (Null, Rỗng, hoặc dính chữ 'None')
        if not path or str(path).strip() == "" or str(path).lower() == "none":
            return True
        # 2. File vật lý KHÔNG tồn tại trên ổ cứng
        if not os.path.exists(str(path)):
            return True
        return False
        
    # Áp dụng bộ lọc
    if not df.empty:
        # Lọc ra những người mà is_image_missing trả về True
        df_missing = df[df['image_path'].apply(is_image_missing)].copy()
        return df_missing[['id', 'name']]
    
    return pd.DataFrame()

# --- HÀM ĐỔI MSSV (GIỮ NGUYÊN LỊCH SỬ) ---
def update_student_id(old_id, new_id, new_name=None, new_image_path=None):
    if old_id == new_id:
        # Nếu ID không đổi, chỉ update tên và ảnh
        return add_student_to_class(old_id, new_name, new_image_path, None) # None class_id vì chỉ update info

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # 1. Kiểm tra ID mới đã tồn tại chưa
        c.execute("SELECT id FROM students WHERE id=?", (new_id,))
        if c.fetchone():
            return False, f"Mã SV mới ({new_id}) đã tồn tại! Không thể đổi."

        # 2. Lấy thông tin ID cũ
        c.execute("SELECT name, image_path, created_at FROM students WHERE id=?", (old_id,))
        row = c.fetchone()
        if not row:
            return False, f"Không tìm thấy sinh viên cũ ({old_id})."
        
        old_name, old_img_path, created_at = row
        
        # Dùng tên/ảnh mới nếu có, không thì dùng lại cái cũ
        final_name = new_name if new_name else old_name
        
        # Xử lý đổi tên file ảnh
        final_img_path = old_img_path
        if new_image_path:
            # Nếu user upload ảnh mới -> Dùng ảnh mới
            final_img_path = new_image_path
        elif old_img_path and os.path.exists(old_img_path):
            # Nếu không up ảnh mới -> Đổi tên file ảnh cũ theo ID mới
            # Ví dụ: gallery/SV1.jpg -> gallery/SV2.jpg
            directory = os.path.dirname(old_img_path)
            extension = os.path.splitext(old_img_path)[1]
            new_path = os.path.join(directory, f"{new_id}{extension}")
            try:
                os.rename(old_img_path, new_path)
                final_img_path = new_path
            except Exception as e:
                print(f"Lỗi rename ảnh: {e}")
                # Nếu lỗi rename thì giữ nguyên path cũ (không ảnh hưởng logic DB)

        # 3. Tạo sinh viên mới (Clone)
        c.execute("INSERT INTO students (id, name, image_path, created_at) VALUES (?, ?, ?, ?)", 
                  (new_id, final_name, final_img_path, created_at))

        # 4. CHUYỂN DỮ LIỆU SANG NHÀ MỚI 
        
        # Cập nhật Enrollments (Các lớp đang học)
        c.execute("UPDATE enrollments SET student_id=? WHERE student_id=?", (new_id, old_id))
        
        # Cập nhật Logs (Lịch sử điểm danh)
        c.execute("UPDATE attendance_logs SET student_id=? WHERE student_id=?", (new_id, old_id))

        # 5. Xóa sinh viên cũ
        c.execute("DELETE FROM students WHERE id=?", (old_id,))

        conn.commit()
        return True, f"Đã đổi MSSV từ {old_id} -> {new_id} thành công!"

    except Exception as e:
        conn.rollback() # Hoàn tác nếu lỗi
        return False, f"Lỗi khi đổi ID: {str(e)}"
    finally:
        conn.close()
        
# --- Lấy danh sách các ngày đã điểm danh của 1 lớp ---
def get_attendance_dates_by_class(class_id):
    conn = sqlite3.connect(DB_PATH)
    # Gộp chung các ngày có log điểm danh VÀ các ngày có log người lạ
    query = """
        SELECT DISTINCT day FROM (
            SELECT date(checkin_time) as day FROM attendance_logs WHERE class_id = ?
            UNION
            SELECT session_date as day FROM unknown_logs WHERE class_id = ?
        )
        ORDER BY day DESC
    """
    try:
        cursor = conn.cursor()
        # Lưu ý: truyền 2 biến class_id vì query có 2 dấu ?
        cursor.execute(query, (class_id, class_id))
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"Lỗi lấy ngày: {e}")
        return []
    finally:
        conn.close()

# --- HÀM CẬP NHẬT HÀNG LOẠT (BATCH UPDATE) ---
def update_session_batch(class_id, date_str, updates_list):
    """
    Cập nhật trạng thái điểm danh cho cả lớp cùng lúc.
    updates_list: List các tuple [(student_id, new_status), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # Thời gian mặc định cho log sửa tay
        fake_time = f"{date_str} 12:00:00"
        
        for student_id, new_status in updates_list:
            # 1. Luôn xóa log cũ của sinh viên trong ngày đó trước (để tránh trùng lặp)
            c.execute("DELETE FROM attendance_logs WHERE student_id=? AND class_id=? AND date(checkin_time)=?",
                      (student_id, class_id, date_str))
            
            # 2. Nếu trạng thái mới là "Có mặt", chèn log mới vào
            if new_status == "Có mặt":
                c.execute("INSERT INTO attendance_logs (student_id, class_id, checkin_time, image_evidence) VALUES (?, ?, ?, ?)",
                          (student_id, class_id, fake_time, "MANUAL_BATCH_UPDATE"))
        
        conn.commit()
        return True, f"Đã cập nhật dữ liệu cho {len(updates_list)} sinh viên."
    except Exception as e:
        conn.rollback()
        return False, f"Lỗi khi lưu: {str(e)}"
    finally:
        conn.close()
        
# --- KHỐI QUẢN LÝ NGƯỜI LẠ (UNKNOWN FACES) ---

def log_unknown_face(class_id, session_date, image_path):
    """Lưu thông tin khuôn mặt lạ vào database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO unknown_logs (class_id, session_date, image_path, created_at) VALUES (?, ?, ?, ?)",
                  (class_id, session_date, image_path, now))
        conn.commit()
        return True, c.lastrowid
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def get_unknown_faces(class_id, session_date):
    """Lấy danh sách các khuôn mặt lạ trong 1 phiên điểm danh"""
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT id, image_path, created_at FROM unknown_logs WHERE class_id = ? AND session_date = ?"
    df = pd.read_sql_query(query, conn, params=(class_id, session_date))
    conn.close()
    return df

def delete_unknown_face(log_id):
    """Xóa bản ghi người lạ và tự động dọn dẹp thư mục rỗng nếu có"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # 1. Tìm đường dẫn file ảnh
        c.execute("SELECT image_path FROM unknown_logs WHERE id = ?", (log_id,))
        row = c.fetchone()
        
        if row and row[0]:
            file_path = row[0]
            
            # 2. Xóa file vật lý
            if os.path.exists(file_path):
                os.remove(file_path)
                
                # 3. Kiểm tra và xóa thư mục chứa nó (Thư mục Ngày) nếu đã rỗng
                dir_path = os.path.dirname(file_path)
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        
                        # (Tùy chọn nâng cao) Kiểm tra tiếp thư mục cha (Thư mục Lớp) xem có rỗng không
                        # Nếu lớp đó không còn ngày nào có người lạ, xóa luôn thư mục Lớp
                        parent_dir = os.path.dirname(dir_path)
                        if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                            os.rmdir(parent_dir)
                            
                except Exception as dir_e:
                    print(f"Bỏ qua thư mục do không rỗng hoặc lỗi: {dir_e}")
                    
        # 4. Xóa bản ghi trong Database
        c.execute("DELETE FROM unknown_logs WHERE id = ?", (log_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Lỗi xóa unknown face: {e}")
        return False
    finally:
        conn.close()
        
def delete_attendance_session(class_id, session_date):
    """Xóa toàn bộ điểm danh, ảnh và dọn sạch thư mục rỗng của một phiên"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        # Tập hợp chứa danh sách các thư mục cần kiểm tra sau khi xóa ảnh
        dirs_to_check = set() 

        # 1. TÌM VÀ XÓA FILE ẢNH NGƯỜI LẠ
        c.execute("SELECT image_path FROM unknown_logs WHERE class_id=? AND session_date=?", (class_id, session_date))
        for row in c.fetchall():
            if row[0] and os.path.exists(row[0]):
                os.remove(row[0]) # Xóa file vật lý
                dirs_to_check.add(os.path.dirname(row[0])) # Ghi nhớ cái thư mục chứa file này
                
        # 2. TÌM VÀ XÓA FILE ẢNH BẰNG CHỨNG ĐIỂM DANH (Của sinh viên quen)
        c.execute("SELECT image_evidence FROM attendance_logs WHERE class_id=? AND date(checkin_time)=?", (class_id, session_date))
        for row in c.fetchall():
            if row[0] and "MANUAL" not in row[0] and os.path.exists(row[0]):
                os.remove(row[0]) 
                dirs_to_check.add(os.path.dirname(row[0])) 

        # 3. DỌN DẸP THƯ MỤC RỖNG
        for d in dirs_to_check:
            try:
                # os.rmdir chỉ xóa được thư mục nếu bên trong nó không còn file nào
                if os.path.exists(d) and not os.listdir(d): 
                    os.rmdir(d)
            except Exception as e:
                print(f"Bỏ qua thư mục {d} vì không rỗng hoặc lỗi: {e}")

        # 4. XÓA BẢN GHI TRONG CƠ SỞ DỮ LIỆU
        c.execute("DELETE FROM attendance_logs WHERE class_id=? AND date(checkin_time)=?", (class_id, session_date))
        c.execute("DELETE FROM unknown_logs WHERE class_id=? AND session_date=?", (class_id, session_date))
        conn.commit()
        return True, "Đã xóa phiên và dọn sạch thư mục thành công"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()
        
def log_attendance_db(student_id, class_id, image_evidence):
    """
    Ghi nhận điểm danh vào DB. 
    Trả về True nếu là lượt điểm danh MỚI trong ngày (để UI biết mà hiện thông báo/lưu ảnh).
    Trả về False nếu hôm nay sinh viên đó đã điểm danh rồi.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        full_time_str = now.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Kiểm tra xem sinh viên này đã điểm danh trong lớp này ngày hôm nay chưa?
        c.execute("""SELECT id FROM attendance_logs 
                     WHERE student_id=? AND class_id=? AND date(checkin_time)=?""",
                  (student_id, class_id, date_str))
        
        if c.fetchone():
            # Nếu đã có data -> Không ghi thêm, trả về False
            return False 
        
        # 2. Nếu chưa có -> Insert log mới
        c.execute("""INSERT INTO attendance_logs 
                     (student_id, class_id, checkin_time, image_evidence) 
                     VALUES (?, ?, ?, ?)""",
                  (student_id, class_id, full_time_str, image_evidence))
        conn.commit()
        return True # Báo hiệu đã lưu thành công log mới
        
    except Exception as e:
        print(f"Lỗi ghi log điểm danh: {e}")
        return False
    finally:
        conn.close()
        
def get_student_id_by_email(email):
    """Tìm MSSV dựa trên Email"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM students WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def get_student_attendance_history(student_id, class_id):
    """
    Lấy lịch sử điểm danh chi tiết của 1 sinh viên trong tất cả các buổi học của lớp.
    Trả về DataFrame: Ngày | Trạng thái
    """
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Lấy danh sách TẤT CẢ các ngày đã điểm danh của lớp
    query_dates = """
        SELECT DISTINCT day FROM (
            SELECT date(checkin_time) as day FROM attendance_logs WHERE class_id = ?
            UNION
            SELECT session_date as day FROM unknown_logs WHERE class_id = ?
        ) ORDER BY day DESC
    """
    df_dates = pd.read_sql_query(query_dates, conn, params=(class_id, class_id))
    
    # 2. Lấy log của riêng sinh viên này
    query_logs = """
        SELECT date(checkin_time) as day, image_evidence 
        FROM attendance_logs 
        WHERE student_id = ? AND class_id = ?
    """
    df_logs = pd.read_sql_query(query_logs, conn, params=(student_id, class_id))
    conn.close()
    
    if df_dates.empty:
        return pd.DataFrame(columns=['Ngày', 'Trạng thái'])
        
    # Xóa trùng lặp (trường hợp điểm danh 2 lần 1 ngày)
    df_logs = df_logs.drop_duplicates(subset=['day'])
    
    # 3. Gộp bảng để biết ngày nào có đi, ngày nào vắng
    df_result = pd.merge(df_dates, df_logs, on='day', how='left')
    df_result['Trạng thái'] = df_result['image_evidence'].apply(lambda x: 'Có mặt' if pd.notnull(x) else 'Vắng')
    df_result.rename(columns={'day': 'Ngày'}, inplace=True)
    
    return df_result[['Ngày', 'Trạng thái']]

# Initialize DB lần đầu
init_db()