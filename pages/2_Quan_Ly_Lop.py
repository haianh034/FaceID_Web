import time
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
tab1, tab2, tab3 = st.tabs(["DANH SÁCH & THỐNG KÊ", "QUẢN LÝ SINH VIÊN", "BỔ SUNG ẢNH"])

# === TAB 1: DANH SÁCH & THỐNG KÊ ===
with tab1:
    df_students = db.get_students_in_class(selected_cid)
    
    if df_students.empty:
        st.warning("Lớp chưa có sinh viên.")
    else:
        df_stats = db.get_class_stats_detailed(selected_cid)
        
        # Merge để ghép cột vắng mặt/có mặt vào bảng chính
        if not df_stats.empty:
            df_merged = pd.merge(df_students, df_stats[['id', 'present_count', 'absent_count']], left_on='Mã SV', right_on='id', how='left')
        else:
            df_merged = df_students.copy()
            df_merged['present_count'] = 0
            df_merged['absent_count'] = 0

        # Thanh tìm kiếm
        search_stats = st.text_input("🔍 Tìm sinh viên (Nhập Tên, Mã SV hoặc Email):", key="search_stats")
        if search_stats:
            df_merged = df_merged[df_merged['Họ Tên'].str.contains(search_stats, case=False) | 
                                  df_merged['Mã SV'].str.contains(search_stats, case=False) | 
                                  df_merged['Email'].str.fillna("").str.contains(search_stats, case=False)]

        # Định dạng lại dữ liệu hiển thị
        df_merged['Email'] = df_merged['Email'].fillna("—")
        df_merged['present_count'] = df_merged['present_count'].fillna(0).astype(int).astype(str)
        df_merged['absent_count'] = df_merged['absent_count'].fillna(0).astype(int).astype(str)
        
        if 'STT' in df_merged.columns and df_merged['STT'].notna().any():
            df_merged['STT_HienThi'] = df_merged['STT'].fillna(0).astype(int).astype(str).replace("0", "—")
        else:
            df_merged['STT_HienThi'] = (df_merged.reset_index().index + 1).astype(str)

        def highlight_warning(row):
            if int(row['absent_count']) >= 2:
                return ['background-color: #ffeba1'] * len(row)
            return [''] * len(row)

        st.dataframe(
            df_merged[['STT_HienThi', 'Mã SV', 'Họ Tên', 'Email', 'present_count', 'absent_count']].style.apply(highlight_warning, axis=1),
            column_config={
                "STT_HienThi": st.column_config.TextColumn("STT", width="small"),
                "Mã SV": st.column_config.TextColumn("Mã SV"),
                "Họ Tên": st.column_config.TextColumn("Họ và Tên"),
                "Email": st.column_config.TextColumn("Email"),
                "present_count": st.column_config.TextColumn("Có mặt"),
                "absent_count": st.column_config.TextColumn("Vắng (Buổi)")
            },
            use_container_width=True,
            hide_index=True
        )

# === TAB 2: QUẢN LÝ SINH VIÊN ===
with tab2:
    mode = st.radio("Chức năng:", ["Thêm/Sửa Sinh viên", "Import Excel", "Xóa Sinh viên"], horizontal=True)
    
    # CHỨC NĂNG 1: THÊM / SỬA SINH VIÊN
    if mode == "Thêm/Sửa Sinh viên":
        st.info("💡 Bạn có thể nhập **MSSV** hoặc **Email** để cập nhật thông tin. (Nếu thêm mới hoàn toàn, bắt buộc phải có MSSV).")
        
        c1, c2 = st.columns(2)
        stt_input = c1.number_input("Số Thứ Tự (Tùy chọn)", min_value=1, step=1, value=None)
        current_id = c1.text_input("Mã Sinh Viên (MSSV):", placeholder="Ví dụ: SV001").strip()
        
        email_input = c2.text_input("Email:", placeholder="Ví dụ: nva@gmail.com").strip()
        inp_name = c2.text_input("Họ và tên:")

        change_id_mode = st.checkbox("Tôi muốn đổi Mã số sinh viên (Sửa ID)")
        new_id_input = None
        if change_id_mode:
            new_id_input = st.text_input("Nhập MSSV Mới:", placeholder="Nhập mã mới...").strip()
            if new_id_input: st.warning(f"Đang đổi mã từ **{current_id}** sang **{new_id_input}**.")

        st.write("Ảnh đại diện (Tùy chọn):")
        img_opt = st.radio("Nguồn ảnh:", ["Upload", "Chụp ảnh"], horizontal=True)
        img_buffer = None
        
        if img_opt == "Upload":
            up = st.file_uploader("File ảnh", type=['jpg','png'])
            if up: img_buffer = up.read()
        else:
            cam = st.camera_input("Chụp ảnh")
            if cam: img_buffer = cam.read()
            
        if st.button("💾 Lưu thông tin", type="primary"):
            target_id = current_id
            
            if not target_id and not email_input:
                st.error("❌ Vui lòng nhập ít nhất Mã SV hoặc Email!")
            else:
                if not target_id and email_input:
                    found_id = db.get_student_id_by_email(email_input)
                    if found_id:
                        target_id = found_id
                        st.success(f"🔍 Đã tự động tìm thấy MSSV: {target_id} qua Email.")
                    else:
                        st.error("❌ Không tìm thấy sinh viên nào có Email này. Vui lòng nhập Mã SV để tạo mới.")
                        target_id = None
                        
                if target_id and not inp_name:
                    st.error("❌ Vui lòng nhập Họ và Tên.")
                elif target_id:
                    save_path = None
                    if img_buffer:
                        final_id = new_id_input if (change_id_mode and new_id_input) else target_id
                        save_path = f"dataset/gallery/{final_id}.jpg"
                        os.makedirs("dataset/gallery", exist_ok=True)
                        with open(save_path, "wb") as f: f.write(img_buffer)

                    if change_id_mode and new_id_input and new_id_input != target_id:
                        succ, msg = db.update_student_id(target_id, new_id_input, inp_name, save_path)
                        if succ:
                            db.add_student_to_class(new_id_input, inp_name, save_path, selected_cid, email=email_input if email_input else None, stt=stt_input)
                    else:
                        succ, msg = db.add_student_to_class(target_id, inp_name, save_path, selected_cid, email=email_input if email_input else None, stt=stt_input)
                    
                    if succ:
                        st.success("✅ Đã cập nhật sinh viên thành công!")
                        if change_id_mode: st.balloons()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------------------------------------------------
    # CHỨC NĂNG 2: IMPORT EXCEL 
    # ---------------------------------------------------------
    elif mode == "Import Excel":
        st.markdown("### 📥 Thêm danh sách từ Excel")
        st.info("💡 File Excel CẦN có 2 cột: **id** (Mã SV) và **name** (Họ tên). Các cột TÙY CHỌN: **stt** (Số thứ tự), **email**.")

        uploaded_file = st.file_uploader("Chọn file .xlsx hoặc .csv", type=['xlsx', 'csv'])
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_input = pd.read_csv(uploaded_file)
                else:
                    df_input = pd.read_excel(uploaded_file)
                
                df_input.columns = [c.lower().strip() for c in df_input.columns]
                
                if 'id' not in df_input.columns or 'name' not in df_input.columns:
                    st.error("❌ File thiếu cột 'id' hoặc 'name'. Vui lòng kiểm tra lại file Excel.")
                    st.dataframe(df_input.head(2)) 
                else:
                    st.write("Xem trước dữ liệu:")
                    st.dataframe(df_input.head())
                    
                    if st.button(f"🚀 Xác nhận Import {len(df_input)} sinh viên"):
                        count_success = 0
                        my_bar = st.progress(0)
                        
                        for i, row in df_input.iterrows():
                            sid = str(row['id']).strip()
                            sname = str(row['name']).strip()
                            
                            sst_val = int(row['stt']) if 'stt' in df_input.columns and not pd.isna(row['stt']) else None
                            email_val = str(row['email']).strip() if 'email' in df_input.columns and not pd.isna(row['email']) else None
                            
                            succ, _ = db.add_student_to_class(sid, sname, None, selected_cid, email=email_val, stt=sst_val)
                            if succ: count_success += 1
                            
                            my_bar.progress((i + 1) / len(df_input))
                        
                        st.success(f"✅ Đã thêm thành công {count_success}/{len(df_input)} sinh viên vào lớp!")
                        st.balloons()
            except Exception as e:
                st.error(f"Lỗi khi đọc file: {e}")

    # CHỨC NĂNG 3: XÓA SINH VIÊN 
    elif mode == "Xóa Sinh viên":
        st.markdown("### Xóa sinh viên khỏi lớp")
        df_sv = db.get_class_stats_detailed(selected_cid)
        
        if df_sv.empty:
            st.warning("Lớp này trống, không có gì để xóa.")
        else:
            student_opts = df_sv.apply(lambda x: f"{x['id']} - {x['name']}", axis=1).tolist()
            selected_to_del = st.multiselect("Chọn các sinh viên cần xóa:", student_opts)
            
            if selected_to_del:
                st.warning(f"Bạn đang chọn xóa **{len(selected_to_del)}** sinh viên. Dữ liệu điểm danh của họ trong lớp này cũng sẽ bị xóa.")
                
                col_del_1, col_del_2 = st.columns([1, 4])
                with col_del_1:
                    if st.button("XÁC NHẬN XÓA", type="primary"):
                        ids_to_del = [s.split(" - ")[0] for s in selected_to_del]
                        succ, msg = db.delete_students_bulk(ids_to_del, selected_cid)
                        
                        if succ:
                            st.success(msg)
                            time.sleep(1)
                            st.rerun() 
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
                        time.sleep(1)
                        st.rerun()
                    else: st.error(msg)
                else:
                    st.error("Chưa có ảnh.")