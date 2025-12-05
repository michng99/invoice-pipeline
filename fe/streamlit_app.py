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
    layout="centered",
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
        "upload_lbl": "Tải lên file XML hóa đơn",
        "list_header": "Hồ sơ chờ xử lý", # Đổi từ ngữ cho sang hơn
        "btn_process": "Xử lý & Xuất Excel",
        "btn_clear": "Làm mới",
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
        "upload_lbl": "Upload XML Invoices",
        "list_header": "Pending Documents",
        "btn_process": "Process & Export",
        "btn_clear": "Reset Pipeline",
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
# 3. QUIET LUXURY CSS ENGINE (2026 TREND)
# ==============================================================================
is_dark = st.session_state["theme_mode"] == "dark"

theme = {
    # Nền: Light = Cloud Dancer Gradient | Dark = Deep Rich Graphite (Không dùng đen tuyền)
    "bg_gradient": 
        "radial-gradient(circle at 50% 0%, #3a3a3c 0%, #1c1c1e 100%)" 
        if is_dark else 
        "radial-gradient(circle at 50% 0%, #F9F7F5 0%, #F0EEE9 100%)", # Hiệu ứng giấy lụa
    
    # Kính: Tinh tế hơn, ít đục hơn
    "glass_bg": "rgba(44, 44, 46, 0.6)" if is_dark else "rgba(255, 255, 255, 0.5)",
    "glass_border": "rgba(255, 255, 255, 0.1)" if is_dark else "rgba(255, 255, 255, 0.6)",
    "glass_shadow": "0 12px 40px rgba(0,0,0,0.4)" if is_dark else "0 12px 40px rgba(166, 160, 149, 0.2)",
    
    # Text: Light = Warm Charcoal (#323232) | Dark = Cloud Dancer (#F0EEE9)
    "text_main": "#F0EEE9" if is_dark else "#323232",
    "text_sub": "#98989d" if is_dark else "#6e6e73",
    
    # Primary Button Color: ĐỐI LẬP SANG TRỌNG
    # Light Mode: Nút màu tối trên nền sáng (Rất thời trang)
    # Dark Mode: Nút màu sáng trên nền tối
    "btn_bg": "#F0EEE9" if is_dark else "#2C2C2E", 
    "btn_text": "#1c1c1e" if is_dark else "#F0EEE9",
    "btn_border": "transparent",
}

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        /* --- RESET & BACKGROUND --- */
        .stApp {{
            background: {theme['bg_gradient']};
            background-attachment: fixed;
            font-family: 'Manrope', sans-serif; /* Font hiện đại, bo tròn nhẹ */
            color: {theme['text_main']};
        }}
        
        /* Ẩn Header mặc định */
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        
        .block-container {{
            padding-top: 3rem !important;
            padding-bottom: 5rem !important;
            max_width: 900px !important;
        }}

        /* --- TYPOGRAPHY --- */
        h1, h2, h3, p, div, span, label, .stMarkdown, .stDataFrame {{
            color: {theme['text_main']} !important;
        }}
        
        h1 {{
            font-weight: 800 !important; 
            font-size: 3rem !important;
            letter-spacing: -0.04em; /* Chữ xích lại gần nhau cho hiện đại */
            text-align: center;
            margin-bottom: 0.5rem;
        }}
        
        /* Hiệu ứng Gradient Text nhẹ cho chữ Pro */
        .pro-badge {{
            background: { "linear-gradient(90deg, #F0EEE9, #bfbfbf)" if is_dark else "linear-gradient(90deg, #2C2C2E, #555)" };
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-style: italic;
        }}

        .subtitle {{
            text-align: center; color: {theme['text_sub']} !important;
            font-size: 1.05rem; font-weight: 500; margin-bottom: 3.5rem;
        }}

        /* --- UPLOADER (GLASS CARD) --- */
        [data-testid="stFileUploader"] {{
            background: {theme['glass_bg']};
            border: 1px solid {theme['glass_border']};
            border-radius: 24px; /* Bo góc lớn */
            padding: 30px;
            box-shadow: {theme['glass_shadow']};
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
        }}
        [data-testid="stFileUploader"] section {{ padding: 0 !important; }}
        
        /* FIX LỖI ICON X QUÁ TO */
        [data-testid="stFileUploader"] button[kind="secondary"] {{
            width: 32px !important; 
            height: 32px !important;
            padding: 0 !important;
            border: none !important;
            background: transparent !important;
        }}
        [data-testid="stFileUploader"] svg {{ 
            width: 18px !important; height: 18px !important; /* Thu nhỏ icon X */
            fill: {theme['text_sub']} !important;
        }}
        /* Icon Cloud Upload */
        [data-testid="stFileUploader"] > section > div > div > svg {{
            width: 40px !important; height: 40px !important;
            fill: {theme['text_main']} !important;
            opacity: 0.8;
        }}
        
        /* --- BUTTONS SYSTEM (LUXURY FLAT) --- */
        button {{
            white-space: nowrap !important;
            transition: all 0.3s cubic-bezier(0.25, 1, 0.5, 1) !important;
        }}

        /* PRIMARY BUTTON (Xử lý, Tải xuống) */
        button[kind="primary"] {{
            background: {theme['btn_bg']} !important;
            color: {theme['btn_text']} !important;
            border: none !important;
            border-radius: 14px !important;
            padding: 0.85rem 1.8rem !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        /* Ép màu chữ bên trong Primary luôn đúng tương phản */
        button[kind="primary"] * {{ color: {theme['btn_text']} !important; }}
        
        button[kind="primary"]:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }}

        /* SECONDARY BUTTON (Control, Reset) */
        button[kind="secondary"] {{
            background: transparent !important;
            border: 1px solid {theme['glass_border']} !important;
            color: {theme['text_main']} !important;
            border-radius: 12px !important;
            font-weight: 600 !important;
        }}
        button[kind="secondary"]:hover {{
            background: {theme['glass_bg']} !important;
            border-color: {theme['text_main']} !important;
        }}

        /* --- DATAFRAME (MINIMAL) --- */
        [data-testid="stDataFrame"] {{
            background: transparent !important;
            border: 1px solid {theme['glass_border']} !important;
            border-radius: 12px;
        }}
        
        /* --- FOOTER --- */
        .custom-footer {{
            text-align: center; font-size: 0.8rem; 
            color: {theme['text_sub']} !important;
            margin-top: 5rem; padding-top: 2rem;
            border-top: 1px solid {theme['glass_border']};
            opacity: 0.6;
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

# --- Control Bar ---
# Layout 6-2 để đẩy nút sang phải nhưng vẫn thoáng
col_logo, col_ctrl = st.columns([6, 2])

with col_ctrl:
    c_lang, c_theme = st.columns(2)
    
    # Lang Button
    current_lang = st.session_state["lang_code"]
    label_lang = "🇻🇳 VN" if current_lang == "vi" else "🇺🇸 EN"
    with c_lang:
        if st.button(label_lang, key="btn_lang", use_container_width=True, type="secondary"):
            st.session_state["lang_code"] = "en" if current_lang == "vi" else "vi"
            st.rerun()
            
    # Theme Button
    current_theme = st.session_state["theme_mode"]
    theme_text = T["theme_light"] if current_theme == "light" else T["theme_dark"]
    label_theme = f"☀️ {theme_text}" if current_theme == "light" else f"🌙 {theme_text}"
    with c_theme:
        if st.button(label_theme, key="btn_theme", use_container_width=True, type="secondary"):
            st.session_state["theme_mode"] = "dark" if current_theme == "light" else "light"
            st.rerun()

# --- Hero Section ---
st.markdown("---") 
st.markdown(f'<h1>Invoice Pipeline <span class="pro-badge">Pro</span></h1>', unsafe_allow_html=True)
st.markdown(f'<p class="subtitle">{T["subtitle"]}</p>', unsafe_allow_html=True)

# --- Main Container ---
uploaded_files = st.file_uploader(
    label=T["upload_lbl"], 
    type=ALLOWED_EXTENSIONS, 
    accept_multiple_files=True, 
    key="uploader"
)

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

# --- Dashboard View ---
if st.session_state["uploads"]:
    st.markdown("##") 
    
    # Chia Layout 7:4 để bảng dữ liệu rộng rãi, Action không bị ép
    c_table, c_actions = st.columns([7, 4])
    
    with c_table:
        st.markdown(f"### **{T['list_header']}** `({len(st.session_state['uploads'])})`")
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                     for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=250)
    
    with c_actions:
        # Thêm Spacer để đẩy nút xuống ngang tầm với hàng đầu tiên của bảng
        st.markdown("<div style='height: 48px'></div>", unsafe_allow_html=True)
        
        # Nút Xử lý (SANG TRỌNG: Màu tối trên nền sáng / Màu sáng trên nền tối)
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
                        del inv_data, rows
                    
                    if all_rows:
                        excel_data = _df_to_xlsx_stream(all_rows)
                        st.session_state["result_bytes"] = excel_data.getvalue()
                        st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        status.update(label=T["status_done"], state="complete", expanded=False)
                        st.balloons()
                    else:
                        status.update(label=T["status_empty"], state="error")
                except Exception as e:
                    st.error(f"{T['status_fail']}: {str(e)}")
                    status.update(label=T["status_fail"], state="error")
        
        # Thêm khoảng cách giữa 2 nút
        st.markdown("<div style='height: 10px'></div>", unsafe_allow_html=True)
        
        # Nút Làm mới
        if st.button(T["btn_clear"], use_container_width=True, type="secondary"):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()

    # Download Button (Xuất hiện nổi bật riêng biệt ở dưới)
    if st.session_state.get("result_bytes"):
        st.markdown("---")
        # Layout 3 cột để căn giữa nút download
        c_left, c_dl, c_right = st.columns([1, 2, 1])
        with c_dl:
            st.download_button(
                label=f"📥 {T['btn_dl']}",
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Result_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

# Footer
st.markdown('<div class="custom-footer">© 2026 Invoice Pipeline Pro | Quiet Luxury Edition</div>', unsafe_allow_html=True)
