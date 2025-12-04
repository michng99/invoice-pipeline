import io
import time
from typing import List, Any, Dict
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH & BẢO MẬT (CONFIGURATION & SECURITY)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline",
    layout="wide",
    initial_sidebar_state="collapsed",
    page_icon="📄"
)

# Giới hạn cứng để chống DDoS và tràn RAM
MAX_FILES_ALLOWED = 50          
MAX_FILE_SIZE_MB = 10           
ALLOWED_EXTENSIONS = ["xml"]

st.markdown("""
    <style>
        /* Tối ưu UI: Ẩn các thành phần thừa */
        .stDeployButton, footer, header, [data-testid="stHeader"] { display: none !important; }
        .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
        
        /* Custom Footer */
        .custom-footer {
            width: 100%; text-align: center; color: #666;
            padding-top: 20px; border-top: 1px solid #ddd;
            font-size: 12px; margin-top: 50px;
        }
        
        /* Tăng trải nghiệm nút bấm */
        button[kind="primary"] { min-height: 45px !important; font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Session State (Quản lý trạng thái ứng dụng)
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "lang_code" not in st.session_state: st.session_state["lang_code"] = "vi"
if "theme" not in st.session_state: st.session_state["theme"] = "light"
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None

# ==============================================================================
# 2. LOGIC LÕI (CORE BUSINESS LOGIC)
# ==============================================================================

def _num(v: Any) -> float:
    """Chuyển đổi an toàn sang số thực (Float). Xử lý dấu phẩy/chấm kiểu VN/US."""
    if not v: return 0.0
    try:
        s = str(v).strip()
        # Nếu có cả dấu chấm và phẩy (vd: 1.000,00), bỏ dấu chấm, thay phẩy bằng chấm
        if "," in s and "." in s: 
            s = s.replace(".", "").replace(",", ".")
        elif "," in s: 
            s = s.replace(",", ".") # Trường hợp 10,5 -> 10.5
        return float(s)
    except: return 0.0

def _find_key_recursive(obj: Any, targets: List[str]) -> Any:
    """Tìm giá trị của key trong dict/list bất chấp độ sâu (Deep Search)."""
    if isinstance(obj, dict):
        # Ưu tiên tìm ở level hiện tại
        for k, v in obj.items():
            clean_k = k.split(":")[-1] # Bỏ namespace (vd: inv:InvoiceData -> InvoiceData)
            if clean_k in targets and v is not None:
                return v
        # Nếu không thấy, đào sâu xuống con
        for v in obj.values():
            found = _find_key_recursive(v, targets)
            if found is not None: return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, targets)
            if found is not None: return found
    return None

def _check_tag_exists_recursive(obj: Any, targets: List[str]) -> bool:
    """
    Kiểm tra sự TỒN TẠI của thẻ (dùng để phát hiện Hóa đơn điều chỉnh/Thay thế).
    Trả về True ngay lập tức nếu tìm thấy key.
    """
    if isinstance(obj, dict):
        for k in obj.keys():
            clean_k = k.split(":")[-1]
            if clean_k in targets:
                return True
        for v in obj.values():
            if _check_tag_exists_recursive(v, targets): return True
    elif isinstance(obj, list):
        for item in obj:
            if _check_tag_exists_recursive(item, targets): return True
    return False

def _get_value(obj: dict, targets: List[str]) -> str:
    """Wrapper an toàn cho hàm tìm kiếm, trả về chuỗi rỗng nếu không thấy."""
    val = _find_key_recursive(obj, targets)
    if val:
        if isinstance(val, (dict, list)): return "" # Không lấy object phức tạp
        return str(val)
    return ""

def _parse_invoice_data(xml_bytes: bytes, filename: str) -> dict:
    """
    Phân tích XML thành Dict, trích xuất thông tin Header và Items.
    Bảo mật: disable_entities=True chặn XXE attack.
    """
    try:
        # 1. Parse XML an toàn
        doc = xmltodict.parse(xml_bytes, disable_entities=True)
        root_key = list(doc.keys())[0]
        hdon = doc[root_key]
        
        # 2. Xác định Loại Hóa Đơn (Logic Ghi Chú)
        # Quét toàn bộ file xem có thẻ TDieuChinh hay ThayThe không
        is_dieuchinh = _check_tag_exists_recursive(hdon, ["TDieuChinh", "DieuChinh"])
        is_thaythe = _check_tag_exists_recursive(hdon, ["ThayThe"])
        
        note_str = "Hóa đơn mới"
        if is_dieuchinh: note_str = "Hóa đơn điều chỉnh"
        elif is_thaythe: note_str = "Hóa đơn thay thế"
        
        # 3. Trích xuất Header Info
        invoice = {
            "KHMSHDon": _get_value(hdon, ["KHMSHDon", "MauSo"]),
            "KHHDon":   _get_value(hdon, ["KHHDon", "KyHieu"]),
            "SHDon":    _get_value(hdon, ["SHDon", "SoHoaDon"]),
            "NLap":     _get_value(hdon, ["NLap", "NgayLap"]),
            "DVTTe":    _get_value(hdon, ["DVTTe", "DonViTienTe"]) or "VND",
            "TGia":     _get_value(hdon, ["TGia", "TyGia"]) or "1",
            "GhiChu":   note_str  # Lưu loại hóa đơn đã xác định
        }
        
        # 4. Trích xuất Seller Info
        nban_data = _find_key_recursive(hdon, ["NBan", "Seller", "NguoiBan"]) or hdon
        invoice["NBan"] = {
            "Ten":  _get_value(nban_data, ["Ten", "Name", "TNNBan"]),
            "MST":  _get_value(nban_data, ["MST", "MaSoThue", "MSTNban"]),
            "DChi": _get_value(nban_data, ["DChi", "DiaChi", "DCNBan"]),
        }
        
        # 5. Trích xuất Items (Hàng hóa)
        items = []
        list_container = _find_key_recursive(hdon, ["DSHHDVu", "ListItems"]) or hdon
        raw_items = _find_key_recursive(list_container, ["HHDVu", "Item", "HangHoa"])
        
        if raw_items:
            if isinstance(raw_items, dict): raw_items = [raw_items] # Chuẩn hóa thành list nếu chỉ có 1 item
            
            for it in raw_items:
                items.append({
                    "MHHDVu":  _get_value(it, ["MHHDVu", "MaHang"]),
                    "THHDVu":  _get_value(it, ["THHDVu", "TenHang"]),
                    "DVTinh":  _get_value(it, ["DVTinh", "DonViTinh"]),
                    "SLuong":  _get_value(it, ["SLuong", "SoLuong"]),
                    "DGia":    _get_value(it, ["DGia", "DonGia"]),
                    "ThTien":  _get_value(it, ["ThTien", "ThanhTien", "ThanhTienTruocThue"]),
                    "TSuat":   _get_value(it, ["TSuat", "ThueSuat", "TSuatGTGT", "TaxRate"]),
                    "TChat":   _get_value(it, ["TChat", "TinhChat"]) # 1: Hàng hóa, 2: KM, 4: Chiết khấu
                })
        
        invoice["Items"] = items
        
        # Cleanup memory ngay lập tức
        del doc 
        return invoice

    except Exception:
        return {}

def _rows_from_invoice(inv: dict) -> List[dict]:
    """Chuyển đổi Dict Invoice thành danh sách Rows để xuất Excel, tính toán lại Thuế."""
    if not inv: return []
    try:
        header_info = {
            "Mẫu số": inv.get("KHMSHDon", ""),
            "KH hóa đơn": inv.get("KHHDon", ""),
            "Số hóa đơn": inv.get("SHDon", ""),
            "Ngày hóa đơn": inv.get("NLap", ""),
            "ST người bán": inv["NBan"].get("MST", ""),
            "Tên người bán": inv["NBan"].get("Ten", ""),
            "ĐC người bán": inv["NBan"].get("DChi", ""),
            "Đơn vị tiền": inv.get("DVTTe", "VND"),
            "Tỷ giá": _num(inv.get("TGia")),
            "Ghi chú": inv.get("GhiChu", "Hóa đơn mới") # Lấy logic phân loại
        }

        items = inv.get("Items", [])
        rows = []
        
        for it in items:
            sl = _num(it["SLuong"])
            dg = _num(it["DGia"])
            
            # Ưu tiên lấy Thành tiền từ XML, nếu không thì tự tính SL * DG
            tht_raw = it["ThTien"]
            tht = _num(tht_raw) if tht_raw else (sl * dg)

            # --- LOGIC TÍNH THUẾ CHUẨN (FIX LỖI CỘT 0 ĐỒNG) ---
            # 1. Parse Thuế suất
            ts_raw = str(it["TSuat"]).strip().upper()
            rate_val = 0.0
            ts_display = ts_raw
            
            # Xử lý các dạng thuế: "8%", "8", "10", "KCT", "KKKNT"
            if "KCT" in ts_raw or "KKKNT" in ts_raw or ts_raw == "":
                rate_val = 0.0
                # ts_display giữ nguyên
            elif '%' in ts_raw:
                try:
                    clean_num = ts_raw.replace('%', '').replace(',', '.')
                    rate_val = float(clean_num) / 100
                except: rate_val = 0.0
            elif ts_raw.replace('.', '').isdigit(): # Case XML ghi "8" nghĩa là 8%
                try:
                    val_check = float(ts_raw)
                    # Nếu số < 1 (vd 0.08) thì là tỷ lệ, nếu > 1 (vd 8) thì chia 100
                    if val_check < 1: rate_val = val_check
                    else: rate_val = val_check / 100
                    ts_display = f"{ts_raw}%"
                except: rate_val = 0.0
            
            # 2. Tính Tiền Thuế = Round(Tiền hàng * Thuế suất)
            vat = round(tht * rate_val, 0)
            
            # 3. Tính Cộng Tiền = Tiền hàng + Tiền thuế
            total = tht + vat
            
            # Tạo row hoàn chỉnh
            row = header_info.copy()
            row.update({
                "Mã hàng": it["MHHDVu"],
                "Tên hàng": it["THHDVu"],
                "Đơn vị tính": it["DVTinh"],
                "Số lượng": sl,
                "Đơn giá": dg,
                "Tiền hàng": int(tht),     # Ép kiểu int cho gọn
                "Thuế suất": ts_display,
                "Tiền thuế": int(vat),     # Tiền thuế tự tính
                "Cộng tiền": int(total),   # Tổng tiền tự tính
                "Cờ (Tchat)": it["TChat"]
            })
            rows.append(row)
            
        return rows
    except Exception: return []

def _df_to_xlsx_stream(rows: List[dict]) -> io.BytesIO:
    """Xuất file Excel với định dạng đẹp."""
    if not rows: return None
    
    # Định nghĩa thứ tự cột mong muốn
    COLUMN_ORDER = [
        "Mẫu số", "KH hóa đơn", "Số hóa đơn", "Ngày hóa đơn",
        "ST người bán", "Tên người bán", "ĐC người bán",
        "Mã hàng", "Tên hàng", "Đơn vị tính", "Số lượng", "Đơn giá",
        "Tiền hàng", "Thuế suất", "Tiền thuế", "Cộng tiền",
        "Ghi chú", "Đơn vị tiền", "Tỷ giá", "Cờ (Tchat)",
    ]
    
    df = pd.DataFrame(rows)
    # Lọc và sắp xếp cột
    existing_cols = [c for c in COLUMN_ORDER if c in df.columns]
    df = df[existing_cols]
    
    # Ép kiểu số học lần cuối để đảm bảo Excel nhận dạng đúng Number
    cols_to_num = ["Số lượng","Đơn giá","Tiền hàng","Tiền thuế","Cộng tiền","Tỷ giá"]
    for c in cols_to_num:
        if c in df.columns: 
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
        df.to_excel(wr, index=False, sheet_name="Data")
        
        # Format cột trong Excel
        workbook = wr.book
        worksheet = wr.sheets['Data']
        
        # Header Format
        header_fmt = workbook.add_format({
            'bold': True, 'text_wrap': True, 'valign': 'vcenter', 
            'fg_color': '#D7E4BC', 'border': 1
        })
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
        
        # Auto width (tương đối)
        worksheet.set_column('A:H', 12)
        worksheet.set_column('I:I', 30) # Tên hàng rộng
        worksheet.set_column('J:T', 12)
        
    buf.seek(0)
    return buf

# ==============================================================================
# 3. GIAO DIỆN NGƯỜI DÙNG (FRONTEND UI)
# ==============================================================================

# Dictionary Ngôn ngữ
LANG = {
    "vi": {
        "title": "Công cụ Xử lý Hóa đơn XML", "settings": "Cài đặt",
        "desc": "Chế độ: **Tự động toàn diện** (Tính thuế & Phân loại hóa đơn)",
        "upload_lbl": "Thả file XML vào đây", 
        "upload_hlp": f"Tối đa {MAX_FILES_ALLOWED} file, {MAX_FILE_SIZE_MB}MB/file",
        "col_file": "Tên file", "col_size": "Dung lượng", 
        "btn_convert": "🚀 Xử lý & Xuất Excel",
        "success": "✅ Xử lý thành công!", "error": "Lỗi xử lý.",
        "btn_dl": "⬇️ Tải file Excel",
        "clear": "Làm mới", "empty": "Danh sách trống"
    },
    "en": {
        "title": "XML Invoice Processor", "settings": "Settings",
        "desc": "Mode: **Full Auto** (Tax Calc & Classification)",
        "upload_lbl": "Drop XML files here", 
        "upload_hlp": f"Max {MAX_FILES_ALLOWED} files, {MAX_FILE_SIZE_MB}MB/file",
        "col_file": "Filename", "col_size": "Size", 
        "btn_convert": "🚀 Process to Excel",
        "success": "✅ Done!", "error": "Error.",
        "btn_dl": "⬇️ Download Excel",
        "clear": "Clear", "empty": "Empty list"
    }
}
T = LANG[st.session_state["lang_code"]]

# Header
c1, c2 = st.columns([6, 1])
with c1: st.title(T["title"])
with c2:
    with st.popover(f"⚙️ {T['settings']}"):
        is_vn = st.session_state["lang_code"] == "vi"
        if st.toggle("Tiếng Việt / English", value=is_vn):
            st.session_state["lang_code"] = "vi"
        else:
            st.session_state["lang_code"] = "en"
        st.rerun()

st.info(T["desc"])

# Upload Area
uploaded_files = st.file_uploader(
    label=T["upload_lbl"], type=ALLOWED_EXTENSIONS, 
    accept_multiple_files=True, help=T["upload_hlp"], key="uploader"
)

# Logic thêm file vào Session (Accumulate)
if uploaded_files:
    store = st.session_state["uploads"]
    count_new = 0
    for f in uploaded_files:
        if len(store) >= MAX_FILES_ALLOWED: break
        if f.name not in store:
            # Validate Size
            if f.size <= MAX_FILE_SIZE_MB * 1024 * 1024:
                store[f.name] = {"data": f.read(), "size": f.size}
                count_new += 1
    
    if count_new > 0:
        st.toast(f"Added {count_new} files!", icon="📥")
        time.sleep(0.5) # Delay nhẹ để UI cập nhật
        st.rerun()

# File List View
if st.session_state["uploads"]:
    c_list, c_act = st.columns([4, 1])
    data_view = [{"#": i+1, T["col_file"]: k, T["col_size"]: f"{v['size']/1024:.1f} KB"} 
                 for i, (k,v) in enumerate(st.session_state["uploads"].items())]
    
    with c_list:
        st.dataframe(data_view, use_container_width=True, hide_index=True, height=200)
    
    with c_act:
        if st.button(f"🗑️ {T['clear']}", use_container_width=True):
            st.session_state["uploads"].clear()
            st.session_state["result_bytes"] = None
            st.rerun()

    # Convert Button
    if st.button(T["btn_convert"], type="primary", use_container_width=True):
        with st.status("Processing...", expanded=True) as status:
            try:
                all_rows = []
                files = st.session_state["uploads"]
                total = len(files)
                bar = st.progress(0)
                
                for idx, (fname, fcontent) in enumerate(files.items()):
                    # 1. Parse
                    inv_data = _parse_invoice_data(fcontent["data"], fname)
                    # 2. Extract & Calculate Rows
                    rows = _rows_from_invoice(inv_data)
                    if rows: all_rows.extend(rows)
                    
                    # 3. Update UI
                    bar.progress((idx + 1) / total)
                    
                    # 4. Clean Memory Explicitly (Quan trọng cho Cloud)
                    del inv_data, rows
                
                # 5. Export
                if all_rows:
                    excel_data = _df_to_xlsx_stream(all_rows)
                    st.session_state["result_bytes"] = excel_data.getvalue()
                    st.session_state["result_mime"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    status.update(label=T["success"], state="complete", expanded=False)
                    st.balloons()
                else:
                    status.update(label="No valid data found!", state="error")
                    
            except Exception as e:
                st.error(f"{T['error']}: {str(e)}")
                status.update(label="Failed", state="error")

# Download Button
if st.session_state.get("result_bytes"):
    st.divider()
    st.download_button(
        label=T["btn_dl"],
        data=st.session_state["result_bytes"],
        file_name=f"Invoice_Export_{int(time.time())}.xlsx",
        mime=st.session_state["result_mime"],
        type="primary",
        use_container_width=True
    )

# Footer
st.markdown('<div class="custom-footer">© 2025 Invoice Processor | Secure & Optimized</div>', unsafe_allow_html=True)
