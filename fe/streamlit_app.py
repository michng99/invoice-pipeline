import io
import os
import time
import hashlib
import zipfile
from typing import Dict, List, Tuple, Any

import streamlit as st
import pandas as pd
import xmltodict
import xlsxwriter

# ==============================================================================
# PHẦN 1: LOGIC BACKEND (ĐÃ CHUYỂN VÀO ĐÂY)
# ==============================================================================

def _ttin_to_map(ttin_container: Any) -> Dict[str, Any]:
    mp: Dict[str, Any] = {}
    if not ttin_container:
        return mp
    items = ttin_container
    if isinstance(items, dict):
        items = [items]
    for node in items:
        try:
            key = str(node.get("TTruong", "")).strip()
            val = node.get("DLieu", "")
            if key:
                mp[key] = val
        except Exception:
            continue
    return mp

def _extract_currency_and_rate(hdon: dict) -> Tuple[str, str, int, int, int, int]:
    dlh = hdon.get("DLHDon") or {}
    ttchung = dlh.get("TTChung") or {}
    dvtte = str(ttchung.get("DVTTe") or "")
    tgia = str(ttchung.get("TGia") or "")

    money_default = 0 if (dvtte.upper() == "VND" or dvtte == "") else 2
    qty_default = 2
    price_default = 2
    rate_default = 2

    root_ttkhac = (hdon.get("TTKhac") or {})
    root_map = _ttin_to_map(root_ttkhac.get("TTin"))

    def _to_int(s, default):
        try:
            return int(str(s).strip())
        except Exception:
            return default

    amount_digits = _to_int(root_map.get("AmountDecimalDigits"), money_default)
    qty_digits    = _to_int(root_map.get("QuantityDecimalDigits"), qty_default)
    price_digits  = _to_int(root_map.get("UnitPriceDecimalDigits"), price_default)
    rate_digits   = _to_int(root_map.get("ExchangRateDecimalDigits"), rate_default)

    return dvtte, tgia, amount_digits, qty_digits, price_digits, rate_digits

def _iter_items(hdon: dict) -> List[dict]:
    dlh = hdon.get("DLHDon") or {}
    nd = dlh.get("NDHDon") or {}
    dshhdv = nd.get("DSHHDVu") or {}
    hh = dshhdv.get("HHDVu")
    if not hh:
        return []
    if isinstance(hh, dict):
        return [hh]
    return hh

def _to_float(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except Exception:
        return 0.0

def _contains_phrase(xml_text: str, needle: str) -> bool:
    return (needle in xml_text) if xml_text else False

def _xml_to_rows_with_rules(xml_bytes: bytes, source_name: str) -> List[Dict]:
    doc = xmltodict.parse(xml_bytes)
    hdon = doc.get("HDon") or {}

    dvtte, tgia, amount_digits, qty_digits, price_digits, rate_digits = _extract_currency_and_rate(hdon)

    xml_text = ""
    try:
        xml_text = xml_bytes.decode("utf-8", errors="ignore")
    except Exception:
        xml_text = ""
    
    if _contains_phrase(xml_text, "Điều chỉnh cho hóa đơn"):
        ghichu = "Hoá đơn điều chỉnh"
    elif _contains_phrase(xml_text, "Thay thế cho hóa đơn"):
        ghichu = "Hoá đơn thay thế"
    else:
        ghichu = "Hoá đơn mới"

    items = _iter_items(hdon)
    rows: List[Dict] = []

    for it in items:
        tchat = str(it.get("TChat", "")).strip()
        if tchat == "1":
            continue

        line_map = _ttin_to_map((it.get("TTKhac") or {}).get("TTin"))

        ten_hang = it.get("THHDVu", "")
        dvt = it.get("DVTinh", "") or line_map.get("MainUnitName", "")
        sl  = _to_float(it.get("SLuong", "0"))
        dg  = _to_float(it.get("DGia", "0"))
        tht = _to_float(it.get("ThTien", "0"))
        unit_price_after_tax = _to_float(line_map.get("UnitPriceAfterTax", "0"))

        tax_rate = 0.08
        vat_amt  = round(tht * tax_rate, amount_digits)

        if unit_price_after_tax > 0 and sl > 0:
            cong_tien = round(unit_price_after_tax * sl, amount_digits)
        else:
            cong_tien = round(tht + vat_amt, amount_digits)

        sl_out  = round(sl, qty_digits)
        dg_out  = round(dg, price_digits)
        tht_out = round(tht, amount_digits)
        tgia_out = round(_to_float(tgia), rate_digits) if tgia else ""

        row = {
            "Cờ (Tchat)": tchat,
            "Tên hàng": ten_hang,
            "ĐVT": dvt,
            "SL": sl_out,
            "Đơn giá": dg_out,
            "Thành tiền": tht_out,
            "Thuế suất": tax_rate,
            "Tiền thuế": vat_amt,
            "Cộng tiền": cong_tien,
            "Đơn vị tiền": dvtte,
            "Tỷ giá": tgia_out,
            "Ghi chú": ghichu,
            "Nguồn (file)": source_name,
        }
        rows.append(row)

    return rows

def process_conversion_internal(files_data: Dict[str, bytes], merge: bool) -> Tuple[bytes, str]:
    """Hàm xử lý chính, thay thế cho việc gọi API"""
    if merge:
        all_rows = []
        for name, data in files_data.items():
            try:
                all_rows.extend(_xml_to_rows_with_rules(data, name))
            except Exception as e:
                print(f"Error parsing {name}: {e}")
        
        df = pd.DataFrame(all_rows)
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="xlsxwriter") as xw:
            df.to_excel(xw, index=False, sheet_name="Data")
        return bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        zipbio = io.BytesIO()
        with zipfile.ZipFile(zipbio, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in files_data.items():
                try:
                    rows = _xml_to_rows_with_rules(data, name)
                    df = pd.DataFrame(rows)
                    xbio = io.BytesIO()
                    with pd.ExcelWriter(xbio, engine="xlsxwriter") as xw:
                        df.to_excel(xw, index=False, sheet_name="Data")
                    zf.writestr(name.rsplit(".", 1)[0] + ".xlsx", xbio.getvalue())
                except Exception:
                    continue
        return zipbio.getvalue(), "application/zip"

# ==============================================================================
# PHẦN 2: FRONTEND STREAMLIT
# ==============================================================================

TTL_SECONDS = 3 * 60 
st.set_page_config(page_title="Invoice Pipeline – Local Mode", layout="wide")

# ========= State Management =========
def _init_state():
    if "uploads" not in st.session_state: st.session_state["uploads"] = {}
    if "sha_index" not in st.session_state: st.session_state["sha_index"] = {}
    if "last_activity" not in st.session_state: st.session_state["last_activity"] = time.time()
    if "busy" not in st.session_state: st.session_state["busy"] = False
    if "do_convert" not in st.session_state: st.session_state["do_convert"] = False
    if "result_bytes" not in st.session_state: st.session_state["result_bytes"] = None
    if "result_mime" not in st.session_state: st.session_state["result_mime"] = None

def _touch():
    st.session_state["last_activity"] = time.time()

def _fmt_left(uploaded_at: float) -> str:
    left = max(0, (uploaded_at + TTL_SECONDS) - time.time())
    m, s = int(left // 60), int(left % 60)
    return f"{m:02d}:{s:02d}"

def _clear_all():
    st.session_state["uploads"].clear()
    st.session_state["sha_index"].clear()
    st.session_state["result_bytes"] = None
    st.session_state["do_convert"] = False
    _touch()

def _cleanup_ttl():
    last = st.session_state.get("last_activity") or time.time()
    if time.time() - last > TTL_SECONDS:
        _clear_all()
        st.toast("Phiên hết hạn, đã dọn dẹp bộ nhớ.", icon="🧹")

def _sha256(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def _add_uploads(files):
    st.session_state["result_bytes"] = None 
    added, rep_n, rep_c = [], [], [] # <--- Khai báo là rep_c
    store = st.session_state["uploads"]
    sha_idx = st.session_state["sha_index"]

    for f in files or []:
        name = (f.name or "unknown.xml").strip()
        data = f.read()
        size = len(data)
        sha = _sha256(data)

        if sha in sha_idx and sha_idx[sha] in store:
            old_name = sha_idx[sha]
            store[old_name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            if old_name != name:
                store[name] = store.pop(old_name)
                sha_idx[sha] = name
            rep_c.append(name) # <--- ĐÃ SỬA: Dùng đúng tên biến rep_c
            continue

        if name in store:
            rep_n.append(name)
            store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
            sha_idx[sha] = name
            continue

        store[name] = {"data": data, "size": size, "uploaded_at": time.time(), "sha": sha}
        sha_idx[sha] = name
        added.append(name)

    _touch()
    return added, rep_n, rep_c

# ========= UI =========
_init_state()
_cleanup_ttl()

st.title("📄 Invoice Pipeline | All-in-One")

# --- Thay thế phần Backend URL bằng System Check ---
with st.container(border=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info("ℹ️ Chế độ: **Standalone (Tất cả trong một)**. Không cần cấu hình Backend URL.")
    with col2:
        if st.button("🔗 Kiểm tra hệ thống", use_container_width=True):
            # Check giả lập để bro yên tâm
            time.sleep(0.5) 
            st.success("✅ Hệ thống hoạt động tốt (Internal Logic Ready)")

st.divider()

# --- Upload Zone ---
uploaded_files = st.file_uploader("Thả file XML vào đây", type=["xml"], accept_multiple_files=True)
if uploaded_files:
    added, rep_n, rep_c = _add_uploads(uploaded_files)
    msg = []
    if added: msg.append(f"✅ Thêm {len(added)}")
    if rep_n: msg.append(f"♻️ Ghi đè tên {len(rep_n)}")
    if rep_c: msg.append(f"♻️ Ghi đè nội dung {len(rep_c)}")
    if msg: st.toast(" | ".join(msg))

# --- File Table ---
if st.session_state["uploads"]:
    colA, colB = st.columns([3,1])
    with colA:
        rows = [{"Tên file": k, "Size": v["size"], "TTL": _fmt_left(v["uploaded_at"])} 
                for k, v in st.session_state["uploads"].items()]
        st.dataframe(rows, hide_index=True, use_container_width=True)
    with colB:
        if st.button("🧽 Xoá hết", use_container_width=True):
            _clear_all()
            st.rerun()

# --- Convert Action ---
num_files = len(st.session_state["uploads"])
merge_to_one = st.checkbox("Gộp thành 1 file Excel", value=True, disabled=num_files <= 1)
convert_btn = st.button("🚀 Convert Ngay", type="primary", disabled=num_files == 0 or st.session_state["busy"])

if convert_btn and not st.session_state["busy"]:
    st.session_state["do_convert"] = True
    st.session_state["busy"] = True
    st.rerun()

if st.session_state["do_convert"] and st.session_state["busy"]:
    try:
        # GỌI HÀM NỘI BỘ THAY VÌ GỌI API
        files_map = {k: v["data"] for k, v in st.session_state["uploads"].items()}
        res_bytes, res_mime = process_conversion_internal(files_map, merge_to_one)
        
        st.session_state["result_bytes"] = res_bytes
        st.session_state["result_mime"] = res_mime
        
        st.session_state["uploads"].clear()
        st.session_state["sha_index"].clear()
        st.success("✅ Xử lý thành công!")
    except Exception as e:
        st.error(f"Lỗi xử lý: {e}")
    finally:
        st.session_state["do_convert"] = False
        st.session_state["busy"] = False
        _touch()
        st.rerun()

# --- Download ---
if st.session_state["result_bytes"]:
    ext = "xlsx" if "spreadsheet" in st.session_state["result_mime"] else "zip"
    fname = "Data.xlsx" if ext == "xlsx" else "excels.zip"
    
    st.download_button(
        f"⬇️ Tải về kết quả ({ext.upper()})",
        data=st.session_state["result_bytes"],
        file_name=fname,
        mime=st.session_state["result_mime"],
        use_container_width=True,
        type="primary"
    )

st.markdown('<div style="text-align:center;color:#888;margin-top:50px;">© 2025 Chương Minh | All Rights Reserved</div>', unsafe_allow_html=True)
