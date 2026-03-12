import streamlit as st
import pandas as pd
from datetime import datetime
import core.db_manager as db 
from navigation import make_sidebar

st.set_page_config(page_title="Dashboard", layout="wide", page_icon="🏫", initial_sidebar_state="expanded")
st.session_state["current_page"] = "Dashboard"
make_sidebar()

# --- INIT SESSION STATE ---
if 'active_class_id' not in st.session_state: st.session_state.active_class_id = None
if 'active_class_name' not in st.session_state: st.session_state.active_class_name = None
if 'edit_session' not in st.session_state: st.session_state.edit_session = None

# SIDEBAR
classes = db.get_all_classes()
class_opts = {name: id for id, name in classes}

default_idx = None
if st.session_state.active_class_name in class_opts:
    all_names = list(class_opts.keys())
    default_idx = all_names.index(st.session_state.active_class_name)

selected_class_name = st.sidebar.selectbox(
    "Chọn lớp làm việc:", 
    list(class_opts.keys()) if classes else [],
    index=default_idx,
    placeholder="--- Chọn một lớp ---",
    key="sb_class_dash"
)

if selected_class_name:
    st.session_state.active_class_name = selected_class_name
    st.session_state.active_class_id = class_opts[selected_class_name]
else:
    st.session_state.active_class_name = None
    st.session_state.active_class_id = None

st.sidebar.write("") 

with st.sidebar.popover("Thêm lớp mới", use_container_width=True):
    st.markdown("### Tạo lớp mới")
    new_class_name = st.text_input("Nhập tên lớp:", key="new_class_dash")
    if st.button("Lưu tạo mới", type="primary", key="btn_add_dash"):
        if new_class_name:
            succ, msg = db.create_class(new_class_name)
            if succ: st.success("Đã tạo!"); st.rerun()
            else: st.error(msg)

if st.session_state.active_class_id:
    with st.sidebar.popover("🗑 Xóa lớp này", use_container_width=True):
        st.warning(f"Bạn đang xóa lớp: **{selected_class_name}**")
        if st.button("Xác nhận Xóa", key="btn_del_dash"):
            db.delete_class(st.session_state.active_class_id)
            st.session_state.active_class_id = None
            st.session_state.active_class_name = None
            st.rerun()

st.sidebar.divider()

# GIAO DIỆN CHÍNH
st.title("Tổng quan & Điểm danh")

btn_cols = st.columns([1, 2])
with btn_cols[0]:
    label_btn = "ĐIỂM DANH NGAY"
    if st.session_state.active_class_name:
        label_btn = f"ĐIỂM DANH: {st.session_state.active_class_name.upper()}"
    if st.button(label_btn, type="primary", use_container_width=True):
        st.switch_page("pages/1_Diem_Danh.py")

st.divider()

st.subheader("Lịch sử Điểm danh")
c1, c2, c3 = st.columns([3, 3, 1], vertical_alignment="bottom")

with c1:
    filter_default_idx = 0
    filter_options = ["Tất cả"] + list(class_opts.keys())
    if st.session_state.active_class_name in filter_options:
        filter_default_idx = filter_options.index(st.session_state.active_class_name)

    filter_class_sel = st.selectbox("Lọc dữ liệu theo lớp:", filter_options, index=filter_default_idx)
    filter_cid = class_opts[filter_class_sel] if filter_class_sel != "Tất cả" else None

with c2:
    filter_date = st.date_input("Lọc theo Ngày:", value=None)

with c3:
    if st.button("Tải lại", use_container_width=True):
        st.rerun()

df_sessions = db.get_attendance_sessions(class_id=filter_cid, date_filter=filter_date)

if df_sessions.empty:
    st.info("Chưa có dữ liệu điểm danh nào.")
else:
    df_sessions = df_sessions.reset_index(drop=True)
    df_sessions['STT'] = (df_sessions.index + 1).astype(str)

    st.dataframe(
        df_sessions[["STT", "Tên Lớp", "Ngày điểm danh", "Sĩ số"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "STT": st.column_config.TextColumn("STT", width="small"),
            "Tên Lớp": st.column_config.TextColumn("Tên Lớp"),
            "Ngày điểm danh": st.column_config.DateColumn("Ngày", format="YYYY-MM-DD"),
            "Sĩ số": st.column_config.TextColumn("Sĩ số")
        }
    )
    
    st.caption("Chọn phiên bên dưới để xem chi tiết:")
    session_options = {f"{row['STT']}. {row['Tên Lớp']} - {row['Ngày điểm danh']}": row for i, row in df_sessions.iterrows()}
    selected_session_key = st.selectbox("Chọn phiên:", list(session_options.keys()))
    
    if selected_session_key:
        session_data = session_options[selected_session_key]
        with st.container(border=True):
            st.markdown(f"### Chi tiết: {selected_session_key}")
            detail_cid = session_data['ID Lớp']
            detail_date = session_data['Ngày điểm danh']
            df_detail = db.get_session_details(detail_cid, detail_date)
            
            df_detail = df_detail.reset_index(drop=True)
            df_detail['STT'] = (df_detail.index + 1).astype(str)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tổng", len(df_detail))
            m2.metric("Có mặt", len(df_detail[df_detail['status']=='Có mặt']))
            m3.metric("Vắng", len(df_detail[df_detail['status']=='Vắng']))
            
            with m4:
                st.write("")
                if st.button("SỬA PHIÊN", type="primary", use_container_width=True, key=f"edit_{selected_session_key}"):
                    st.session_state.edit_session = {"class_id": detail_cid, "class_name": session_data['Tên Lớp'], "date": detail_date}
                    st.switch_page("pages/3_Hieu_Chinh.py")
                    
                # DÙNG POPOVER ĐỂ TẠO BƯỚC XÁC NHẬN TRƯỚC KHI XÓA
                with st.popover("XÓA PHIÊN", use_container_width=True):
                    st.warning("Cảnh báo: Thao tác này sẽ xóa toàn bộ lịch sử điểm danh và file ảnh của phiên học này. Bạn có chắc chắn không?")
                    
                    if st.button("XÁC NHẬN XÓA", use_container_width=True, key=f"confirm_del_{selected_session_key}"):
                        import time
                        db.delete_attendance_session(detail_cid, detail_date)
                        st.success("Đã xóa toàn bộ dữ liệu phiên này!")
                        time.sleep(1)
                        st.rerun()
            
            # HIỂN THỊ BẢNG CHI TIẾT DANH SÁCH SINH VIÊN VÀ TRẠNG THÁI
            st.dataframe(
                df_detail[['STT', 'id', 'name', 'status']], 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "STT": st.column_config.TextColumn("STT", width="small"),
                    "id": st.column_config.TextColumn("Mã số sinh viên"),  # <--- ĐỔI TÊN
                    "name": st.column_config.TextColumn("Họ và tên"),      # <--- ĐỔI TÊN
                    "status": st.column_config.TextColumn("Trạng thái")
                }
            )