import io
import time
from typing import List, Any, Union
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & QUẢN LÝ TRẠNG THÁI (SESSION STATE)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="✨"
)

# Khởi tạo Session State (Chỉ khởi tạo 1 lần)
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "theme_mode" not in st.session_state: st.session_state["theme_mode"] = "light"

# Các hằng số bảo mật và giới hạn hệ thống
MAX_FILES_ALLOWED = 50        
MAX_FILE_SIZE_MB = 10        
ALLOWED_EXTENSIONS = ["xml"]

# ==============================================================================
# 2. BỘ XỬ LÝ LOGIC NGHIỆP VỤ (CORE BUSINESS LOGIC)
# ==============================================================================

def _num(v: Any) -> float:
    """Chuyển đổi chuỗi số (có dấu phẩy/chấm) sang float chuẩn Python"""
    if not v: return 0.0
    try:
        s = str(v).strip()
        # Xử lý trường hợp 1.000,00 hoặc 1,000.00
        if "," in s and "." in s: 
            if s.find(".") < s.find(","): # Dạng 1.000,00 (VN)
                s = s.replace(".", "").replace(",", ".")
            else: # Dạng 1,000.00 (US)
                s = s.replace(",", "")
        elif "," in s: # Dạng 1000,00
            s = s.replace(",", ".")
        return float(s)
    except: return 0.0

def _find_key_recursive(obj: Any, targets: List[str]) -> Any:
    """Đệ quy tìm key trong cấu trúc XML lồng nhau phức tạp"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            # Xử lý namespace XML (ví dụ: hdon:MaSoThue -> lấy MaSoThue)
            clean_key = k.split(":")[-1]
            if clean_key in targets and v is not None: return v
        for v in obj.values():
            found = _find_key_recursive(v, targets)
            if found is not None: return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, targets)
            if found is not None: return found
    return None

def _check_tag_exists_recursive(obj: Any, targets: List[str]) -> bool:
    """Kiểm tra sự tồn tại của thẻ (dùng để check Hóa đơn điều chỉnh/thay thế)"""
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
    """Lấy giá trị an toàn, trả về chuỗi rỗng nếu không tìm thấy"""
    val = _find_key_recursive(obj, targets)
    if val:
        if isinstance(val, (dict, list)): return "" # Không lấy nếu value là object con
        return str(val)
    return ""

def _parse_invoice_data(xml_bytes: bytes, filename: str) -> dict:
    """
    Phân tích file XML thành Dictionary cấu trúc phẳng hơn.
    Xử lý logic: Phát hiện loại hóa đơn, thông tin người bán, danh sách hàng hóa.
    """
    try:
        doc = xmltodict.parse(xml_bytes)
        # Lấy root node bất kể tên là gì (HDon, TDiep, v.v.)
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # Logic xác định loại hóa đơn
        is_dieuchinh = _check_tag_exists_recursive(hdon, ["TDieuChinh", "DieuChinh"])
        is_thaythe = _check_tag_exists_recursive(hdon, ["ThayThe"])
        note_str = "Hóa đơn điều chỉnh" if is_dieuchinh else ("Hóa đơn thay thế" if is_thaythe else "Hóa đơn mới")
        
        # Header Hóa đơn
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
            "GhiChu":   note_str 
        }
        
        # Thông tin Người bán (Seller)
        nban_data = _find_key_recursive(hdon, ["NBan", "Seller", "NguoiBan"]) or hdon
        invoice["NBan"] = {
            "Ten":  _get_value(nban_data, ["Ten", "Name", "TNNBan"]),
            "MST":  _get_value(nban_data, ["MST", "MaSoThue", "MSTNban"]),
            "DChi": _get_value(nban_data, ["DChi", "DiaChi", "DCNBan"]),
        }
        
        # Chi tiết Hàng hóa (Items)
        items = []
        list_container = _find_key_recursive(hdon, ["DSHHDVu", "ListItems"]) or hdon
        raw_items = _find_key_recursive(list_container, ["HHDVu", "Item", "HangHoa"])
        
        if raw_items:
            # Nếu chỉ có 1 sản phẩm, xmltodict trả về dict, cần đưa vào list
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
    except Exception as e:
        # Ghi log lỗi nếu cần thiết (ở đây return rỗng để không crash app)
        return {}

def _rows_from_invoice(inv: dict) -> List[dict]:
    """
    Chuyển đổi dữ liệu hóa đơn thành các dòng cho Excel.
    THỰC HIỆN TÍNH TOÁN: Thành tiền, Tiền thuế, Tổng cộng.
    """
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
            # 1. Parse số liệu cơ bản
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            
            # 2. Logic Thành tiền: Nếu XML không có, tự tính = SL * ĐG
            tht_raw = it["ThTien"]
            if tht_raw:
                tht = _num(tht_raw)
            else:
                tht = sl * dg
            
            # 3. Logic Thuế suất (Phức tạp nhất)
            ts_raw = str(it["TSuat"]).strip().upper()
            rate_val = 0.0
            ts_display = ts_raw
            
            # Xử lý các trường hợp đặc biệt: KCT (Không chịu thuế), KKKNT, KHONG
            if any(x in ts_raw for x in ["KCT", "KKKNT", "KHONG", "K"]): 
                rate_val = 0.0
            elif '%' in ts_raw:
                try: rate_val = float(ts_raw.replace('%', '').replace(',', '.')) / 100
                except: rate_val = 0.0
            elif ts_raw.replace('.', '').isdigit() and ts_raw != "": 
                try:
                    val_check = float(ts_raw)
                    # Nếu < 1 (ví dụ 0.08) -> là tỷ lệ
                    if val_check < 1: 
                        rate_val = val_check
                        ts_display = f"{int(val_check*100)}%"
                    # Nếu > 1 (ví dụ 8) -> là số phần trăm
                    else: 
                        rate_val = val_check / 100
                        ts_display = f"{ts_raw}%"
                except: rate_val = 0.0
            
            # 4. Tính Tiền thuế & Tổng cộng
            vat = round(tht * rate_val, 0)
            total = tht + vat
            
            # 5. Đóng gói dòng dữ liệu
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"],
                "Tên hàng": it["THHDVu"],
                "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl, 
                "Đơn giá": dg, 
                "Tiền hàng": int(tht),
                "Thuế suất": ts_display, 
                "Tiền thuế": int(vat), 
                "Cộng tiền": int(total),
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: List[dict]) -> io.BytesIO:
    """
    Xuất file Excel với định dạng đẹp (Formatting).
    """
    if not rows: return None
    
    # Định nghĩa thứ tự cột chuẩn
    COLUMN_ORDER = [
        "Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn", 
        "MST người bán", "Tên người bán", "ĐC người bán", 
        "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá", 
        "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền", 
        "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)"
    ]
    
    df = pd.DataFrame(rows)
    # Reorder cột, bỏ qua cột nào không có dữ liệu nếu cần
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[existing_cols]
    
    # Ép kiểu số để Excel tính toán được
    cols_to_num = ["Số lượng","Đơn giá","Tiền hàng","Tiền thuế","Cộng tiền","Tỷ giá"]
    for c in cols_to_num:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
        workbook = wr.book
        worksheet = wr.sheets['Data']
        
        # Style Header: Nền xanh nhạt, Chữ đậm, Border
        header_fmt = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'vcenter', 
            'fg_color': '#D7E4BC', 'border': 1, 'font_size': 10
        })
        
        # Set column width thông minh
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
# 3. QUIET LUXURY UI SYSTEM (CLOUD DANCER THEME - FIXED & OPTIMIZED)
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

# --- COLOR PALETTE (Warm Taupe / Cloud Dancer) ---
c_bg_light = "#F7F6F3"     # Cloud Dancer Light
c_glass_light = "rgba(255, 255, 255, 0.65)"
c_glass_dark = "rgba(40, 35, 30, 0.7)"
c_text_light = "#574f3c"   # Warm Grey Text
c_text_dark = "#e0dbd1"    # Light Beige Text
c_accent = "#928463"       # Muted Gold/Taupe
c_border_light = "#e0dbd1"
c_border_dark = "#4e4735"

st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;700;800&display=swap');

        /* NỀN CHÍNH */
        .stApp {{
            background: {'linear-gradient(135deg, #fdfbf7 0%, #e8e6e1 100%)' if not is_dark else 'linear-gradient(135deg, #2c281e 0%, #1a1814 100%)'};
            font-family: 'Manrope', sans-serif;
            color: {c_text_dark if is_dark else c_text_light};
        }}

        /* HEADER & TYPOGRAPHY */
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
        
        /* 1. FILE UPLOADER (Glassmorphism) */
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
        /* Chỉnh màu chữ trong vùng upload */
        [data-testid="stFileUploader"] div, [data-testid="stFileUploader"] span, [data-testid="stFileUploader"] label {{
            color: {c_text_dark if is_dark else c_text_light} !important;
        }}

        /* 2. DATAFRAME (Bảng dữ liệu) */
        [data-testid="stDataFrame"] {{
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid {c_border_dark if is_dark else c_border_light};
            background: {c_glass_dark if is_dark else "rgba(255,255,255,0.4)"};
        }}
        
        /* 3. BUTTONS (Hệ thống nút bấm) */
        /* Nút Primary: Xử lý & Download */
        button[kind="primary"] {{
            background: {c_text_dark if is_dark else "#3a3528"} !important; 
            color: {c_bg_light if is_dark else "#fff"} !important;
            border-radius: 12px !important;
            border: none !important;
            padding: 0.6rem 1.5rem !important;
            box-shadow: 0 4px 15px rgba(58, 53, 40, 0.2);
            font-weight: 700 !important;
        }}
        /* Nút Secondary: Reset & Config */
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

        /* Ẩn các thành phần mặc định Streamlit */
        .stDeployButton, footer, header, [data-testid="stHeader"] {{ display: none !important; }}
        .block-container {{ padding-top: 3rem !important; max-width: 950px !important; }}
    </style>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. LUỒNG THỰC THI CHÍNH (MAIN EXECUTION FLOW)
# ==============================================================================

# --- Header & Toolbar ---
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

# --- Upload Area ---
uploaded_files = st.file_uploader(
    label=T["upload_lbl"],
    type=ALLOWED_EXTENSIONS,
    accept_multiple_files=True,
    label_visibility="visible" 
)

# Xử lý sự kiện Upload (Lazy Loading vào Session State)
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

# --- Main Dashboard ---
if st.session_state["uploads"]:
    st.write("") 
    st.write("") 
    
    # Layout 2 cột: Bảng (2 phần) - Điều khiển (1 phần)
    col_list, col_action = st.columns([2, 1], gap="large")
    
    with col_list:
        st.markdown(f"**{T['list_header']}** ({len(st.session_state['uploads'])})")
        # Hiển thị bảng file đã nạp
        data_view = [{T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} for k,v in st.session_state["uploads"].items()]
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=250)

    with col_action:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True) 
        
        # Nút Xử lý chính (Trigger Logic)
        if st.button(T["btn_process"], type="primary", use_container_width=True):
            # Hiển thị trạng thái Loading
            with st.status(T["status_process"], expanded=True) as status:
                try:
                    all_rows = []
                    files = st.session_state["uploads"]
                    total = len(files)
                    bar = st.progress(0)
                    
                    # Vòng lặp xử lý từng file
                    for idx, (fname, fcontent) in enumerate(files.items()):
                        # 1. Parse XML
                        inv_data = _parse_invoice_data(fcontent["data"], fname)
                        # 2. Tính toán & Flatten data
                        rows = _rows_from_invoice(inv_data)
                        if rows: all_rows.extend(rows)
                        # Cập nhật progress bar
                        bar.progress((idx + 1) / total)
                    
                    if all_rows:
                        # 3. Xuất file Excel vào bộ nhớ đệm (RAM)
                        excel_buffer = _df_to_xlsx_stream(all_rows)
                        st.session_state["result_bytes"] = excel_buffer.getvalue()
                        st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        status.update(label=T["status_done"], state="complete", expanded=False)
                    else:
                        status.update(label=T["status_empty"], state="error")
                except Exception as e:
                    st.error(f"{T['status_fail']}: {str(e)}")
                    status.update(label=T["status_fail"], state="error")
        
        # Nút Reset
        if st.button(T["btn_clear"], type="secondary", use_container_width=True):
            st.session_state["uploads"] = {}
            st.session_state["result_bytes"] = None
            st.rerun()

    # Nút Download (Chỉ hiện khi đã có kết quả xử lý)
    if st.session_state.get("result_bytes"):
        st.markdown("---")
        # Canh giữa nút download
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
    # Màn hình chờ (Empty State)
    st.markdown(f"""
    <div style="text-align:center; padding: 5rem 2rem; color: {c_accent}; opacity: 0.6;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">🍂</div>
        <div style="font-weight: 500;">{T['status_empty']}</div>
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown(f"""
<div style="text-align: center; margin-top: 5rem; font-size: 0.8rem; color: {c_border_dark if is_dark else "#b0a895"};">
    © 2026 Invoice Pipeline Pro | Quiet Luxury Edition | v2.1.0 Stable
</div>
""", unsafe_allow_html=True)
