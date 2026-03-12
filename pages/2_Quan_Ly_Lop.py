from time import time
import streamlit as st
import pandas as pd
import sqlite3
import core.db_manager as db
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation import make_sidebar 

st.set_page_config(page_title="Quản lý Lớp", layout="wide")
st.session_state["current_page"] = "Quản Lý Lớp"
make_sidebar()

# --- INIT SESSION STATE ---
if 'active_class_id' not in st.session_state: st.session_state.active_class_id = None
if 'active_class_name' not in st.session_state: st.session_state.active_class_name = None

# SIDEBAR
classes = db.get_all_classes()
class_opts = {name: id for id, name in classes}

default_index = None
if st.session_state.active_class_name in class_opts:
    all_names = list(class_opts.keys())
    default_index = all_names.index(st.session_state.active_class_name)

selected_class_name = st.sidebar.selectbox(
    "Chọn lớp làm việc:", 
    list(class_opts.keys()) if classes else [],
    index=default_index,
    placeholder="--- Chọn một lớp ---",
    key="sb_class_ql"
)

if selected_class_name:
    new_id = class_opts[selected_class_name]
    if new_id != st.session_state.active_class_id:
        st.session_state.active_class_name = selected_class_name
        st.session_state.active_class_id = new_id
        st.rerun()

st.sidebar.write("") 

with st.sidebar.popover("Thêm lớp mới", use_container_width=True):
    st.markdown("### Tạo lớp mới")
    new_class_name = st.text_input("Nhập tên lớp:", key="new_class_ql")
    if st.button("Lưu tạo mới", type="primary", key="btn_add_ql"):
        if new_class_name:
            succ, msg = db.create_class(new_class_name)
            if succ: st.success("Đã tạo!"); st.rerun()
            else: st.error(msg)

if st.session_state.active_class_id:
    with st.sidebar.popover("🗑 Xóa lớp này", use_container_width=True):
        st.warning(f"Bạn đang xóa lớp: **{selected_class_name}**")
        if st.button("Xác nhận Xóa", key="btn_del_ql"):
            succ, msg = db.delete_class(st.session_state.active_class_id)
            if succ:
                st.session_state.active_class_id = None
                st.session_state.active_class_name = None
                st.success(msg)
                time.sleep(1)
                st.rerun()
            else:
                st.error("Có lỗi xảy ra khi xóa lớp.")

st.sidebar.divider()

# GIAO DIỆN CHÍNH
st.title("Quản lý Sinh viên & Thống kê")

if not st.session_state.active_class_id:
    st.info("Bạn có thể chọn lớp từ Sidebar hoặc bấm nút **Vào quản lý** ở danh sách dưới.")
    
    if classes:
        st.write("---")
        search_class = st.text_input("Tìm kiếm lớp nhanh:", placeholder="Nhập tên lớp...")
        display_classes = classes
        if search_class:
            display_classes = [c for c in classes if search_class.lower() in c[1].lower()]
        
        st.write(f"### Danh sách các lớp ({len(display_classes)}):")
        
        for cid, cname in display_classes:
            stats = db.get_class_stats_detailed(cid)
            si_so = len(stats)
            with st.container(border=True):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.write(f"**{cname}**") 
                    st.caption(f"Sĩ số: {si_so} sinh viên")
                with col2:
                    if st.button("Vào quản lý", key=f"btn_open_{cid}", use_container_width=True, type="primary"):
                        st.session_state.active_class_id = cid
                        st.session_state.active_class_name = cname
                        st.rerun()
    else:
        st.warning("Chưa có lớp nào.")
    st.stop() 

selected_cid = st.session_state.active_class_id
selected_cname = st.session_state.active_class_name

if st.button("Quay lại danh sách lớp"):
    st.session_state.active_class_id = None
    st.session_state.active_class_name = None
    st.rerun()

st.header(f"Lớp: {selected_cname}")
tab1, tab2, tab3 = st.tabs(["THỐNG KÊ", "QUẢN LÝ SINH VIÊN", "BỔ SUNG ẢNH"])

# === TAB 1: THỐNG KÊ ===
with tab1:
    df_sv = db.get_class_stats_detailed(selected_cid)
    if df_sv.empty:
        st.warning("Lớp chưa có sinh viên.")
    else:
        search_stats = st.text_input("Tìm sinh viên:", key="search_stats")
        if search_stats:
            df_sv = df_sv[df_sv['name'].str.contains(search_stats, case=False) | df_sv['id'].str.contains(search_stats, case=False)]

        df_sv = df_sv.reset_index(drop=True)
        df_sv['STT'] = (df_sv.index + 1).astype(str)
        df_sv['present_count'] = df_sv['present_count'].astype(str)
        df_sv['absent_count'] = df_sv['absent_count'].astype(str)

        def highlight_warning(row):
            if int(row['absent_count']) >= 2:
                return ['background-color: #ffeba1'] * len(row)
            return [''] * len(row)

        # [CẬP NHẬT] Đổi tiêu đề cột tại đây
        st.dataframe(
            df_sv[['STT', 'id', 'name', 'present_count', 'absent_count']].style.apply(highlight_warning, axis=1),
            column_config={
                "STT": st.column_config.TextColumn("STT", width="small"),
                "id": st.column_config.TextColumn("Mã số sinh viên"),  # <--- ĐỔI TÊN
                "name": st.column_config.TextColumn("Họ và tên"),      # <--- ĐỔI TÊN
                "present_count": st.column_config.TextColumn("Có mặt"),
                "absent_count": st.column_config.TextColumn("Vắng (Buổi)")
            },
            use_container_width=True,
            hide_index=True
        )

# === TAB 2: QUẢN LÝ SINH VIÊN ===
with tab2:
    # Menu chức năng
    mode = st.radio("Chức năng:", ["Thêm/Sửa Sinh viên", "Import Excel", "Xóa Sinh viên"], horizontal=True)
    
    # CHỨC NĂNG 1: THÊM / SỬA SINH VIÊN
    if mode == "Thêm/Sửa Sinh viên":
        st.info("Nhập MSSV hiện tại để tìm kiếm. Sau đó có thể sửa Tên, Ảnh hoặc đổi sang MSSV mới.")
        
        c1, c2 = st.columns(2)
        current_id = c1.text_input("Nhập MSSV hiện tại:", placeholder="Ví dụ: SV001").strip()
        
        current_name_val = ""
        if current_id:
            conn = sqlite3.connect(db.DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT name FROM students WHERE id=?", (current_id,))
            res = cur.fetchone()
            conn.close()
            if res: current_name_val = res[0]
            else: 
                if len(current_id) > 0: st.caption("✨ Đây là sinh viên mới.")

        inp_name = c2.text_input("Họ và tên:", value=current_name_val)

        change_id_mode = st.checkbox("Tôi muốn đổi Mã số sinh viên (Sửa ID)")
        new_id_input = None
        if change_id_mode:
            new_id_input = st.text_input("Nhập MSSV Mới:", placeholder="Nhập mã mới...").strip()
            if new_id_input: st.warning(f"Đang đổi mã từ **{current_id}** sang **{new_id_input}**.")

        st.write("Ảnh đại diện:")
        img_opt = st.radio("Nguồn ảnh:", ["Upload", "Chụp ảnh"], horizontal=True)
        img_buffer = None
        
        if img_opt == "Upload":
            up = st.file_uploader("File ảnh", type=['jpg','png'])
            if up: img_buffer = up.read()
        else:
            cam = st.camera_input("Chụp ảnh")
            if cam: img_buffer = cam.read()
            
        if st.button("Lưu thông tin", type="primary"):
            if not current_id or not inp_name:
                st.error("Vui lòng nhập Mã SV và Tên.")
            else:
                save_path = None
                if img_buffer:
                    target_id = new_id_input if (change_id_mode and new_id_input) else current_id
                    save_path = f"dataset/gallery/{target_id}.jpg"
                    # Tạo thư mục nếu chưa có
                    os.makedirs("dataset/gallery", exist_ok=True)
                    with open(save_path, "wb") as f: f.write(img_buffer)

                if change_id_mode and new_id_input and new_id_input != current_id:
                    succ, msg = db.update_student_id(current_id, new_id_input, inp_name, save_path)
                else:
                    succ, msg = db.add_student_to_class(current_id, inp_name, save_path if save_path else None, selected_cid)
                
                if succ:
                    st.success(msg)
                    if change_id_mode: st.balloons()
                else:
                    st.error(msg)

    # CHỨC NĂNG 2: IMPORT EXCEL 
    elif mode == "Import Excel":
        st.markdown("### Thêm danh sách từ Excel")
        st.info("File Excel cần có 2 cột tiêu đề: **id** (Mã SV) và **name** (Họ tên).")

        uploaded_file = st.file_uploader("Chọn file .xlsx hoặc .csv", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                # Đọc file dựa vào đuôi mở rộng
                if uploaded_file.name.endswith('.csv'):
                    df_input = pd.read_csv(uploaded_file)
                else:
                    df_input = pd.read_excel(uploaded_file)
                
                # Chuẩn hóa tên cột về chữ thường để tránh lỗi (ID, Id -> id)
                df_input.columns = [c.lower().strip() for c in df_input.columns]
                
                # Kiểm tra cột bắt buộc
                if 'id' not in df_input.columns or 'name' not in df_input.columns:
                    st.error("File thiếu cột 'id' hoặc 'name'. Vui lòng kiểm tra lại file Excel.")
                    st.dataframe(df_input.head(2)) # Hiện thử cho user xem
                else:
                    st.write("Xem trước dữ liệu:")
                    st.dataframe(df_input.head())
                    
                    if st.button(f"Xác nhận Import {len(df_input)} sinh viên"):
                        count_success = 0
                        my_bar = st.progress(0)
                        
                        for i, row in df_input.iterrows():
                            sid = str(row['id']).strip()
                            sname = str(row['name']).strip()
                            
                            # Gọi hàm thêm vào lớp (Ảnh để None/Null)
                            succ, _ = db.add_student_to_class(sid, sname, None, selected_cid)
                            if succ: count_success += 1
                            
                            # Cập nhật thanh tiến trình
                            my_bar.progress((i + 1) / len(df_input))
                        
                        st.success(f"Đã thêm thành công {count_success}/{len(df_input)} sinh viên vào lớp!")
                        st.balloons()
            except Exception as e:
                st.error(f"Lỗi khi đọc file: {e}")

    # CHỨC NĂNG 3: XÓA SINH VIÊN 
    elif mode == "Xóa Sinh viên":
        st.markdown("### Xóa sinh viên khỏi lớp")
        
        # Lấy danh sách SV hiện tại để chọn xóa
        df_sv = db.get_class_stats_detailed(selected_cid)
        
        if df_sv.empty:
            st.warning("Lớp này trống, không có gì để xóa.")
        else:
            # Tạo danh sách lựa chọn dạng "Mã - Tên"
            student_opts = df_sv.apply(lambda x: f"{x['id']} - {x['name']}", axis=1).tolist()
            
            selected_to_del = st.multiselect("Chọn các sinh viên cần xóa:", student_opts)
            
            if selected_to_del:
                st.warning(f"Bạn đang chọn xóa **{len(selected_to_del)}** sinh viên. Dữ liệu điểm danh của họ trong lớp này cũng sẽ bị xóa.")
                
                col_del_1, col_del_2 = st.columns([1, 4])
                with col_del_1:
                    if st.button("XÁC NHẬN XÓA", type="primary"):
                        # Tách lấy ID từ chuỗi lựa chọn
                        ids_to_del = [s.split(" - ")[0] for s in selected_to_del]
                        
                        # Gọi hàm xóa bulk từ db_manager
                        succ, msg = db.delete_students_bulk(ids_to_del, selected_cid)
                        
                        if succ:
                            st.success(msg)
                            st.rerun() # Tải lại trang
                        else:
                            st.error(msg)

# === TAB 3: BỔ SUNG ẢNH ===
with tab3:
    st.markdown("### Danh sách sinh viên chưa có ảnh")
    df_missing = db.get_students_missing_image(selected_cid)
    
    if df_missing.empty:
        st.success("Tất cả sinh viên đã có ảnh.")
    else:
        st.info(f"Có {len(df_missing)} sinh viên thiếu ảnh.")
        missing_opts = {f"{row['id']} - {row['name']}": row for _, row in df_missing.iterrows()}
        selected_missing = st.selectbox("Chọn sinh viên:", list(missing_opts.keys()))
        
        if selected_missing:
            curr_sv = missing_opts[selected_missing]
            st.markdown(f"**Cập nhật cho:** `{curr_sv['name']}` (MSSV: `{curr_sv['id']}`)")
            
            c_up1, c_up2 = st.columns(2)
            img_buffer_update = None
            
            with c_up1:
                st.write("Upload ảnh")
                up_missing = st.file_uploader("Chọn ảnh", type=['jpg','png'], key="up_miss")
                if up_missing: img_buffer_update = up_missing.read()
                
            with c_up2:
                st.write("Chụp ảnh")
                cam_missing = st.camera_input("Chụp ảnh", key="cam_miss")
                if cam_missing: img_buffer_update = cam_missing.read()
            
            if st.button("Lưu ảnh mới", type="primary", key="btn_save_miss"):
                if img_buffer_update:
                    save_path = f"dataset/gallery/{curr_sv['id']}.jpg"
                    with open(save_path, "wb") as f: f.write(img_buffer_update)
                    res, msg = db.add_student_to_class(curr_sv['id'], curr_sv['name'], save_path, selected_cid)
                    if res: 
                        st.success(f"Đã cập nhật ảnh cho {curr_sv['name']}!")
                        st.rerun()
                    else: st.error(msg)
                else:
                    st.error("Chưa có ảnh.")