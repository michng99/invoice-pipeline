import io
import time
from typing import List, Any
import streamlit as st
import pandas as pd
import xmltodict

# ==============================================================================
# 1. CẤU HÌNH & GIAO DIỆN (CONFIGURATION & UI THEME)
# ==============================================================================
st.set_page_config(
    page_title="Invoice Pipeline Pro",
    layout="centered", # Chuyển về Centered nhìn cho tập trung, giống app chuyên nghiệp hơn Wide
    initial_sidebar_state="collapsed",
    page_icon="⚡"
)

# Giới hạn cứng
MAX_FILES_ALLOWED = 50       
MAX_FILE_SIZE_MB = 10        
ALLOWED_EXTENSIONS = ["xml"]

# --- CSS CAO CẤP (PREMIUM MINIMALIST STYLE) ---
st.markdown("""
    <style>
        /* Import Font Inter từ Google Fonts cho sang */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #1F2937;
        }

        /* Ẩn Header/Footer mặc định gây rối mắt */
        .stDeployButton, footer, header, [data-testid="stHeader"] { display: none !important; }
        
        /* Chỉnh lại padding cho thoáng */
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 5rem !important;
            max_width: 900px !important;
        }

        /* --- CARD UI STYLE --- */
        /* Tạo khung trắng bao quanh các thành phần chính */
        div[data-testid="stVerticalBlock"] > div:has(div.stMarkdown) {
            background-color: transparent;
        }
        
        /* Style cho File Uploader nhìn xịn hơn */
        [data-testid="stFileUploader"] {
            background-color: #ffffff;
            border: 1px dashed #4F46E5; /* Viền đứt màu tím chủ đạo */
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            transition: all 0.3s ease;
        }
        [data-testid="stFileUploader"]:hover {
            border-color: #4338ca;
            background-color: #fcfcff;
        }
        section[data-testid="stFileUploaderDropzone"] > div > small {
            font-size: 14px; color: #6B7280;
        }

        /* Style cho Nút bấm (Primary Button) */
        button[kind="primary"] {
            background: linear-gradient(135deg, #4F46E5 0%, #4338ca 100%);
            border: none;
            border-radius: 8px;
            color: white;
            padding: 0.75rem 1.5rem;
            font-weight: 600;
            box-shadow: 0 4px 6px rgba(79, 70, 229, 0.3);
            transition: all 0.2s;
            width: 100%;
        }
        button[kind="primary"]:hover {
            box-shadow: 0 6px 10px rgba(79, 70, 229, 0.4);
            transform: translateY(-1px);
        }

        /* Style cho DataFrame (Bảng) */
        [data-testid="stDataFrame"] {
            border: 1px solid #E5E7EB;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }

        /* Custom Title & Header */
        h1 {
            font-weight: 800 !important;
            letter-spacing: -0.025em;
            color: #111827;
            font-size: 2.5rem !important;
            text-align: center;
            margin-bottom: 0.5rem;
        }
        p.subtitle {
            text-align: center;
            color: #6B7280;
            font-size: 1.1rem;
            margin-bottom: 2.5rem;
        }

        /* Footer nhỏ gọn */
        .custom-footer {
            text-align: center;
            font-size: 0.85rem;
            color: #9CA3AF;
            margin-top: 3rem;
            border-top: 1px solid #E5E7EB;
            padding-top: 1rem;
        }
        
        /* Metric Box nhỏ xinh */
        div[data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
            color: #4F46E5 !important;
        }
    </style>
""", unsafe_allow_html=True)

# Khởi tạo Session State
if "uploads" not in st.session_state: st.session_state["uploads"] = {}
if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
if "result_mime" not in st.session_state: st.session_state["result_mime"] = None

# ==============================================================================
# 2. LOGIC LÕI (GIỮ NGUYÊN - KHÔNG ĐỔI)
# ==============================================================================
# (Phần này tui giữ nguyên logic xử lý XML ở phiên bản trước, chỉ rút gọn hiển thị code ở đây để ông dễ nhìn phần UI)
# ... [Paste lại toàn bộ hàm _num, _find_key_recursive, _parse_invoice_data, _rows_from_invoice, _df_to_xlsx_stream y chang phiên bản trước vào đây] ...

# --- ĐỂ TIỆN CHO ÔNG COPY, TUI PASTE LẠI CÁC HÀM LOGIC CẦN THIẾT Ở DƯỚI ĐÂY LUÔN ---
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
# 3. GIAO DIỆN NGƯỜI DÙNG CAO CẤP (PREMIUM FRONTEND UI)
# ==============================================================================

# Header Section (Hero)
st.markdown('<h1>Invoice Pipeline <span style="color:#4F46E5">Pro</span></h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Hệ thống xử lý hóa đơn tự động & tối ưu thuế</p>', unsafe_allow_html=True)

# Container chính (Card Effect)
with st.container():
    # Upload Area
    uploaded_files = st.file_uploader(
        label="Tải lên file XML hóa đơn (Kéo thả vào đây)", 
        type=ALLOWED_EXTENSIONS, 
        accept_multiple_files=True, 
        key="uploader"
    )

    # Logic Accumulate (Cộng dồn file upload)
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
            st.toast(f"Đã thêm {count_new} file mới!", icon="✨")
            time.sleep(0.5)
            st.rerun()

# Dashboard View (Chỉ hiện khi có file)
if st.session_state["uploads"]:
    st.markdown("---")
    
    # 2 Cột: List file và Thống kê nhanh
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.caption(f"📁 **Danh sách file chờ xử lý ({len(st.session_state['uploads'])})**")
        # Tạo dataframe view đơn giản
        data_view = [{"File": k, "Size": f"{v['size']/1024:.1f} KB"} 
                     for k,v in st.session_state["uploads"].items()]
        st.dataframe(
            data_view, 
            use_container_width=True, 
            hide_index=True,
            height=200
        )
    
    with c2:
        # Card Action nhỏ
        with st.container():
            st.write("") # Spacer
            if st.button("🚀 Xử lý & Xuất Excel", type="primary", use_container_width=True):
                with st.status("Đang phân tích dữ liệu...", expanded=True) as status:
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
                            status.update(label="Hoàn tất!", state="complete", expanded=False)
                            st.balloons()
                        else:
                            status.update(label="Không có dữ liệu!", state="error")
                    except Exception as e:
                        st.error(f"Lỗi: {str(e)}")
                        status.update(label="Thất bại", state="error")
            
            # Nút xóa nằm riêng cho đỡ bấm nhầm
            if st.button("Làm mới danh sách", use_container_width=True):
                st.session_state["uploads"].clear()
                st.session_state["result_bytes"] = None
                st.rerun()

    # Download Section (Nổi bật)
    if st.session_state.get("result_bytes"):
        st.markdown("### ✅ Kết quả đã sẵn sàng")
        col_dl, _ = st.columns([1, 1])
        with col_dl:
            st.download_button(
                label="⬇️ TẢI FILE EXCEL NGAY",
                data=st.session_state["result_bytes"],
                file_name=f"Invoice_Export_{int(time.time())}.xlsx",
                mime=st.session_state["result_mime"],
                type="primary",
                use_container_width=True
            )

# Footer tinh tế
st.markdown('<div class="custom-footer">© 2025 Chuong Minh - Automation Solutions | Optimized for Performance.</div>', unsafe_allow_html=True)
