"""Nhóm HQ-MAU-GC — hai loại tệp, nhận sheet theo dòng tiêu đề, ghi đè toàn bộ theo
(loại tệp, năm). Đặc tả 5.1, 10.3, 15.3, 17.2, 18.2, QT-03, QT-10, QT-16, NT-11."""

from __future__ import annotations

import pytest

from .conftest import TEP_GIA_CONG, TEP_MAY_MAU, can_tep_mau, dem, tai_len

NHOM = "HQ-MAU-GC"


def _tai(goi, tep, loai, nam="2026"):
    return tai_len(goi, can_tep_mau(tep), nhom=NHOM, loai=loai, nam=nam)


def _nap(goi, tep, loai, nam="2026"):
    ma = _tai(goi, tep, loai, nam).json()["ma_tep_cho"]
    return goi("POST", f"/uploads/{ma}/confirm").json()


def _gold(ct, bang, nam=2026):
    return dem(ct, f"SELECT count(*) FROM gold.{bang} WHERE is_current AND nam = %s", (nam,))


def test_domains_hai_loai_tep(admin):
    gc = admin("GET", "/domains").json()[1]
    assert gc["code"] == NHOM
    assert gc["phu"] == "HQ-MAU-GC · Lịch may mẫu, Đơn gia công ngoài"
    assert gc["loai_tep"] == [
        {"ma": "LICH_MAY_MAU", "ten": "Lịch may mẫu", "phu": "SAMPLE MAKING SCHEDULE"},
        {"ma": "DON_GIA_CONG", "ten": "Đơn gia công ngoài", "phu": "TOTAL PO SUBCON"}]


def test_bat_buoc_loai_tep(admin):
    r = tai_len(admin, can_tep_mau(TEP_GIA_CONG), nhom=NHOM)
    assert r.status_code == 422 and r.json()["detail"] == "Chưa chọn Loại tệp."


def test_man_xac_nhan_lich_may_mau(admin):
    ma = _tai(admin, TEP_MAY_MAU, "LICH_MAY_MAU").json()["ma_tep_cho"]
    d = admin("GET", f"/uploads/{ma}").json()
    assert d["sheet"] == "30 Sep - OK"
    kt = d["kiem_tra"][0]
    assert (kt["doc"], kt["se_ghi"], kt["trung_bo"], kt["o_trong"], kt["tong"]) == (
        1703, 1703, 0, 28, 4911)
    assert kt["o_trong_chi_tiet"] == [{"cot": "ngay_giao_mau", "so_o": 24},
                                      {"cot": "don_gia", "so_o": 4}]
    assert d["moi"] == ["Lịch may mẫu"] and d["truoc"] is None
    tn = d["theo_nhom"]
    assert (tn["tieu_de"], tn["cot_dau"]) == ("Theo tháng giao mẫu", "Tháng giao mẫu")
    assert [(x["nhom"], x["so_dong"], x["so_luong"]) for x in tn["dong"]] == [
        ("Tháng 6/2026", 405, 795), ("Tháng 7/2026", 359, 907), ("Tháng 8/2026", 307, 988),
        ("Tháng 9/2026", 365, 696), ("Tháng 10/2026", 95, 157),
        ("Chưa có ngày giao mẫu", 172, 1368)]
    assert tn["dong"][-1]["phu"] == "148 ô trống, 24 ô không đọc được ngày"
    assert tn["tong"]["so_dong"] == 1703 and tn["tong"]["so_luong"] == 4911


def test_man_xac_nhan_don_gia_cong(admin):
    ma = _tai(admin, TEP_GIA_CONG, "DON_GIA_CONG").json()["ma_tep_cho"]
    d = admin("GET", f"/uploads/{ma}").json()
    assert d["sheet"] == "Final 09.4"
    assert d["kiem_tra"][0]["doc"] == 50 and d["kiem_tra"][0]["tong"] == 108541
    tn = d["theo_nhom"]
    assert tn["tieu_de"] == "Theo đơn vị gia công"
    assert [(x["nhom"], x["so_dong"], x["so_luong"]) for x in tn["dong"]] == [
        ("NT", 7, 13800), ("TNT", 15, 54125), ("TYLER", 4, 4200), ("NGAN DINH", 3, 2675),
        ("THAO UYEN", 1, 1010), ("Kingstyle - Viet Khanh", 3, 6300),
        ("Kingstyle - Viet Hong", 3, 8820), ("HUNG THINH PHAT", 8, 4765),
        ("PHUONG ANH", 3, 1235), ("OASIS", 3, 11611)]
    assert tn["tong"] == {"so_dong": 50, "so_luong": 108541, "hien_co": None}


def test_chon_nham_loai_tep_bi_tu_choi_dung_1_loi(admin, sach):
    """NT-11: chọn "Lịch may mẫu" nhưng tải tệp TOTAL PO SUBCON."""
    kq = _tai(admin, TEP_GIA_CONG, "LICH_MAY_MAU").json()
    assert kq["status"] == "rejected"
    d = admin("GET", f"/loads/{kq['load_id']}").json()
    assert d["loi"] == [{
        "sheet": "Cả tệp", "vi_tri": "Dòng tiêu đề",
        "van_de": "Không có sheet đang hiện nào có đủ 7 cột của Lịch may mẫu: KHÁCH HÀNG, "
                  "MÃ HÀNG, LOẠI MẪU, SALE, SỐ LƯỢNG, NGÀY GIAO MẪU (QC), GIÁ TIỀN (USD)",
        "cach_xu_ly": "Chọn đúng Loại tệp, hoặc sửa dòng tiêu đề đúng tên cột"}]
    buoc = {b["ma"]: b for b in d["buoc"]}
    assert buoc["A1"]["ket_qua"] == "Đúng định dạng .xlsx, đọc được 9 sheet."
    assert buoc["A2"]["ket_qua"] == ("Không sheet nào có đủ 7 cột của Lịch may mẫu. Cả tệp "
                                     "bị từ chối.")
    assert buoc["A2"]["ket_luan"] == "Sai" and d["sheet"] is None
    assert dem(sach, "SELECT count(*) FROM bronze.fact_may_mau") == 0


def test_nap_lich_may_mau_cac_buoc_va_doi_chieu(admin, sach):
    kq = _nap(admin, TEP_MAY_MAU, "LICH_MAY_MAU")
    assert kq["status"] == "success"
    assert _gold(sach, "fact_may_mau") == 1703
    d = admin("GET", f"/loads/{kq['load_id']}").json()
    assert d["sheet"] == "30 Sep - OK" and d["thang"] is None
    assert d["bang_chinh"] == "fact_may_mau" and d["so_dong_ghi"] == 1703
    buoc = {b["ma"]: b["ket_qua"] for b in d["buoc"]}
    assert buoc["A2"] == "Sheet 30 Sep - OK có đủ 7 cột cần lấy ở dòng tiêu đề 11."
    assert buoc["A3"] == ("Đọc 1.703 dòng (dòng 14–1.716), không có dòng trùng. 28 ô không "
                          "đọc được ngày hoặc số sẽ để trống. Sẽ ghi 1.703 dòng.")
    assert buoc["A4"] == "Lần nạp đầu của Lịch may mẫu năm 2026."
    assert buoc["B4"] == ("Tổng so_luong 4.911 = 4.911; tổng don_gia 77.416,50 = 77.416,50; "
                          "số tháng, khách hàng, nhóm, mã hàng, loại mẫu khớp.")
    assert buoc["B5"] == "Lịch may mẫu năm 2026 (bản 30/09/2026) có hiệu lực từ lúc này."
    assert d["buoc"][8]["ten"] == "Đối chiếu số lượng và các mã"

    the = admin("GET", f"/loads/{kq['load_id']}/reconcile").json()["the"]
    assert [t["ma"] for t in the] == ["so_dong", "tong", "o_trong", "theo_chieu", "ma",
                                      "truoc_sau"]
    tong = {r["o"][0]: r for r in the[1]["dong"]}
    p10 = tong["Ô tổng P10 của tệp (SỐ LƯỢNG)"]
    assert p10["o"][1:] == [141, 4911, 4770] and p10["ket_luan"] == "Ghi nhận"
    assert p10["phu"] == ("Chỉ cộng 90 dòng đang hiện; 1.613 dòng bị bộ lọc Excel ẩn. Portal "
                          "đọc cả dòng ẩn.")
    assert tong["Tổng cột don_gia"]["o"][1:] == [77416.5, 77416.5, 0]
    assert the[2]["so"] == 28 and the[2]["dong"][0]["o"][:3] == ["ngay_giao_mau", "X", 9]
    assert the[3]["tieu_de"] == "Đối chiếu số lượng theo tháng giao mẫu"
    assert the[3]["dong"][0]["mo"]["tim"] == "06/2026"
    assert the[3]["dong"][-1]["o"][0] == "Chưa có ngày giao mẫu"
    assert "mo" not in the[3]["dong"][-1]
    ma = {r["o"][0]: r["o"][1:] for r in the[4]["dong"]}
    assert ma == {"Số tháng giao mẫu": [5, 5], "Số khách hàng (ten_khach)": [118, 118],
                  "Số nhóm kinh doanh (ma_nhom_kd)": [11, 11],
                  "Số mã hàng (ma_mau)": [1254, 1254],
                  "Số loại mẫu (ma_giai_doan_mau)": [187, 187]}
    assert the[5]["tieu_de"] == "Nhóm HQ-MAU-GC năm 2026 trước và sau lần nạp"
    assert [r["o"] for r in the[5]["dong"]] == [
        ["May mẫu chào hàng", "Có", 0, 1703, "Ghi thêm"],
        ["Đơn gia công ngoài", "Không", 0, 0, "Không đụng tới"]]

    khach = admin("GET", f"/loads/{kq['load_id']}/reconcile?the=theo_chieu"
                         "&chia_theo=ten_khach&trang=2&moi=25").json()["the"][0]
    assert khach["so"] == 119 and khach["trang"] == {"trang": 2, "moi": 25, "tong": 119}
    assert len(khach["dong"]) == 25 and khach["tong"][1] == 1703
    thang6 = admin("GET", "/tables/fact_may_mau?nam=2026&tim=06/2026").json()
    assert thang6["tong"] == 405
    assert thang6["dong_tong"][[c["ten"] for c in thang6["cot"]].index("so_luong")] == 795


def test_nap_lai_ghi_de_toan_bo_loai_kia_giu_nguyen(admin, sach):
    """QT-10, NT-11: nạp lại cùng loại tệp, cùng năm thì ghi đè toàn bộ; loại tệp kia
    giữ nguyên."""
    lan_gc = _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG")["load_id"]
    lan1 = _nap(admin, TEP_MAY_MAU, "LICH_MAY_MAU")["load_id"]
    ma = _tai(admin, TEP_MAY_MAU, "LICH_MAY_MAU").json()["ma_tep_cho"]
    d = admin("GET", f"/uploads/{ma}").json()
    assert d["truoc"]["load_id"] == lan1 and d["truoc"]["so_dong"] == 1703
    assert d["ghi_de"] == ["Lịch may mẫu"] and d["moi"] == []
    assert d["giong_het"]["load_id"] == lan1
    assert d["theo_nhom"]["dong"][0]["cach_ghi"] == "Ghi đè"
    lan2 = admin("POST", f"/uploads/{ma}/confirm").json()["load_id"]
    assert _gold(sach, "fact_may_mau") == 1703
    assert _gold(sach, "fact_gia_cong") == 50
    buoc = {b["ma"]: b["ket_qua"] for b in admin("GET", f"/loads/{lan2}").json()["buoc"]}
    assert buoc["A4"] == f"Ghi đè toàn bộ Lịch may mẫu năm 2026 của lần nạp #{lan1}."
    the = admin("GET", f"/loads/{lan2}/reconcile?the=truoc_sau").json()["the"][0]
    assert [r["o"][1:] for r in the["dong"]] == [["Có", 1703, 1703, "Ghi đè"],
                                                  ["Không", 50, 50, "Không đụng tới"]]
    assert [r["ket_luan"] for r in the["dong"]] == ["Đúng", "Giữ nguyên"]
    # Gỡ theo (nhóm, loại tệp): lần mới nhất của Lịch may mẫu gỡ được dù Đơn gia công
    # nạp trước; gỡ xong dữ liệu lần trước được dùng lại.
    assert admin("DELETE", f"/loads/{lan1}").status_code == 409
    assert admin("DELETE", f"/loads/{lan2}").status_code == 204
    assert _gold(sach, "fact_may_mau") == 1703
    assert admin("GET", f"/loads/{lan_gc}").json()["co_the_go"] is True


def test_nam_khac_khong_ghi_de(admin, sach):
    _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG", "2026")
    _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG", "2027")
    assert _gold(sach, "fact_gia_cong", 2026) == 50
    assert _gold(sach, "fact_gia_cong", 2027) == 50


def test_doi_chieu_don_gia_cong(admin):
    kq = _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG")
    buoc = {b["ma"]: b["ket_qua"] for b in admin("GET", f"/loads/{kq['load_id']}").json()
            ["buoc"]}
    assert buoc["A3"] == "Đọc 50 dòng (dòng 3–52), không có dòng trùng. Sẽ ghi 50 dòng."
    assert buoc["B4"] == ("Tổng so_luong 108.541 = 108.541, bằng ô tổng P1 của tệp; số đơn vị "
                          "gia công, khách hàng, mã hàng, đơn hàng, màu khớp.")
    assert buoc["B5"] == "Đơn gia công ngoài năm 2026 có hiệu lực từ lúc này."
    the = admin("GET", f"/loads/{kq['load_id']}/reconcile").json()["the"]
    assert [t["ma"] for t in the] == ["so_dong", "tong", "theo_chieu", "ma", "truoc_sau"]
    assert the[0]["dong"][0]["o"][1] == {"v": 50, "mo": {"sheet": 4}}
    assert the[1]["dong"][1]["o"] == ["Ô tổng P1 của tệp (Order qty)", 108541, 108541, 0]
    assert the[1]["dong"][1]["ket_luan"] == "Đúng"
    assert [r["o"][0] for r in the[2]["dong"][:3]] == ["TNT", "NT", "OASIS"]
    assert {r["o"][0]: r["o"][1] for r in the[3]["dong"]} == {
        "Số đơn vị gia công (ma_don_vi_gc)": 10, "Số khu vực (khu_vuc)": 7,
        "Số khách hàng (ten_khach)": 3, "Số mã hàng (ma_hang)": 21,
        "Số đơn hàng (ma_don_hang)": 28, "Số màu (mau)": 26}


def test_man_du_lieu_hq_mau_gc(admin):
    lan = _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG")["load_id"]
    d = admin("GET", "/tables?nhom=HQ-MAU-GC&nam=2026").json()
    assert [b["bang"] for b in d] == ["fact_may_mau", "fact_gia_cong"]
    assert d[0]["so_dong"] == 0 and d[0]["load_id"] is None
    assert (d[1]["so_dong"], d[1]["load_id"], d[1]["loai_tep"]["phu"]) == (
        50, lan, "TOTAL PO SUBCON")
    ct = admin("GET", "/tables/fact_gia_cong?nam=2026").json()
    cot = {c["ten"]: c for c in ct["cot"]}
    assert cot["ma_dong"]["ten_nbc"] == "Không có trong tệp — để trống"
    assert cot["ma_don_vi_gc"]["bat_buoc"] and cot["so_luong"]["so_do"]
    assert ct["co_ky"] is False and ct["tong"] == 50


@pytest.mark.parametrize("loai", ["LICH_MAY_MAU", "DON_GIA_CONG"])
def test_loc_lich_su_theo_loai_tep(admin, loai):
    _nap(admin, TEP_GIA_CONG, "DON_GIA_CONG")
    dong = admin("GET", f"/loads?nhom=HQ-MAU-GC&loai={loai}").json()["dong"]
    assert len(dong) == (1 if loai == "DON_GIA_CONG" else 0)
