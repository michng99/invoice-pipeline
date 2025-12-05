import io
import time
from typing import List, Any
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH & TRẠNG THÁI
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="wide", # Đổi sang wide để layout 2 cột thoáng hơn
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
# 2. TỪ ĐIỂN NGÔN NGỮ
# ==============================================================================
LANG = {
    "vi": {
        "title": "Invoice Pipeline", "subtitle": "Hệ thống xử lý hóa đơn tự động & tối ưu thuế",
        "upload_lbl": "Kéo thả hoặc chọn file XML hóa đơn",
        "list_header": "Hồ sơ chờ xử lý",
        "btn_process": "⚡ Xử lý & Xuất Excel",
        "btn_clear": "🔄 Làm mới",
        "btn_dl": "TẢI KẾT QUẢ VỀ MÁY",
        "toast_add": "Đã thêm hồ sơ mới",
        "status_process": "Đang phân tích dữ liệu...",
        "status_done": "Hoàn tất!",
        "status_empty": "Chưa có dữ liệu đầu vào",
        "status_fail": "Thất bại",
        "col_file": "Tên tập tin", "col_size": "Dung lượng",
        "theme_light": "Sáng", "theme_dark": "Tối" 
    },
    "en": {
        "title": "Invoice Pipeline", "subtitle": "Automated Invoice Processing & Tax Optimization",
        "upload_lbl": "Drag & drop or select XML files",
        "list_header": "Pending Documents",
        "btn_process": "⚡ Process & Export",
        "btn_clear": "🔄 Reset Pipeline",
        "btn_dl": "DOWNLOAD RESULT",
        "toast_add": "Documents added",
        "status_process": "Analyzing data...",
        "status_done": "Done!",
        "status_empty": "No input data",
        "status_fail": "Failed",
        "col_file": "Filename", "col_size": "Size",
        "theme_light": "Light", "theme_dark": "Dark"
    }
}
T = LANG[st.session_state["lang_code"]]

# ==============================================================================
# 3. QUIET LUXURY CSS ENGINE (REVAMPED)
# ==============================================================================
is_dark = st.session_state["theme_mode"] == "dark"

# Palette màu Slate/Gray cao cấp
colors = {
    "bg_app": "#0f172a" if is_dark else "#f8fafc", # Slate-900 vs Slate-50
    "bg_card": "#1e293b" if is_dark else "#ffffff", # Slate-800 vs White
    "text_main": "#f1f5f9" if is_dark else "#1e293b", # Slate-100 vs Slate-800
    "text_sub": "#94a3b8" if is_dark else "#64748b", # Slate-400 vs Slate-500
    "border": "#334155" if is_dark else "#e2e8f0",   # Slate-700 vs Slate-200
    
    # Button Colors
    "btn_primary_bg": "#4f46e5", # Indigo-600 (Màu điểm nhấn chính)
    "btn_primary_text": "#ffffff",
    "btn_secondary_bg": "transparent",
    "btn_secondary_border": "#475569" if is_dark else "#cbd5e1",
    
    # Upload Zone
    "upload_bg": "#334155" if is_dark else "#f1f5f9",
    "shadow": "0 20px 25px -5px rgba(0, 0, 0, 0.3)" if is_dark else "0 20px 25px -5px rgba(0, 0, 0, 0.1)"
}

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        /* --- GLOBAL RESET --- */
        .stApp {{
            background-color: {colors['bg_app']};
            font-family: 'Inter', sans-serif;
            color: {colors['text_main']};
        }}
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        
        /* Căn chỉnh container chính */
        .block-container {{
            padding-top: 3rem !important;
            padding-bottom: 5rem !important;
            max-width: 1000px !important; /* Giới hạn chiều rộng để Card đẹp hơn */
        }}

        /* --- TYPOGRAPHY --- */
        h1 {{
            font-weight: 800 !important; 
            font-size: 2.5rem !important;
            text-align: center;
            letter-spacing: -0.025em;
            margin-bottom: 0.5rem;
            color: {colors['text_main']} !important;
        }}
        .pro-badge {{
            color: #4f46e5; /* Indigo */
            font-style: italic;
        }}
        .subtitle {{
            text-align: center; 
            color: {colors['text_sub']} !important;
            font-size: 1rem; 
            font-weight: 500; 
            margin-bottom: 2rem;
        }}

        /* --- THE MAIN CARD (Cái khung bao quanh) --- */
        div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {{
            /* Hack nhẹ để target block nội dung chính nếu cần, nhưng ta sẽ dùng container riêng */
        }}

        /* Style cho cái Container bọc nội dung (được gọi bằng st.container) */
        .main-card {{
            background-color: {colors['bg_card']};
            border: 1px solid {colors['border']};
            border-radius: 24px;
            padding: 40px;
            box-shadow: {colors['shadow']};
        }}

        /* --- FILE UPLOADER (Dashed Box) --- */
        [data-testid="stFileUploader"] {{
            padding: 0;
            margin-bottom: 2rem;
        }}
        [data-testid="stFileUploader"] section {{
            background-color: {colors['bg_app']} !important; /* Màu nền của vùng drop */
            border: 2px dashed {colors['border']} !important;
            border-radius: 16px !important;
            padding: 2rem !important;
            box-shadow: none !important;
            transition: all 0.2s ease;
        }}
        [data-testid="stFileUploader"] section:hover {{
            border-color: #4f46e5 !important; /* Highlight khi hover */
            background-color: {colors['bg_card']} !important;
        }}
        /* Chỉnh màu chữ trong uploader */
        [data-testid="stFileUploader"] div, [data-testid="stFileUploader"] span {{
            color: {colors['text_sub']} !important;
        }}
        [data-testid="stFileUploader"] button {{
             display: none; /* Ẩn nút Browse mặc định xấu xí nếu muốn, hoặc style lại */
        }}

        /* --- BUTTONS --- */
        /* Primary Button (Xử lý) */
        button[kind="primary"] {{
            background-color: {colors['btn_primary_bg']} !important;
            color: white !important;
            border: none !important;
            border-radius: 10px !important;
            padding: 0.75rem 1.5rem !important;
            font-weight: 600 !important;
            box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2);
            transition: transform 0.1s;
            height: auto !important;
        }}
        button[kind="primary"]:hover {{
            background-color: #4338ca !important; /* Indigo-700 */
            transform: translateY(-1px);
        }}
        
        /* Secondary Button (Làm mới) */
        button[kind="secondary"] {{
            background-color: transparent !important;
            color: {colors['text_main']} !important;
            border: 1px solid {colors['border']} !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
            height: auto !important;
        }}
        button[kind="secondary"]:hover {{
            border-color: {colors['text_sub']} !important;
            background-color: {colors['bg_app']} !important;
        }}

        /* --- DATAFRAME --- */
        [data-testid="stDataFrame"] {{
            border: 1px solid {colors['border']} !important;
            border-radius: 12px;
            overflow: hidden;
        }}
        
        /* --- TOAST --- */
        div[data-testid="stToast"] {{
            background-color: {colors['bg_card']} !important;
            color: {colors['text_main']} !important;
            border: 1px solid {colors['border']};
            border-radius: 12px;
        }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. LOGIC LÕI (GIỮ NGUYÊN)
# ==============================================================================
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
        is_dieuchinh = _check_tag_exists_recursive(hdon, ["TDieuChinh", "DieuChinh"])
        is_thaythe = _check_tag_exists_recursive(hdon, ["ThayThe"])
        note_str = "Hóa đơn điều chỉnh" if is_dieuchinh else ("Hóa đơn thay thế" if is_thaythe else "Hóa đơn mới")
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
            "GhiChu":   note_str 
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
            ts_raw = str(it["TSuat"]).strip().upper()
            rate_val = 0.0
            ts_display = ts_raw
            if any(x in ts_raw for x in ["KCT", "KKKNT", "KHONG"]): rate_val = 0.0
            elif '%' in ts_raw:
                try: rate_val = float(ts_raw.replace('%', '').replace(',', '.')) / 100
                except: rate_val = 0.0
            elif ts_raw.replace('.', '').isdigit() and ts_raw != "": 
                try:
                    val_check = float(ts_raw)
                    if val_check < 1: rate_val = val_check; ts_display = f"{int(val_check*100)}%"
                    else: rate_val = val_check / 100; ts_display = f"{ts_raw}%"
                except: rate_val = 0.0
            vat = round(tht * rate_val, 0)
            total = tht + vat
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"],
                "Tên hàng": it["THHDVu"],
                "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl, "Đơn giá": dg, "Tiền hàng": int(tht),
                "Thuế suất": ts_display, "Tiền thuế": int(vat), "Cộng tiền": int(total),
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: List[dict]) -> io.BytesIO:
    if not rows: return None
    COLUMN_ORDER = ["Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn", "MST người bán", "Tên người bán", "ĐC người bán", "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá", "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền", "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)"]
    df = pd.DataFrame(rows)
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[existing_cols]
    cols_to_num = ["Số lượng","Đơn giá","Tiền hàng","Tiền thuế","Cộng tiền","Tỷ giá"]
    for c in cols_to_num:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
        workbook = wr.book
        worksheet = wr.sheets['Data']
        header_fmt = workbook.add_format({'bold': True, 'text_wrap': True, 'valign': 'vcenter', 'fg_color': '#D7E4BC', 'border': 1, 'font_size': 10})
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            width = 15
            if "Tên" in value or "ĐC" in value: width = 35
            elif "Ghi chú" in value: width = 20
            elif "Số lượng" in value or "ĐVT" in value: width = 10
            worksheet.set_column(col_num, col_num, width)
    buf.seek(0)
    return buf

# ==============================================================================
# 5. UI LAYOUT & CONTROL BAR
# ==============================================================================

# --- Header & Control ---
col_logo, col_space, col_ctrl = st.columns([4, 4, 2])
with col_ctrl:
    c_lang, c_theme = st.columns(2)
    with c_lang:
        current_lang = st.session_state["lang_code"]
        label_lang = "VN" if current_lang == "vi" else "EN"
        if st.button(label_lang, key="btn_lang", use_container_width=True, type="secondary"):
            st.session_state["lang_code"] = "en" if current_lang == "vi" else "vi"
            st.rerun()
    with c_theme:
        current_theme = st.session_state["theme_mode"]
        label_theme = "☀️" if current_theme == "light" else "🌙"
        if st.button(label_theme, key="btn_theme", use_container_width=True, type="secondary"):
            st.session_state["theme_mode"] = "dark" if current_theme == "light" else "light"
            st.rerun()

st.markdown(f'<h1>Invoice Pipeline <span class="pro-badge">Pro</span></h1>', unsafe_allow_html=True)
st.markdown(f'<p class="subtitle">{T["subtitle"]}</p>', unsafe_allow_html=True)

# --- THE MAIN CARD WRAPPER ---
# Bắt đầu gói toàn bộ nội dung chính vào một cái thẻ Card
st.markdown('<div class="main-card">', unsafe_allow_html=True)

# 1. Upload Area (Nằm trong card)
uploaded_files = st.file_uploader(
    label=T["upload_lbl"], 
    type=ALLOWED_EXTENSIONS, 
    accept_multiple_files=True, 
    key="uploader"
)

# Xử lý file mới
if uploaded_files:
    store = st.session_state["uploads"]
    count_new = 0
    for f in uploaded_files:
        if len(store) >= MAX_FILES_ALLOWED: break
        if f.name not in store:
            if f.size <= MAX_FILE_SIZE_MB * 1024 * 1024:
                store[f.name] = {"data": f.read(), "size": f.size}
                count_new += 1
    if count_new > 0:
        st.toast(T["toast_add"], icon="✨")
        time.sleep(0.5)
        st.rerun()

# 2. Split Layout (Table vs Actions)
if st.session_state["uploads"]:
    # Chia layout: Bên trái (Table) 70% | Bên phải (Actions) 30%
    c_left, c_right = st.columns([2, 1], gap="large")
    
    # --- CỘT TRÁI: TABLE ---
    with c_left:
        st.markdown(f"##### {T['list_header']} <span style='background:#e0e7ff; color:#4338ca; padding:2px 8px; border-radius:10px; font-size:0.8em'>{len(st.session_state['uploads'])}</span>", unsafe_allow_html=True)
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                     for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=200)

    # --- CỘT PHẢI: ACTIONS ---
    with c_right:
        # Spacer để đẩy nút xuống ngang hàng với bảng
        st.write("") 
        st.write("") 
        
        # Nút Xử lý (Primary)
        if st.button(T["btn_process"], type="primary", use_container_width=True):
            with st.status(T["status_process"], expanded=True) as status:
                try:
                    all_rows = []
                    files = st.session_state["uploads"]
                    total = len(files)
                    bar = st.progress(0)
                    
                    for idx, (fname, fcontent) in enumerate(files.items()):
                        inv_data = _parse_invoice_data(fcontent["data"], fname)
                        rows = _rows_from_invoice(inv_data)
                        if rows: all_rows.extend(rows)
                        bar.progress((idx + 1) / total)
                    
                    if all_rows:
                        excel_data = _df_to_xlsx_stream(all_rows)
                        st.session_state["result_bytes"] = excel_data.getvalue()
                        st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        status.update(label=T["status_done"], state="complete", expanded=False)
                    else:
                        status.update(label=T["status_empty"], state="error")
                except Exception as e:
                    st.error(f"{T['status_fail']}: {str(e)}")
                    status.update(label=T["status_fail"], state="error")
        
        # Nút Làm mới (Secondary)
        if st.button(T["btn_clear"], use_container_width=True, type="secondary"):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()

        # Nút Download (Chỉ hiện khi có kết quả)
        if st.session_state.get("result_bytes"):
            st.markdown("---")
            st.download_button(
                label=f"📥 {T['btn_dl']}",
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Result_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

else:
    # Nếu chưa có file, hiển thị placeholder cho đỡ trống
    st.markdown(f"<div style='text-align:center; color:{colors['text_sub']}; padding: 40px;'>📂 {T['status_empty']}</div>", unsafe_allow_html=True)

# Đóng thẻ Main Card
st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown(f'<div style="text-align: center; margin-top: 3rem; color: {colors["text_sub"]}; font-size: 0.8rem;">© 2025 Chuong Minh - Automation Solutions Engineer | Optimized for performance.</div>', unsafe_allow_html=True)
