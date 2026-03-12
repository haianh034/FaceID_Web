import streamlit as st
from streamlit_option_menu import option_menu
from time import sleep

def make_sidebar():
    # CSS TÙY CHỈNH GIAO DIỆN
    st.markdown("""
        <style>
            /* 1. Ẩn danh sách file mặc định (quan trọng nhất) */
            [data-testid="stSidebarNav"] {
                display: none !important;
            }

            /* 2. Xử lý Header: KHÔNG ẨN, chỉ làm trong suốt */
            header[data-testid="stHeader"] {
                background-color: transparent !important; /* Nền trong suốt */
            }
            
            /* 3. Ẩn thanh trang trí cầu vồng trên cùng */
            [data-testid="stDecoration"] {
                display: none !important;
            }

            /* 4. Tùy chỉnh nút mở/đóng Sidebar (nút >) */
            /* Vì Header trong suốt nên nút này sẽ tự hiện ra, không cần hack vị trí */
            [data-testid="stSidebarCollapsedControl"] {
                color: #31333F !important; /* Màu đen xám cho dễ nhìn */
                background-color: white !important; /* Thêm nền trắng cho nút nổi bật */
                border: 1px solid #e5e7eb; /* Viền mỏng */
                border-radius: 5px;
                display: block !important;
            }

            /* 5. Đẩy nội dung chính lên cao đè lên vùng header trong suốt */
            .main .block-container {
                padding-top: 3rem !important; 
            }

            /* 6. Chỉnh padding bên trong Sidebar cho đẹp */
            section[data-testid="stSidebar"] {
                top: 0px !important; 
                height: 100vh !important;
            }
            section[data-testid="stSidebar"] > div {
                padding-top: 2rem;
            }
        </style>
    """, unsafe_allow_html=True)

    # VẼ MENU
    with st.sidebar:
        selected = option_menu(
            menu_title="FaceID App", 
            options=["Dashboard", "Điểm Danh", "Quản Lý Lớp", "Hiệu Chỉnh", "Cài Đặt"], 
            icons=["house", "camera", "people", "pencil", "gear"], 
            menu_icon="cast", 
            default_index=get_current_index(), 
            
            # --- CHỈNH SỬA PHẦN NÀY ĐỂ GIỐNG NATIVE STREAMLIT ---
            styles={
                # Container: Để trong suốt để hòa vào nền sidebar xám
                "container": {"padding": "0!important", "background-color": "transparent"},
                
                # Icon: Chỉnh nhỏ lại và màu tối hơn
                "icon": {"color": "#555", "font-size": "14px"}, 
                
                # Link (Chữ): Chỉnh về 14px, font chuẩn, màu đen xám
                "nav-link": {
                    "font-size": "14px", 
                    "text-align": "left", 
                    "margin": "0px", 
                    "padding": "10px 15px", # Padding chuẩn nút bấm
                    "--hover-color": "#f0f2f6", # Màu hover xám nhạt giống Streamlit
                    "font-family": "Source Sans Pro, sans-serif", # Font mặc định
                    "color": "#31333F", # Màu chữ mặc định
                    "font-weight": "400"
                },
                
                # Mục đang chọn: Màu xanh giống nút Primary
                "nav-link-selected": {
                    "background-color": "#0284c7", # Hoặc màu đỏ #ff4b4b nếu muốn giống hệt Streamlit gốc
                    "color": "white",
                    "font-weight": "600"
                },
                
                # Tiêu đề menu (Chữ FaceID App)
                "menu-title": {
                    "font-family": "Source Sans Pro, sans-serif",
                    "font-weight": "bold",
                    "color": "#31333F",
                    "font-size": "18px" # To hơn chút làm tiêu đề
                }
            }
        )
        
    # XỬ LÝ CHUYỂN TRANG
    current_page = st.session_state.get("current_page", "Dashboard")
    if selected != current_page:
        if selected == "Dashboard":
            st.switch_page("Dashboard.py")
        elif selected == "Điểm Danh":
            st.switch_page("pages/1_Diem_Danh.py")
        elif selected == "Quản Lý Lớp":
            st.switch_page("pages/2_Quan_Ly_Lop.py")
        elif selected == "Hiệu Chỉnh":
            st.switch_page("pages/3_Hieu_Chinh.py")
        elif selected == "Cài Đặt":
            st.switch_page("pages/4_Cai_Dat.py")

def get_current_index():
    current = st.session_state.get("current_page", "Dashboard")
    mapping = {
        "Dashboard": 0, "Điểm Danh": 1, "Quản Lý Lớp": 2, "Hiệu Chỉnh": 3, "Cài Đặt": 4
    }
    return mapping.get(current, 0)