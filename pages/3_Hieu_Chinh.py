import streamlit as st
import pandas as pd
from datetime import datetime
import core.db_manager as db
import sys
import os
import time
import shutil
import re

# Setup đường dẫn để import navigation
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation import make_sidebar 

st.set_page_config(page_title="Hiệu chỉnh", layout="wide", page_icon="🛠")
st.session_state["current_page"] = "Hiệu Chỉnh"
make_sidebar()

st.title("Hiệu chỉnh & Cập nhật Dữ liệu")

# --- CHỌN LỚP ---
classes = db.get_all_classes()
if not classes:
    st.warning("Chưa có lớp nào.")
    st.stop()

c_opts = {name: id for id, name in classes}
selected_cname = st.selectbox("1. Chọn Lớp làm việc:", list(c_opts.keys()))
selected_cid = c_opts[selected_cname]

st.divider()

# --- CHIA 2 TABS LỚN ---
main_tab1, main_tab2 = st.tabs(["📅 HIỆU CHỈNH THEO PHIÊN (NGÀY)", "🧑‍🎓 HIỆU CHỈNH THEO SINH VIÊN"])

# ==========================================
# GIAO DIỆN THEO PHIÊN (NGÀY)
# ==========================================
with main_tab1:
    existing_dates = db.get_attendance_dates_by_class(selected_cid)
    
    col_date1, col_date2 = st.columns([1, 2])
    with col_date1:
        if existing_dates:
            selected_date_str = st.selectbox("Chọn ngày đã học:", existing_dates)
        else:
            st.info("Lớp này chưa có lịch sử.")
            sel_date = st.date_input("Chọn ngày mới:", value=datetime.now())
            selected_date_str = str(sel_date)

    if selected_cid and selected_date_str:
        sub_tab1, sub_tab2 = st.tabs(["Chỉnh sửa Trạng thái cả lớp", "Xử lý Người Lạ"])
        
        # SUB-TAB 1: TRẠNG THÁI
        with sub_tab1:
            df_detail = db.get_session_details(selected_cid, selected_date_str)
            if df_detail.empty:
                st.warning("Không tìm thấy sinh viên trong lớp này.")
            else:
                editor_df = df_detail[['id', 'name', 'status']].copy()
                editor_df.columns = ["Mã SV", "Họ và Tên", "Trạng thái"]
                
                st.info("💡 Chỉnh sửa trực tiếp ở cột 'Trạng thái', sau đó bấm 'Lưu thay đổi'.")
                edited_df = st.data_editor(
                    editor_df, use_container_width=True, hide_index=True,
                    column_config={
                        "Mã SV": st.column_config.TextColumn(disabled=True),
                        "Họ và Tên": st.column_config.TextColumn(disabled=True),
                        "Trạng thái": st.column_config.SelectboxColumn("Trạng thái", options=["Có mặt", "Vắng"], required=True)
                    },
                    key="editor_attendance" 
                )
                
                c_btn1, c_btn2 = st.columns([1, 4])
                with c_btn1:
                    if st.button("LƯU THAY ĐỔI", type="primary", use_container_width=True, key="btn_save_session"):
                        with st.spinner("Đang cập nhật..."):
                            updates_list = [(row['Mã SV'], row['Trạng thái']) for _, row in edited_df.iterrows()]
                            success, msg = db.update_session_batch(selected_cid, selected_date_str, updates_list)
                            if success:
                                st.success(msg)
                                time.sleep(1) 
                                st.rerun() 
                            else: st.error(msg)
                            
                count_present = len(edited_df[edited_df['Trạng thái'] == 'Có mặt'])
                st.caption(f"Sĩ số ngày này: {count_present}/{len(edited_df)}")

        # SUB-TAB 2: NGƯỜI LẠ (Đã tích hợp AI AI dọn rác ở Bước 3)
        with sub_tab2:
            df_unknown = db.get_unknown_faces(selected_cid, selected_date_str)
            if df_unknown.empty:
                st.success("Tuyệt vời! Không có khuôn mặt lạ nào trong phiên này.")
            else:
                st.info(f"Phát hiện {len(df_unknown)} khuôn mặt lạ chưa được nhận diện.")
                cols = st.columns(3)
                for index, row in df_unknown.iterrows():
                    log_id, img_path = row['id'], row['image_path']
                    with cols[index % 3]:
                        with st.container(border=True):
                            if os.path.exists(img_path): st.image(img_path, use_container_width=True)
                            else: st.error("Lỗi: Không tìm thấy ảnh")
                                
                            input_mssv = st.text_input("Nhập MSSV:", key=f"mssv_{log_id}", placeholder="VD: SV001").strip()
                            cb1, cb2 = st.columns(2)
                            
                            with cb1:
                                if st.button("Xác nhận", key=f"btn_ok_{log_id}", use_container_width=True):
                                    if not input_mssv: st.warning("Nhập MSSV!")
                                    else:
                                        import sqlite3
                                        conn = sqlite3.connect(db.DB_PATH)
                                        cur = conn.cursor()
                                        cur.execute("SELECT s.name, s.image_path FROM students s JOIN enrollments e ON s.id = e.student_id WHERE s.id=? AND e.class_id=?", (input_mssv, selected_cid))
                                        sv_info = cur.fetchone()
                                        conn.close()
                                        
                                        if not sv_info: st.error("MSSV không thuộc lớp này!")
                                        else:
                                            name, old_img = sv_info
                                            
                                            # Lưu bằng chứng
                                            safe_cname = re.sub(r'[\\/*?:"<>|]', "", selected_cname).strip()
                                            attendance_dir = os.path.join("dataset", "attendance_images", safe_cname, selected_date_str)
                                            os.makedirs(attendance_dir, exist_ok=True)
                                            ts = datetime.now().strftime("%H%M%S")
                                            new_evidence_path = os.path.join(attendance_dir, f"{input_mssv}_{ts}.jpg")
                                            shutil.copy(img_path, new_evidence_path)
                                            
                                            # Điểm danh
                                            db.manual_add_attendance(input_mssv, selected_cid, selected_date_str)
                                            conn_update = sqlite3.connect(db.DB_PATH)
                                            cur_up = conn_update.cursor()
                                            cur_up.execute("UPDATE attendance_logs SET image_evidence=? WHERE student_id=? AND class_id=? AND date(checkin_time)=?",
                                                        (new_evidence_path, input_mssv, selected_cid, selected_date_str))
                                            conn_update.commit(); conn_update.close()

                                            # Cập nhật Avatar nếu thiếu
                                            if not old_img or old_img.strip() == "" or "sample" in old_img:
                                                new_gallery_path = f"dataset/gallery/{input_mssv}.jpg"
                                                shutil.copy(img_path, new_gallery_path)
                                                db.update_student_info(input_mssv, new_image_path=new_gallery_path)
                                                st.toast(f"Đã cập nhật ảnh đại diện mới!", icon="🖼️")
                                            
                                            # AI Dọn rác
                                            with st.spinner("AI đang quét dọn ảnh trùng..."):
                                                other_unknowns = [(row_u['id'], row_u['image_path']) for _, row_u in df_unknown.iterrows() if row_u['id'] != log_id]
                                                from core.ai_engine import FaceAttendanceSystem
                                                ai_engine = FaceAttendanceSystem()
                                                similar_ids = ai_engine.compare_and_clean_unknowns(img_path, other_unknowns, threshold=0.45)
                                                
                                                db.delete_unknown_face(log_id)
                                                for dup_id in similar_ids: db.delete_unknown_face(dup_id)
                                                    
                                            st.success(f"Đã điểm danh cho {name}. AI tự động xóa {len(similar_ids) + 1} ảnh trùng!")
                                            time.sleep(2); st.rerun()
                                            
                            with cb2:
                                if st.button("Xóa rác", key=f"btn_del_{log_id}", use_container_width=True):
                                    db.delete_unknown_face(log_id)
                                    st.toast("Đã xóa!", icon="🗑️"); time.sleep(0.5); st.rerun()


# ==========================================
# GIAO DIỆN THEO SINH VIÊN
# ==========================================
with main_tab2:
    st.markdown("### Lịch sử chi tiết Sinh viên")
    df_stats = db.get_class_stats_detailed(selected_cid)
    
    if df_stats.empty:
        st.warning("Lớp chưa có sinh viên.")
    else:
        # Tạo danh sách lựa chọn có kèm tỷ lệ đi học cho sinh động
        student_options = []
        student_map = {}
        for _, row in df_stats.iterrows():
            label = f"[{row['id']}] {row['name']} - Đi: {row['present_count']}/{row['total_sessions']} buổi"
            student_options.append(label)
            student_map[label] = row['id']
            
        selected_sv_label = st.selectbox("🔍 Chọn sinh viên cần tra cứu:", student_options)
        target_sid = student_map[selected_sv_label]
        
        # Gọi hàm lấy lịch sử chi tiết
        df_history = db.get_student_attendance_history(target_sid, selected_cid)
        
        if df_history.empty:
            st.info("Lớp này chưa có dữ liệu điểm danh nào để hiển thị.")
        else:
            col_h1, col_h2 = st.columns([2, 3])
            
            with col_h1:
                st.write("**Bảng lịch sử điểm danh:**")
                # Lấy bản gốc để so sánh khi lưu
                original_df = df_history.copy() 
                
                edited_history = st.data_editor(
                    df_history, use_container_width=True, hide_index=True,
                    column_config={
                        "Ngày": st.column_config.TextColumn(disabled=True),
                        "Trạng thái": st.column_config.SelectboxColumn("Trạng thái", options=["Có mặt", "Vắng"], required=True)
                    },
                    key=f"editor_history_{target_sid}"
                )
                
                if st.button("💾 Lưu lịch sử Sinh viên", type="primary"):
                    changes_made = False
                    for index, row in edited_history.iterrows():
                        date_str = row['Ngày']
                        new_status = row['Trạng thái']
                        old_status = original_df.loc[index, 'Trạng thái']
                        
                        # Chỉ gọi DB xử lý khi có sự thay đổi thực sự
                        if new_status != old_status:
                            changes_made = True
                            if new_status == "Có mặt":
                                db.manual_add_attendance(target_sid, selected_cid, date_str)
                            else:
                                db.manual_remove_attendance(target_sid, selected_cid, date_str)
                                
                    if changes_made:
                        st.success("✅ Đã cập nhật thành công lịch sử của sinh viên!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.info("Không có thay đổi nào để lưu.")
            
            with col_h2:
                # Trang trí thêm cái biểu đồ hoặc hướng dẫn cho chuyên nghiệp
                st.write("**Ghi chú:**")
                st.info("""
                - Thay đổi cột **Trạng thái** thành 'Có mặt' hoặc 'Vắng' và ấn Lưu để điều chỉnh.
                - Nếu bạn chỉnh từ 'Vắng' -> 'Có mặt': Hệ thống sẽ tự tạo 1 log thủ công.
                - Nếu bạn chỉnh từ 'Có mặt' -> 'Vắng': Hệ thống sẽ xóa toàn bộ log điểm danh và ảnh bằng chứng của ngày hôm đó.
                """)