import sys, os, re, decimal
import xmltodict
import pandas as pd

def num(x):
    if x is None: return None
    s = str(x).strip().replace(',', '')
    try:
        return float(s)
    except:
        return None

def percent_to_decimal(x):
    if not x: return None
    s = str(x).strip()
    if s.endswith('%'):
        try:
            return float(s[:-1]) / 100.0
        except:
            return None
    try:
        return float(s)
    except:
        return None

def ensure_list(x):
    if x is None: return []
    if isinstance(x, list): return x
    return [x]

def main(inp, outp):
    with open(inp, 'rb') as f:
        d = xmltodict.parse(f, force_list=('HHDVu',))

    # lấy “gốc” tuỳ file
    # Cấu trúc thường là HDon/DLHDon/TTChung... & HDon/DLHDon/NDHDon/DSHHDVu/HHDVu
    g = d.get('HDon') or d
    DLHDon = g.get('DLHDon', {})
    TTChung = DLHDon.get('TTChung', {})
    NDHDon = DLHDon.get('NDHDon', {})
    DSHHDVu = NDHDon.get('DSHHDVu', {})
    HHDVu_list = ensure_list(DSHHDVu.get('HHDVu'))

    # Thông tin hóa đơn chung
    mau_so = TTChung.get('KHMSHDon') or '1'
    kh_hd   = TTChung.get('KHHDon')     # ví dụ: C25TLT
    so_hd   = TTChung.get('SHDon')      # ví dụ: 00003000
    ngay_hd = TTChung.get('NLap')       # ví dụ: 2025-10-29
    dvt_te  = TTChung.get('DVTTe') or 'VND'
    ty_gia  = TTChung.get('TGia') or '1'

    # Người bán
    NBan = NDHDon.get('NBan', {})
    mst_ban = NBan.get('MST')
    ten_ban = NBan.get('Ten')
    dc_ban  = NBan.get('DChi')

    rows = []
    for it in HHDVu_list:
        # KHÔNG lọc theo TChat – giữ nguyên tất cả
        tchat = it.get('TChat')
        mh    = (it.get('MHHDVu') or '').strip()
        ten_h = (it.get('THHDVu') or '').strip()
        dvt   = it.get('DVTinh') or ''
        sluong= num(it.get('SLuong'))
        dg    = num(it.get('DGia'))
        th_tien = num(it.get('ThTien'))                 # tiền hàng (chưa thuế)
        thuesuat_txt = it.get('TSuat')                  # ví dụ "8%"
        thuesuat = percent_to_decimal(thuesuat_txt)

        # đào thêm trong TTKhac nếu có VATAmount/Amount… 
        ttk = it.get('TTKhac', {})
        kvs = {}
        for e in ensure_list(ttk.get('TTin')):
            k = (e or {}).get('TTruong')
            v = (e or {}).get('DLieu')
            if k: kvs[k] = v

        amount = num(kvs.get('Amount')) or th_tien
        vat_amt = num(kvs.get('VATAmount') or kvs.get('VATAmountOC'))

        # nếu vẫn thiếu, tự tính từ thuế suất
        if vat_amt is None and amount is not None and thuesuat is not None:
            vat_amt = round(amount * thuesuat)

        cong_tien = None
        if amount is not None and vat_amt is not None:
            cong_tien = amount + vat_amt

        # mapping cột
        rows.append({
            'Mẫu số':            str(mau_so),
            'KH hóa đơn':        kh_hd,
            'Số hóa đơn':        so_hd,
            'ngày hóa đơn':      ngay_hd,
            'ST người bán':      mst_ban,
            'tên người bán':     ten_ban,
            'C người bán':       dc_ban,
            'Mã hàng':           mh,
            'Tên hàng':          ten_h,
            'Đơn vị tính':       dvt,
            'Số lượng':          sluong,
            'Đơn giá':           dg,
            'Tiền hàng':         amount if amount is not None else th_tien,
            'Thuế suất':         thuesuat if thuesuat is not None else thuesuat_txt,
            'Tiền thuế':         vat_amt,
            'Cộng tiền':         cong_tien,
            'Ghi chú':           'Hoá đơn mới',
            'Đơn vị tiền':       dvt_te,
            'Tỷ giá':            num(ty_gia) if num(ty_gia) is not None else ty_gia,
            'Cờ (Tchat)':        tchat
        })

    df = pd.DataFrame(rows, columns=[
        'Mẫu số','KH hóa đơn','Số hóa đơn','ngày hóa đơn','ST người bán','tên người bán','C người bán',
        'Mã hàng','Tên hàng','Đơn vị tính','Số lượng','Đơn giá','Tiền hàng','Thuế suất','Tiền thuế','Cộng tiền',
        'Ghi chú','Đơn vị tiền','Tỷ giá','Cờ (Tchat)'
    ])
    # ghi xlsx
    with pd.ExcelWriter(outp, engine='xlsxwriter') as w:
        df.to_excel(w, index=False, sheet_name='Mẫu số')

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Cách dùng: python offline_convert.py input.xml output.xlsx")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
