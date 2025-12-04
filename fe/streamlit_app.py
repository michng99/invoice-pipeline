import io
import time
from typing import List, Any
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH & QUẢN LÝ TRẠNG THÁI
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="centered",
    initial_sidebar_state="collapsed",
    page_icon="⚡"
)

# Khởi tạo Session State
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "theme_mode" not in st.session_state: st.session_state["theme_mode"] = "light"

# Giới hạn
MAX_FILES_ALLOWED = 50       
MAX_FILE_SIZE_MB = 10        
ALLOWED_EXTENSIONS = ["xml"]

# ==============================================================================
# 2. BỘ TỪ ĐIỂN NGÔN NGỮ (RESTORED)
# ==============================================================================
LANG = {
    "vi": {
        "title": "Invoice Pipeline", "subtitle": "Hệ thống xử lý hóa đơn tự động & tối ưu thuế",
        "upload_lbl": "Tải lên file XML hóa đơn (Kéo thả vào đây)",
        "list_header": "Danh sách file chờ xử lý",
        "btn_process": "🚀 Xử lý & Xuất Excel",
        "btn_clear": "Làm mới",
        "btn_dl": "⬇️ TẢI FILE EXCEL NGAY",
        "toast_add": "Đã thêm file mới!",
        "status_process": "Đang phân tích dữ liệu...",
        "status_done": "Hoàn tất!",
        "status_empty": "Không có dữ liệu!",
        "status_fail": "Thất bại",
        "col_file": "Tên File", "col_size": "Dung lượng"
    },
    "en": {
        "title": "Invoice Pipeline", "subtitle": "Automated Invoice Processing & Tax Optimization",
        "upload_lbl": "Upload XML Invoices (Drag & Drop here)",
        "list_header": "Pending Files",
        "btn_process": "🚀 Process to Excel",
        "btn_clear": "Reset",
        "btn_dl": "⬇️ DOWNLOAD EXCEL",
        "toast_add": "Files added!",
        "status_process": "Processing data...",
        "status_done": "Done!",
        "status_empty": "No data found!",
        "status_fail": "Failed",
        "col_file": "Filename", "col_size": "Size"
    }
}
T = LANG[st.session_state["lang_code"]]

# ==============================================================================
# 3. CSS ĐỘNG (DYNAMIC THEME ENGINE)
# ==============================================================================
# Xác định màu sắc dựa trên chế độ đang chọn
is_dark = st.session_state["theme_mode"] == "dark"

theme_cfg = {
    "bg_color": "#111827" if is_dark else "#F3F4F6",        # Nền tổng
    "card_bg":  "#1F2937" if is_dark else "#ffffff",        # Nền thẻ/khung
    "text_main": "#F9FAFB" if is_dark else "#1F2937",       # Chữ chính
    "text_sub":  "#9CA3AF" if is_dark else "#6B7280",       # Chữ phụ
    "border":    "#374151" if is_dark else "#E5E7EB",       # Viền
    "accent":    "#818CF8" if is_dark else "#4F46E5",       # Màu tím chủ đạo
    "accent_hover": "#6366F1" if is_dark else "#4338ca"     # Màu tím khi hover
}

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Inter', sans-serif;
            color: {theme_cfg['text_main']};
            background-color: {theme_cfg['bg_color']};
        }}

        /* Ghi đè nền mặc định của Streamlit */
        .stApp {{
            background-color: {theme_cfg['bg_color']} !important;
        }}

        /* Ẩn Header/Footer mặc định */
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        
        .block-container {{
            padding-top: 2rem !important;
            padding-bottom: 5rem !important;
            max_width: 900px !important;
        }}

        /* --- CARD UI STYLE --- */
        [data-testid="stFileUploader"] {{
            background-color: {theme_cfg['card_bg']};
            border: 1px dashed {theme_cfg['accent']};
            border-radius: 12px;
            padding: 20px;
            transition: all 0.3s ease;
        }}
        [data-testid="stFileUploader"] section > div {{
            color: {theme_cfg['text_sub']} !important;
        }}
        [data-testid="stFileUploader"] small {{
            color: {theme_cfg['text_sub']} !important;
        }}

        /* Style cho Nút bấm Primary */
        button[kind="primary"] {{
            background: linear-gradient(135deg, {theme_cfg['accent']} 0%, {theme_cfg['accent_hover']} 100%);
            border: none; border-radius: 8px; color: white !important;
            padding: 0.75rem 1.5rem; font-weight: 600;
            box-shadow: 0 4px 6px rgba(0,0,0, 0.2);
            transition: all 0.2s;
        }}
        button[kind="primary"]:hover {{ transform: translateY(-1px); }}

        /* Style cho Nút bấm Secondary (Settings) */
        button[kind="secondary"] {{
            background-color: {theme_cfg['card_bg']};
            color: {theme_cfg['text_main']};
            border: 1px solid {theme_cfg['border']};
            border-radius: 20px; /* Nút tròn */
            font-size: 12px;
        }}

        /* Table Style */
        [data-testid="stDataFrame"] {{
            background-color: {theme_cfg['card_bg']};
            border: 1px solid {theme_cfg['border']};
            border-radius: 8px;
        }}

        /* Typography */
        h1 {{
            font-weight: 800 !important; letter-spacing: -0.025em;
            color: {theme_cfg['text_main']}; font-size: 2.5rem !important;
            text-align: center; margin-bottom: 0.5rem;
        }}
        p.subtitle {{
            text-align: center; color: {theme_cfg['text_sub']};
            font-size: 1.1rem; margin-bottom: 1.5rem;
        }}
        .custom-footer {{
            text-align: center; font-size: 0.85rem; color: {theme_cfg['text_sub']};
            margin-top: 3rem; border-top: 1px solid {theme_cfg['border']}; padding-top: 1rem;
        }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. LOGIC LÕI (CORE BUSINESS LOGIC - GIỮ NGUYÊN)
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

# --- Thanh công cụ (Control Bar) ---
c_spacer, c_lang, c_theme = st.columns([6, 1, 1])

with c_lang:
    # Logic đảo ngữ
    current_lang = st.session_state["lang_code"]
    label_lang = "🇻🇳 VN" if current_lang == "vi" else "🇬🇧 EN"
    if st.button(label_lang, key="btn_lang", use_container_width=True):
        st.session_state["lang_code"] = "en" if current_lang == "vi" else "vi"
        st.rerun()

with c_theme:
    # Logic đảo màu
    current_theme = st.session_state["theme_mode"]
    label_theme = "🌙" if current_theme == "light" else "☀️"
    if st.button(label_theme, key="btn_theme", use_container_width=True):
        st.session_state["theme_mode"] = "dark" if current_theme == "light" else "light"
        st.rerun()

# --- Header Section ---
st.markdown(f'<h1>{T["title"]} <span style="color:{theme_cfg["accent"]}">Pro</span></h1>', unsafe_allow_html=True)
st.markdown(f'<p class="subtitle">{T["subtitle"]}</p>', unsafe_allow_html=True)

# --- Main Container ---
with st.container():
    # Upload Area
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

# --- Dashboard ---
if st.session_state["uploads"]:
    st.markdown("---")
    
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.caption(f"📁 **{T['list_header']} ({len(st.session_state['uploads'])})**")
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                     for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=200)
    
    with c2:
        with st.container():
            st.write("") # Spacer
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
            
            if st.button(T["btn_clear"], use_container_width=True):
                st.session_state["uploads"].clear()
                st.session_state["result_bytes"] = None
                st.rerun()

    # Download Section
    if st.session_state.get("result_bytes"):
        st.markdown("### ✅ Result")
        col_dl, _ = st.columns([1, 1])
        with col_dl:
            st.download_button(
                label=T["btn_dl"],
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Export_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

# Footer
st.markdown('<div class="custom-footer">© 2025 Chuong Minh - Automation Solutions | Optimized For Performance .</div>', unsafe_allow_html=True)
