import streamlit as st
import pandas as pd
from datetime import datetime
import core.db_manager as db
import sys
import os
import time
import shutil

# Setup đường dẫn để import navigation
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation import make_sidebar 

# 1. CẤU HÌNH TRANG
st.set_page_config(page_title="Hiệu chỉnh", layout="wide", page_icon="🛠")
st.session_state["current_page"] = "Hiệu Chỉnh"
make_sidebar()

st.title("Hiệu chỉnh Dữ liệu (Chế độ chỉnh sửa hàng loạt)")

# --- BIẾN CỤC BỘ ---
selected_cid = None
selected_date_str = None
selected_cname = None

# --- LOGIC 1: LẤY THÔNG TIN (TỪ DASHBOARD HOẶC CHỌN TAY) ---
if 'edit_session' in st.session_state and st.session_state.edit_session:
    session = st.session_state.edit_session
    selected_cid = session['class_id']
    selected_cname = session['class_name']
    selected_date_str = session['date']
    
    st.success(f"Đang sửa phiên: **{selected_cname}** - Ngày: **{selected_date_str}**")
    if st.button("Chọn phiên khác"):
        st.session_state.edit_session = None
        st.rerun()
else:
    # Chọn thủ công
    classes = db.get_all_classes()
    if not classes:
        st.warning("Chưa có lớp nào.")
        st.stop()
        
    c_opts = {name: id for id, name in classes}
    col_sel_1, col_sel_2 = st.columns(2)
    
    with col_sel_1:
        sel_name = st.selectbox("1. Chọn Lớp:", list(c_opts.keys()))
        selected_cid = c_opts[sel_name]
        selected_cname = sel_name
        
    existing_dates = db.get_attendance_dates_by_class(selected_cid)
    
    with col_sel_2:
        if existing_dates:
            selected_date_str = st.selectbox("2. Chọn ngày đã học:", existing_dates)
        else:
            st.info("Lớp này chưa có dữ liệu lịch sử.")
            sel_date = st.date_input("Chọn ngày mới:", value=datetime.now())
            selected_date_str = str(sel_date)
            
    st.divider()

# --- LOGIC 2 & 3: HIỂN THỊ GIAO DIỆN TABS ---
if selected_cid and selected_date_str:
    # Tạo 2 Tab
    tab1, tab2 = st.tabs(["Chỉnh sửa Trạng thái", "Xử lý Người Lạ"])
    
    # TAB 1: CHỈNH SỬA TRẠNG THÁI ĐIỂM DANH
    with tab1:
        df_detail = db.get_session_details(selected_cid, selected_date_str)
        
        if df_detail.empty:
            st.warning("Không tìm thấy sinh viên trong lớp này.")
        else:
            editor_df = df_detail[['id', 'name', 'status']].copy()
            editor_df.columns = ["Mã SV", "Họ và Tên", "Trạng thái"]
            
            st.info("Hướng dẫn: Chỉnh sửa trực tiếp cột 'Trạng thái' bên dưới, sau đó bấm 'Lưu thay đổi'.")
            
            edited_df = st.data_editor(
                editor_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Mã SV": st.column_config.TextColumn(disabled=True),
                    "Họ và Tên": st.column_config.TextColumn(disabled=True),
                    "Trạng thái": st.column_config.SelectboxColumn(
                        "Trạng thái",
                        options=["Có mặt", "Vắng"],
                        required=True,
                        width="medium"
                    )
                },
                key="editor_attendance" 
            )
            
            st.write("")
            col_btn_1, col_btn_2 = st.columns([1, 4])
            
            with col_btn_1:
                if st.button("LƯU THAY ĐỔI", type="primary", use_container_width=True):
                    with st.spinner("Đang cập nhật cơ sở dữ liệu..."):
                        updates_list = []
                        for index, row in edited_df.iterrows():
                            student_id = row['Mã SV']
                            new_status = row['Trạng thái']
                            updates_list.append((student_id, new_status))
                        
                        success, msg = db.update_session_batch(selected_cid, selected_date_str, updates_list)
                        
                        if success:
                            st.success(f"{msg}")
                            time.sleep(1) 
                            st.rerun() 
                        else:
                            st.error(f"Lỗi: {msg}")

            with col_btn_2:
                if st.button("Hủy / Tải lại"):
                    st.rerun()

            count_present = len(edited_df[edited_df['Trạng thái'] == 'Có mặt'])
            count_total = len(edited_df)
            st.caption(f"Thống kê trên bảng: Có mặt {count_present}/{count_total} ({round(count_present/count_total*100, 1)}%)")

    # TAB 2: XỬ LÝ NGƯỜI LẠ 
    with tab2:
        st.markdown("### Nhận diện & Liên kết Người Lạ")
        df_unknown = db.get_unknown_faces(selected_cid, selected_date_str)
        
        if df_unknown.empty:
            st.success("Tuyệt vời! Không có khuôn mặt lạ nào trong phiên này.")
        else:
            st.info(f"Phát hiện {len(df_unknown)} khuôn mặt lạ chưa được nhận diện.")
            
            # Hiển thị ảnh dạng lưới 3 cột cho gọn
            cols = st.columns(3)
            for index, row in df_unknown.iterrows():
                log_id = row['id']
                img_path = row['image_path']
                
                with cols[index % 3]:
                    with st.container(border=True):
                        # 1. Hiển thị ảnh
                        if os.path.exists(img_path):
                            st.image(img_path, use_container_width=True)
                        else:
                            st.error("Lỗi: Không tìm thấy file ảnh")
                            
                        # 2. Ô nhập MSSV
                        input_mssv = st.text_input("Nhập MSSV:", key=f"mssv_{log_id}", placeholder="VD: SV001").strip()
                        
                        c_btn1, c_btn2 = st.columns(2)
                        
                        # Nút Xác nhận
                        with c_btn1:
                            if st.button("Xác nhận", key=f"btn_ok_{log_id}", use_container_width=True):
                                if not input_mssv:
                                    st.warning("Vui lòng nhập MSSV!")
                                else:
                                    import sqlite3
                                    # Kiểm tra xem MSSV có thuộc lớp này không
                                    conn = sqlite3.connect(db.DB_PATH)
                                    cur = conn.cursor()
                                    cur.execute("""
                                        SELECT s.name, s.image_path 
                                        FROM students s 
                                        JOIN enrollments e ON s.id = e.student_id 
                                        WHERE s.id=? AND e.class_id=?
                                    """, (input_mssv, selected_cid))
                                    sv_info = cur.fetchone()
                                    conn.close()
                                    
                                    if not sv_info:
                                        st.error("MSSV không có trong lớp này!")
                                    else:
                                        name, old_img = sv_info
                                        
                                        # BƯỚC A: Điểm danh (Chuyển thành Có mặt)
                                        db.manual_add_attendance(input_mssv, selected_cid, selected_date_str)
                                        
                                        # BƯỚC B: Cập nhật ảnh nếu SV chưa có ảnh thật (ảnh rỗng hoặc đang dùng sample.jpg)
                                        if not old_img or old_img.strip() == "" or "sample" in old_img:
                                            new_img_path = f"dataset/gallery/{input_mssv}.jpg"
                                            # Trích xuất file ảnh sang gallery
                                            shutil.copy(img_path, new_img_path)
                                            # Update path trong DB
                                            db.update_student_info(input_mssv, new_image_path=new_img_path)
                                            st.toast(f"Đã cập nhật ảnh đại diện mới cho {name}!", icon="🖼️")
                                        
                                        # BƯỚC C: Dọn dẹp Log người lạ
                                        db.delete_unknown_face(log_id)
                                        
                                        st.success(f"Đã xác nhận điểm danh cho {name}!")
                                        time.sleep(1)
                                        st.rerun()
                                        
                        # Nút Xóa / Bỏ qua (Nếu đó không phải sinh viên)
                        with c_btn2:
                            if st.button("Xóa", key=f"btn_del_{log_id}", use_container_width=True):
                                db.delete_unknown_face(log_id)
                                st.toast("Đã xóa ảnh người lạ!", icon="🗑️")
                                time.sleep(0.5)
                                st.rerun()