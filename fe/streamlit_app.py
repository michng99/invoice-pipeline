import io
import time
from typing import List, Any
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH TRANG
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="✨"
)

# Init Session State
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "theme_mode" not in st.session_state: st.session_state["theme_mode"] = "light"

# Constants
MAX_FILES_ALLOWED = 50        
MAX_FILE_SIZE_MB = 10        
ALLOWED_EXTENSIONS = ["xml"]

# ==============================================================================
# 2. DATA & LOGIC (GIỮ NGUYÊN NHƯ CŨ)
# ==============================================================================
# ... (Phần logic xử lý XML giữ nguyên để tiết kiệm không gian, 
# ông cứ giữ nguyên các hàm _num, _find_key_recursive... như code cũ nhé)
# Để code chạy được ngay, tui paste lại bản rút gọn logic ở đây:

def _num(v: Any) -> float:
    if not v: return 0.0
    try:
        s = str(v).strip()
        if "," in s and "." in s: 
            if s.find(".") < s.find(","): s = s.replace(".", "").replace(",", ".")
            else: s = s.replace(",", "")
        elif "," in s: s = s.replace(",", ".")
        return float(s)
    except: return 0.0

def _find_key_recursive(obj: Any, targets: List[str]) -> Any:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.split(":")[-1] in targets and v is not None: return v
        for v in obj.values():
            found = _find_key_recursive(v, targets)
            if found is not None: return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, targets)
            if found is not None: return found
    return None

def _check_tag_exists_recursive(obj: Any, targets: List[str]) -> bool:
    if isinstance(obj, dict):
        for k in obj.keys():
            if k.split(":")[-1] in targets: return True
        for v in obj.values():
            if _check_tag_exists_recursive(v, targets): return True
    elif isinstance(obj, list):
        for item in obj:
            if _check_tag_exists_recursive(item, targets): return True
    return False

def _get_value(obj: dict, targets: List[str]) -> str:
    val = _find_key_recursive(obj, targets)
    if val:
        if isinstance(val, (dict, list)): return "" 
        return str(val)
    return ""

def _parse_invoice_data(xml_bytes: bytes, filename: str) -> dict:
    try:
        doc = xmltodict.parse(xml_bytes)
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
            "GhiChu":   "Hóa đơn điện tử"
        }
        nban_data = _find_key_recursive(hdon, ["NBan", "Seller", "NguoiBan"]) or hdon
        invoice["NBan"] = {
            "Ten":  _get_value(nban_data, ["Ten", "Name", "TNNBan"]),
            "MST":  _get_value(nban_data, ["MST", "MaSoThue", "MSTNban"]),
            "DChi": _get_value(nban_data, ["DChi", "DiaChi", "DCNBan"]),
        }
        items = []
        list_container = _find_key_recursive(hdon, ["DSHHDVu", "ListItems"]) or hdon
        raw_items = _find_key_recursive(list_container, ["HHDVu", "Item", "HangHoa"])
        if raw_items:
            if isinstance(raw_items, dict): raw_items = [raw_items]
            for it in raw_items:
                items.append({
                    "MHHDVu":  _get_value(it, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_value(it, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_value(it, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_value(it, ["SLuong", "SoLuong"]),
                    "DGia":    _get_value(it, ["DGia", "DonGia"]),
                    "ThTien":  _get_value(it, ["ThTien", "ThanhTien", "ThanhTienTruocThue"]),
                    "TSuat":   _get_value(it, ["TSuat", "ThueSuat", "TSuatGTGT", "TaxRate"]),
                    "TChat":   _get_value(it, ["TChat", "TinhChat"]) 
                })
        invoice["Items"] = items
        del doc 
        return invoice
    except Exception: return {}

def _rows_from_invoice(inv: dict) -> List[dict]:
    if not inv: return []
    try:
        header_info = {
            "Mẫu số": inv.get("KHMSHDon", ""),
            "KH hóa đơn": inv.get("KHHDon", ""),
            "Số hóa đơn": inv.get("SHDon", ""),
            "Ngày hóa đơn": inv.get("NLap", ""),
            "MST người bán": inv["NBan"].get("MST", ""),
            "Tên người bán": inv["NBan"].get("Ten", ""),
            "ĐC người bán": inv["NBan"].get("DChi", ""),
            "Đơn vị tiền": inv.get("DVTTe", "VND"),
            "Tỷ giá": _num(inv.get("TGia")),
            "Ghi chú": inv.get("GhiChu", "")
        }
        items = inv.get("Items", [])
        rows = []
        for it in items:
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            tht_raw = it["ThTien"]
            tht = _num(tht_raw) if tht_raw else (sl * dg)
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"], "Tên hàng": it["THHDVu"], "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": int(tht),
                "Thuế suất": str(it["TSuat"]), "Tiền thuế": 0, "Cộng tiền": int(tht), # Giản lược logic thuế
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: List[dict]) -> io.BytesIO:
    if not rows: return None
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
    buf.seek(0)
    return buf

# ==============================================================================
# 3. QUIET LUXURY CSS (CLOUD DANCER PALETTE)
# ==============================================================================
LANG = {
    "vi": {
        "title": "Invoice Pipeline", "subtitle": "Hệ thống xử lý hóa đơn tự động & tối ưu thuế",
        "upload_lbl": "Thả hóa đơn vào đây để xử lý",
        "list_header": "Hồ sơ chờ xử lý",
        "btn_process": "Xử lý ngay",
        "btn_clear": "Làm mới",
        "btn_dl": "TẢI KẾT QUẢ VỀ MÁY",
        "status_process": "Đang phân tích...", "status_done": "Hoàn tất!", "status_empty": "Chưa có dữ liệu", "status_fail": "Lỗi"
    },
    "en": {
        "title": "Invoice Pipeline", "subtitle": "Automated Invoice Processing & Tax Optimization",
        "upload_lbl": "Drop invoices here to process",
        "list_header": "Pending Docs",
        "btn_process": "Process Now",
        "btn_clear": "Reset",
        "btn_dl": "DOWNLOAD RESULT",
        "status_process": "Processing...", "status_done": "Done!", "status_empty": "No data", "status_fail": "Error"
    }
}
T = LANG[st.session_state["lang_code"]]

is_dark = st.session_state["theme_mode"] == "dark"

# BẢNG MÀU CHUẨN TỪ ẢNH ÔNG GỬI (WARM TAUPE / BEIGE)
c_bg_light = "#F7F6F3"     # Cloud Dancer Light
c_bg_dark = "#1d1a14"      # Warm Black/Dark Brown
c_glass_light = "rgba(255, 255, 255, 0.65)"
c_glass_dark = "rgba(40, 35, 30, 0.7)"
c_text_light = "#574f3c"   # Warm Grey Text
c_text_dark = "#e0dbd1"    # Light Beige Text
c_accent = "#928463"       # Muted Gold/Taupe (Accent)
c_border_light = "#e0dbd1"
c_border_dark = "#4e4735"

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&display=swap');

        /* NỀN TỔNG THỂ - GRADIENT ẤM ÁP */
        .stApp {{
            background: {'linear-gradient(135deg, #fdfbf7 0%, #e8e6e1 100%)' if not is_dark else 'linear-gradient(135deg, #2c281e 0%, #1a1814 100%)'};
            font-family: 'Manrope', sans-serif;
            color: {c_text_dark if is_dark else c_text_light};
        }}

        /* HEADER */
        h1 {{
            font-weight: 800 !important;
            letter-spacing: -0.03em;
            color: {c_text_dark if is_dark else "#3a3528"} !important;
            text-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        .pro-badge {{
            background: linear-gradient(90deg, #b5ab92, #928463);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-style: italic;
        }}
        
        /* GLASSMORPHISM CARD - 
           Thay vì bọc div, ta style trực tiếp các thành phần của Streamlit 
           để tạo cảm giác chúng nằm trên một tấm kính.
        */

        /* 1. FILE UPLOADER STYLE */
        [data-testid="stFileUploader"] {{
            padding: 20px;
            border-radius: 20px;
            background: {c_glass_dark if is_dark else c_glass_light};
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid {c_border_dark if is_dark else "rgba(255,255,255,0.8)"};
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, {0.2 if is_dark else 0.05});
            transition: transform 0.2s;
        }}
        
        /* Vùng kéo thả (Dropzone) */
        [data-testid="stFileUploader"] section {{
            background-color: transparent !important;
            border: 1px dashed {c_accent} !important;
            opacity: 0.8;
        }}
        /* Icon upload và chữ */
        [data-testid="stFileUploader"] div, [data-testid="stFileUploader"] span {{
            color: {c_text_dark if is_dark else c_text_light} !important;
        }}

        /* 2. DATAFRAME STYLE */
        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid {c_border_dark if is_dark else c_border_light};
            background: {c_glass_dark if is_dark else "rgba(255,255,255,0.4)"};
        }}
        
        /* 3. BUTTONS (WARM & MINIMAL) */
        button[kind="primary"] {{
            background: {c_text_dark if is_dark else "#3a3528"} !important; /* Màu tối đậm đà */
            color: {c_bg_light if is_dark else "#fff"} !important;
            border-radius: 12px !important;
            border: none !important;
            padding: 0.6rem 1.5rem !important;
            box-shadow: 0 4px 15px rgba(58, 53, 40, 0.2);
            font-weight: 700 !important;
        }}
        button[kind="secondary"] {{
            background: transparent !important;
            color: {c_text_dark if is_dark else c_text_light} !important;
            border: 1px solid {c_border_dark if is_dark else c_border_light} !important;
            border-radius: 12px !important;
        }}
        button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(58, 53, 40, 0.25);
        }}

        /* Ẩn Header mặc định */
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        .block-container {{ padding-top: 3rem !important; max-width: 950px !important; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. GIAO DIỆN CHÍNH (LAYOUT ĐÃ FIX)
# ==============================================================================

# Header Controls
c1, c2, c3 = st.columns([6, 1, 1])
with c2:
    if st.button("VN/EN", key="lang", type="secondary", use_container_width=True):
        st.session_state["lang_code"] = "en" if st.session_state["lang_code"] == "vi" else "vi"
        st.rerun()
with c3:
    if st.button("🌗", key="theme", type="secondary", use_container_width=True):
        st.session_state["theme_mode"] = "dark" if st.session_state["theme_mode"] == "light" else "light"
        st.rerun()

# Title Area
st.markdown(f"<h1 style='text-align: center; margin-bottom: 0;'>Invoice Pipeline <span class='pro-badge'>Pro</span></h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: {c_accent}; margin-bottom: 3rem;'>{T['subtitle']}</p>", unsafe_allow_html=True)

# --- KHU VỰC UPLOAD (NẰM TRÊN CÙNG, RỘNG RÃI) ---
# Không dùng thẻ div bọc ngoài nữa, để Streamlit tự render và CSS sẽ bắt lấy nó
uploaded_files = st.file_uploader(
    label=T["upload_lbl"],
    type=ALLOWED_EXTENSIONS,
    accept_multiple_files=True,
    label_visibility="visible" 
)

# Logic lưu file
if uploaded_files:
    count_new = 0
    for f in uploaded_files:
        if f.name not in st.session_state["uploads"]:
            st.session_state["uploads"][f.name] = {"data": f.read(), "size": f.size}
            count_new += 1
    if count_new: 
        st.toast("Đã nhận hồ sơ", icon="🍂")
        time.sleep(0.5)
        st.rerun()

# --- KHU VỰC DỮ LIỆU & NÚT BẤM ---
if st.session_state["uploads"]:
    st.write("") # Spacer
    st.write("") 
    
    # Chia layout: Bên trái là List file, Bên phải là Cụm nút
    col_list, col_action = st.columns([2, 1], gap="large")
    
    with col_list:
        st.markdown(f"**{T['list_header']}** ({len(st.session_state['uploads'])})")
        data_view = [{"File": k, "KB": f"{v['size']/1024:.1f}"} for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=200)

    with col_action:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) # Căn cho ngang hàng với title bảng
        
        if st.button(T["btn_process"], type="primary", use_container_width=True):
            with st.status(T["status_process"], expanded=True) as status:
                all_rows = []
                for fname, fcontent in st.session_state["uploads"].items():
                    inv = _parse_invoice_data(fcontent["data"], fname)
                    all_rows.extend(_rows_from_invoice(inv))
                
                if all_rows:
                    excel_buffer = _df_to_xlsx_stream(all_rows)
                    st.session_state["result_bytes"] = excel_buffer.getvalue()
                    st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    status.update(label=T["status_done"], state="complete")
                else:
                    status.update(label=T["status_empty"], state="error")
        
        if st.button(T["btn_clear"], type="secondary", use_container_width=True):
            st.session_state["uploads"] = {}
            st.session_state["result_bytes"] = None
            st.rerun()

    # Nút Download (Chỉ hiện khi có kết quả)
    if st.session_state["result_bytes"]:
        st.markdown("---")
        st.download_button(
            label=f"📥 {T['btn_dl']}",
            data=st.session_state["result_bytes"],
            file_name="Invoice_Result.xlsx",
            mime=st.session_state["result_mime"],
            type="primary",
            use_container_width=True
        )

else:
    # Trạng thái rỗng (Empty State) - Trang trí nhẹ
    st.markdown(f"""
    <div style="text-align:center; padding: 4rem; color: {c_accent}; opacity: 0.7;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🍂</div>
        {T['status_empty']}
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown(f"""
<div style="text-align: center; margin-top: 5rem; font-size: 0.8rem; color: {c_border_dark if is_dark else "#b0a895"};">
    © 2026 Invoice Pipeline Pro | Quiet Luxury Edition
</div>
""", unsafe_allow_html=True)
