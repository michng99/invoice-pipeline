import io
import time
from typing import List, Any
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG
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
# 2. LOGIC XỬ LÝ (GIỮ NGUYÊN LOGIC GỐC)
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
            
            if any(x in ts_raw for x in ["KCT", "KKKNT", "KHONG"]): 
                rate_val = 0.0
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
                "Mã hàng": it["MHHDVu"], "Tên hàng": it["THHDVu"], "Đơn vị tính": it["DVTinh"],
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
# 3. QUIET LUXURY UI (CLOUD DANCER) - FIXED & BOLD
# ==============================================================================
LANG = {
    "vi": {
        "title": "Invoice Pipeline", "subtitle": "Hệ thống xử lý hóa đơn tự động & tối ưu thuế",
        "upload_lbl": "Thả hóa đơn vào đây để xử lý",
        "list_header": "Hồ sơ chờ xử lý",
        "btn_process": "Xử lý ngay",
        "btn_clear": "Làm mới",
        "btn_dl": "TẢI KẾT QUẢ VỀ MÁY",
        "status_process": "Đang phân tích dữ liệu...", "status_done": "Hoàn tất!", 
        "status_empty": "Chưa có dữ liệu hợp lệ", "status_fail": "Lỗi hệ thống",
        "toast_add": "Đã thêm hồ sơ mới", "col_file": "Tên tập tin", "col_size": "Dung lượng"
    },
    "en": {
        "title": "Invoice Pipeline", "subtitle": "Automated Invoice Processing & Tax Optimization",
        "upload_lbl": "Drop invoices here to process",
        "list_header": "Pending Docs",
        "btn_process": "Process Now",
        "btn_clear": "Reset",
        "btn_dl": "DOWNLOAD RESULT",
        "status_process": "Processing data...", "status_done": "Done!", 
        "status_empty": "No valid data", "status_fail": "System Error",
        "toast_add": "Documents added", "col_file": "Filename", "col_size": "Size"
    }
}
T = LANG[st.session_state["lang_code"]]

is_dark = st.session_state["theme_mode"] == "dark"

# --- COLOR PALETTE DEFINITION ---
c_bg_light = "#F7F6F3"
c_bg_dark = "#1d1a14"       # Biến màu nền tối
c_glass_light = "rgba(255, 255, 255, 0.65)"
c_glass_dark = "rgba(40, 35, 30, 0.7)"
c_text_light = "#574f3c"
c_text_dark = "#e0dbd1"
c_accent = "#928463"
c_border_light = "#e0dbd1"
c_border_dark = "#4e4735"

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&display=swap');

        .stApp {{
            background: {'linear-gradient(135deg, #fdfbf7 0%, #e8e6e1 100%)' if not is_dark else 'linear-gradient(135deg, #2c281e 0%, #1a1814 100%)'};
            font-family: 'Manrope', sans-serif;
            color: {c_text_dark if is_dark else c_text_light};
        }}

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
        
        [data-testid="stFileUploader"] {{
            padding: 24px;
            border-radius: 20px;
            background: {c_glass_dark if is_dark else c_glass_light};
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid {c_border_dark if is_dark else "rgba(255,255,255,0.8)"};
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, {0.2 if is_dark else 0.05});
            transition: all 0.2s ease-in-out;
        }}
        [data-testid="stFileUploader"] section {{
            background-color: transparent !important;
            border: 1px dashed {c_accent} !important;
            opacity: 0.8;
        }}
        [data-testid="stFileUploader"] div, [data-testid="stFileUploader"] span, [data-testid="stFileUploader"] label {{
            color: {c_text_dark if is_dark else c_text_light} !important;
        }}

        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid {c_border_dark if is_dark else c_border_light};
            background: {c_glass_dark if is_dark else "rgba(255,255,255,0.4)"};
        }}
        
        /* --- BUTTON STYLING (FIX: EXTRA BOLD & CONTRAST) --- */
        
        /* 1. Target chung cho Button & Download Button */
        div[data-testid="stButton"] button, 
        div[data-testid="stDownloadButton"] button {{
            font-weight: 800 !important; /* ExtraBold */
            font-family: 'Manrope', sans-serif !important;
            letter-spacing: 0.04em !important;
            font-size: 1rem !important;
            transition: all 0.2s ease-in-out !important;
        }}

        /* 2. Style cho Nút Chính (Primary) */
        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stDownloadButton"] button[kind="primary"] {{
            /* Logic đảo màu tương phản: Dark Mode -> Nền sáng/Chữ tối; Light Mode -> Nền tối/Chữ trắng */
            background: {c_text_dark if is_dark else "#3a3528"} !important; 
            color: {c_bg_dark if is_dark else "#ffffff"} !important; 
            border: none !important;
            border-radius: 12px !important;
            padding: 0.75rem 1.5rem !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
        }}
        
        /* 3. Style cho Nút Phụ (Secondary) */
        div[data-testid="stButton"] button[kind="secondary"] {{
            background: transparent !important;
            color: {c_text_dark if is_dark else c_text_light} !important;
            border: 2px solid {c_border_dark if is_dark else c_border_light} !important; 
            border-radius: 12px !important;
        }}
        
        /* 4. Hover Effect */
        div[data-testid="stButton"] button:hover,
        div[data-testid="stDownloadButton"] button:hover {{
            transform: translateY(-2px);
            filter: brightness(1.1);
            box-shadow: 0 6px 16px rgba(0,0,0,0.2) !important;
        }}

        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        .block-container {{ padding-top: 3rem !important; max-width: 950px !important; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. DASHBOARD & FLOW
# ==============================================================================

c1, c2, c3 = st.columns([6, 1, 1])
with c2:
    if st.button("VN/EN", key="lang", type="secondary", use_container_width=True):
        st.session_state["lang_code"] = "en" if st.session_state["lang_code"] == "vi" else "vi"
        st.rerun()
with c3:
    if st.button("🌗", key="theme", type="secondary", use_container_width=True):
        st.session_state["theme_mode"] = "dark" if st.session_state["theme_mode"] == "light" else "light"
        st.rerun()

st.markdown(f"<h1 style='text-align: center; margin-bottom: 0;'>Invoice Pipeline <span class='pro-badge'>Pro</span></h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align: center; color: {c_accent}; margin-bottom: 3rem;'>{T['subtitle']}</p>", unsafe_allow_html=True)

uploaded_files = st.file_uploader(
    label=T["upload_lbl"],
    type=ALLOWED_EXTENSIONS,
    accept_multiple_files=True,
    label_visibility="visible" 
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

if st.session_state["uploads"]:
    st.write("") 
    st.write("") 
    
    col_list, col_action = st.columns([2, 1], gap="large")
    
    with col_list:
        st.markdown(f"**{T['list_header']}** ({len(st.session_state['uploads'])})")
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=250)

    with col_action:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) 
        
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
                        excel_buffer = _df_to_xlsx_stream(all_rows)
                        st.session_state["result_bytes"] = excel_buffer.getvalue()
                        st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        status.update(label=T["status_done"], state="complete", expanded=False)
                    else:
                        status.update(label=T["status_empty"], state="error")
                except Exception as e:
                    st.error(f"{T['status_fail']}: {str(e)}")
                    status.update(label=T["status_fail"], state="error")
        
        if st.button(T["btn_clear"], type="secondary", use_container_width=True):
            st.session_state["uploads"] = {}
            st.session_state["result_bytes"] = None
            st.rerun()

    if st.session_state.get("result_bytes"):
        st.markdown("---")
        c_dl_1, c_dl_2, c_dl_3 = st.columns([1, 2, 1])
        with c_dl_2:
            st.download_button(
                label=f"📥 {T['btn_dl']}",
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Result_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

else:
    st.markdown(f"""
    <div style="text-align:center; padding: 5rem 2rem; color: {c_accent}; opacity: 0.6;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🍂</div>
        <div style="font-weight: 500;">{T['status_empty']}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div style="text-align: center; margin-top: 5rem; font-size: 0.8rem; color: {c_border_dark if is_dark else "#b0a895"};">
    © 2026 Invoice Pipeline Pro | Quiet Luxury Edition | v3.0 Final Stable
</div>
""", unsafe_allow_html=True)
