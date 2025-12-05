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
    page_title="Invoice Pipeline Pro | Cloud Dancer Edition",
    layout="centered",
    initial_sidebar_state="collapsed",
    page_icon="☁️"
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
        "list_header": "Danh sách file chờ xử lý",
        "btn_process": "🚀 Xử lý & Xuất Excel",
        "btn_clear": "Làm mới",
        "btn_dl": "⬇️ TẢI FILE KẾT QUẢ",
        "toast_add": "Đã thêm file mới!",
        "status_process": "Đang phân tích dữ liệu...",
        "status_done": "Hoàn tất!",
        "status_empty": "Không có dữ liệu!",
        "status_fail": "Thất bại",
        "col_file": "Tên File", "col_size": "Dung lượng",
        "theme_light": "Sáng", "theme_dark": "Tối" 
    },
    "en": {
        "title": "Invoice Pipeline", "subtitle": "Automated Invoice Processing & Tax Optimization",
        "upload_lbl": "Upload XML Invoices",
        "list_header": "Pending Files",
        "btn_process": "🚀 Process to Excel",
        "btn_clear": "Reset",
        "btn_dl": "⬇️ DOWNLOAD EXCEL",
        "toast_add": "Files added!",
        "status_process": "Processing data...",
        "status_done": "Done!",
        "status_empty": "No data found!",
        "status_fail": "Failed",
        "col_file": "Filename", "col_size": "Size",
        "theme_light": "Light", "theme_dark": "Dark"
    }
}
T = LANG[st.session_state["lang_code"]]

# ==============================================================================
# 3. PANTONE 2026 "CLOUD DANCER" DESIGN SYSTEM
# ==============================================================================
is_dark = st.session_state["theme_mode"] == "dark"

# Bảng màu Cloud Dancer (Pantone 2026)
theme = {
    # NỀN: Light dùng Cloud Dancer (#F0EEE9). Dark dùng Warm Charcoal (#1A1A1A) để hợp tông.
    "bg_color": "#1A1A1A" if is_dark else "#F0EEE9",
    
    # Gradient: Cực nhẹ, mô phỏng ánh sáng tự nhiên trên bề mặt giấy/đá
    "bg_gradient": 
        "radial-gradient(circle at 50% 0%, #2D2D2D 0%, #1A1A1A 100%)" 
        if is_dark else 
        "linear-gradient(180deg, #F0EEE9 0%, #E8E6E1 100%)",
        
    # Kính: Light mode dùng màu trắng thuần khiết để nổi trên nền kem (#F0EEE9)
    "glass_bg": "rgba(30, 30, 30, 0.7)" if is_dark else "rgba(255, 255, 255, 0.65)",
    "glass_border": "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(255, 255, 255, 0.8)",
    
    # Bóng đổ: Mềm mại hơn (Soft Diffusion)
    "glass_shadow": "0 20px 40px -10px rgba(0,0,0,0.5)" if is_dark else "0 10px 30px -5px rgba(166, 160, 149, 0.4)",
    
    # Chữ: Light mode dùng Deep Slate (#2D3748) thay vì đen tuyền để hợp với nền kem
    "text_main": "#F0EEE9" if is_dark else "#2D3748",
    "text_sub": "#A0AEC0" if is_dark else "#5F6C7B",
    
    # Accent: Indigo nhưng trầm hơn, sang trọng hơn
    "accent": "#818cf8" if is_dark else "#4338ca", 
}

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

        /* --- CẤU TRÚC NỀN TẢNG --- */
        .stApp {{
            background-color: {theme['bg_color']};
            background-image: {theme['bg_gradient']};
            background-attachment: fixed;
            font-family: 'Plus Jakarta Sans', sans-serif;
            color: {theme['text_main']};
        }}

        /* --- TYPOGRAPHY (QUIET LUXURY) --- */
        h1, h2, h3, div, span, label, p, .stMarkdown {{
            color: {theme['text_main']} !important;
        }}
        
        h1 {{
            font-weight: 800 !important; 
            font-size: 3.5rem !important;
            letter-spacing: -0.03em;
            text-align: center; 
            margin-bottom: 0.2rem;
            /* Hiệu ứng chữ chìm/nổi tinh tế */
            text-shadow: { "0 2px 10px rgba(0,0,0,0.3)" if is_dark else "0 2px 0px rgba(255,255,255,0.5)" };
        }}
        
        .subtitle {{
            color: {theme['text_sub']} !important;
            text-align: center; 
            font-size: 1.1rem; 
            font-weight: 500;
            margin-bottom: 3.5rem;
            letter-spacing: 0.02em;
        }}
        
        .gradient-text {{
            /* Gradient cho chữ Pro: Mượt mà hơn */
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            -webkit-background-clip: text; 
            -webkit-text-fill-color: transparent;
        }}

        /* Ẩn thành phần thừa */
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        
        .block-container {{
            padding-top: 3rem !important;
            padding-bottom: 4rem !important;
            max_width: 850px !important;
        }}

        /* --- UPLOADER (STYLE GIẤY IN CAO CẤP) --- */
        [data-testid="stFileUploader"] {{
            background: {theme['glass_bg']};
            border: 1px dashed {theme['text_sub']}; /* Viền mảnh tinh tế */
            border-radius: 20px;
            padding: 40px 20px;
            box-shadow: {theme['glass_shadow']};
            backdrop-filter: blur(12px);
            transition: all 0.3s ease;
        }}
        [data-testid="stFileUploader"]:hover {{
            border-color: {theme['accent']};
            transform: translateY(-2px);
        }}
        
        /* Chỉnh màu icon và text trong uploader */
        [data-testid="stFileUploader"] * {{ color: {theme['text_main']} !important; }}
        [data-testid="stFileUploader"] svg {{ 
            fill: {theme['accent']} !important; 
            width: 50px; height: 50px;
        }}
        [data-testid="stFileUploader"] button {{ 
            background-color: transparent !important;
            color: {theme['text_main']} !important; 
            border: 1px solid {theme['text_main']} !important;
            border-radius: 8px;
            font-weight: 600;
        }}

        /* --- BUTTONS SYSTEM --- */
        button {{
            white-space: nowrap !important;
            min-height: 48px !important;
            border-radius: 12px !important;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        }}

        /* Primary Button (Xử lý, Tải xuống) */
        button[kind="primary"] {{
            background: {theme['accent']}; /* Màu đơn sắc (Solid) sang trọng hơn gradient lòe loẹt */
            border: none;
            box-shadow: 0 4px 12px rgba(67, 56, 202, 0.3);
        }}
        button[kind="primary"] * {{
            color: #FFFFFF !important; /* Luôn trắng */
            font-weight: 700 !important;
            font-size: 1rem !important;
            letter-spacing: 0.5px;
        }}
        button[kind="primary"]:hover {{ 
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(67, 56, 202, 0.4);
            filter: brightness(110%);
        }}

        /* Secondary Button (Control, Reset) */
        button[kind="secondary"] {{
            background: { "rgba(255,255,255,0.05)" if is_dark else "rgba(255,255,255,0.5)" };
            border: 1px solid {theme['glass_border']};
            color: {theme['text_main']} !important;
        }}
        button[kind="secondary"]:hover {{
            background: {theme['glass_bg']};
            border-color: {theme['accent']};
            color: {theme['accent']} !important;
        }}
        button[kind="secondary"] * {{ color: inherit !important; }}

        /* --- DATAFRAME (MINIMALIST TABLE) --- */
        [data-testid="stDataFrame"] {{
            background: {theme['glass_bg']};
            border: 1px solid {theme['glass_border']};
            border-radius: 16px;
            padding: 5px;
            box-shadow: {theme['glass_shadow']};
        }}
        [data-testid="stDataFrame"] * {{ 
            color: {theme['text_main']} !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
        }}

        /* --- FOOTER --- */
        .custom-footer {{
            text-align: center; 
            font-size: 0.85rem; 
            color: {theme['text_sub']} !important;
            margin-top: 5rem; 
            opacity: 0.8;
            font-weight: 500;
        }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. LOGIC LÕI
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
# Layout 4-1-3 để đảm bảo không gian
col_logo, col_space, col_ctrl = st.columns([4, 1, 3])

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
st.markdown(f'<h1>{T["title"]} <span class="gradient-text">Pro</span></h1>', unsafe_allow_html=True)
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
    
    c_table, c_actions = st.columns([5, 3])
    
    with c_table:
        st.markdown(f"### **{T['list_header']}** `({len(st.session_state['uploads'])})`")
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                     for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=220)
    
    with c_actions:
        st.markdown("#") 
        
        # Process Button
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
        
        # Clear Button
        if st.button(T["btn_clear"], use_container_width=True, type="secondary"):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()

    # Download Button
    if st.session_state.get("result_bytes"):
        st.markdown("---")
        c_center = st.columns([1, 2, 1])
        with c_center[1]:
            st.download_button(
                label=T["btn_dl"],
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Result_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

# Footer
st.markdown('<div class="custom-footer">© 2025 Chuong Minh - Automation Solutions Engineer | Optimized For Performance</div>', unsafe_allow_html=True)
