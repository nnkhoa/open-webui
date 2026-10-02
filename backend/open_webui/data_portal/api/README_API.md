# API JSON của Data Portal

Hợp đồng thực tế của `open_webui/data_portal/api` — đúng với mã nguồn và bộ kiểm thử `open_webui/test/data_portal/`.
Đặc tả gốc: `DacTa_GiaoDien_DataPortal_OpenWebUI.md` (mục 8.3, 9, 15–20).

## 1. Quy ước chung

- Ứng dụng FastAPI con, chạy trong process Open WebUI, gắn ở `/api/v1/data-portal` (`open_webui/main.py`). Đường dẫn ở mục 3 viết tương đối: `GET /loads` là `GET /api/v1/data-portal/loads`.
- JSON UTF-8. Số trả dạng số: số nguyên là `int`, số có phần lẻ là `float`. Thời gian theo ISO 8601 (`2026-10-02T04:30:12.345+00:00`). Giao diện tự định dạng theo mục 13.3.
- Phân trang: `trang` (từ 1), `moi` ∈ {25, 50, 100}. Giá trị khác trả 422.
- Lỗi: mã HTTP 4xx/5xx, thân `{"detail": "<câu tiếng Việt>"}`.

| Mã | Khi nào |
|---|---|
| 401 | Chưa đăng nhập Open WebUI hoặc phiên hết hạn |
| 403 | Vai trò không phải `admin` / `data_uploader` ("Bạn không có quyền vào Data Portal. Liên hệ Admin nếu cần nạp dữ liệu."); Data Loader gọi đường dẫn chỉ Admin ("Bạn không có quyền thực hiện thao tác này") |
| 404 | Không tìm thấy (lần nạp, tệp chờ, bảng, sheet, đường dẫn) |
| 409 | Gỡ lần nạp không phải mới nhất (QT-17) |
| 422 | Dữ liệu gửi lên sai. Riêng cấu hình database có thêm `theo_o: {host, port, database, username}` — lỗi theo từng ô |
| 503 | Data Portal đang khởi động; chưa cấu hình / mất kết nối database; `detail` là lý do |
| 500 | Lỗi ngoài dự kiến; thân có thêm `ma_yeu_cau` để tra nhật ký |

Đường dẫn không tồn tại vẫn kiểm danh tính trước (401/403) rồi mới trả 404.

## 2. Danh tính (mục 8.3)

- Người gọi là tài khoản Open WebUI đang đăng nhập (`get_verified_user`, token Bearer như mọi API khác của Open WebUI).
- Cột Người nạp và nhật ký `ctl_audit_event` ghi tên hiển thị của tài khoản; `user_id` là mã người dùng Open WebUI.
- Quyền theo cột Quyền ở 9.2: **A** = chỉ `admin`; **A, L** = `admin` và `data_uploader`.

## 3. Danh sách API

| Phương thức, đường dẫn | Quyền | Mục |
|---|---|---|
| `GET /domains` | A, L | 3.1 |
| `POST /uploads` | A, L | 3.2 |
| `GET /uploads/{ma_tep_cho}` | A, L | 3.3 |
| `DELETE /uploads/{ma_tep_cho}` | A, L | 3.4 |
| `POST /uploads/{ma_tep_cho}/confirm` | A, L | 3.5 |
| `GET /loads` | A, L | 3.6 |
| `GET /loads/{id}` | A, L | 3.7 |
| `GET /loads/{id}/reconcile` | A, L | 3.8 |
| `GET /loads/{id}/errors.csv` | A, L | 3.9 |
| `GET /loads/{id}/file` | A, L | 3.10 |
| `GET /loads/{id}/file/sheets` | A, L | 3.10 |
| `GET /loads/{id}/file/sheets/{n}` | A, L | 3.10 |
| `DELETE /loads/{id}` | A | 3.11 |
| `GET /tables` | A, L | 3.12 |
| `GET /tables/{bang}` | A, L | 3.13 |
| `GET /tables/{bang}/export.xlsx` | A, L | 3.14 |
| `GET /db-config` · `POST /db-config/test` · `PUT /db-config` · `DELETE /db-config` | A | 3.15 |

### 3.1 `GET /domains`

```json
[
  {"code": "HQKD", "name": "Hiệu quả kinh doanh theo nhóm và khách hàng",
   "phu": "HQKD · Báo cáo hiệu quả từng khách hàng",
   "loai_tep": [{"ma": "BAO_CAO_HQKH", "ten": "Báo cáo hiệu quả từng khách hàng", "phu": null}]},
  {"code": "HQ-MAU-GC", "name": "Hiệu quả may mẫu chào hàng, gia công ngoài",
   "phu": "HQ-MAU-GC · Lịch may mẫu, Đơn gia công ngoài",
   "loai_tep": [{"ma": "LICH_MAY_MAU", "ten": "Lịch may mẫu", "phu": "SAMPLE MAKING SCHEDULE"},
                {"ma": "DON_GIA_CONG", "ten": "Đơn gia công ngoài", "phu": "TOTAL PO SUBCON"}]}
]
```

`loai_tep` rỗng ⇒ nhóm chưa khai loại tệp (màn trống 15.6). Danh sách năm cố định 2025–2031 (QT-02), giao diện tự có.

### 3.2 `POST /uploads` — Kiểm tra tệp (chỉ đọc, QT-07)

`multipart/form-data`: `nhom` (mã nhóm), `nam` (2025–2031), `loai` (mã loại tệp — bắt buộc khi nhóm có nhiều loại tệp, bỏ trống được khi nhóm chỉ có một), `file`.

- Hợp lệ → `200 {"ma_tep_cho": "<32 ký tự hex>"}`. Database không đổi.
- Có lỗi cấu trúc / dữ liệu → `200 {"load_id": 12, "status": "rejected"}`. Đã tạo lần nạp "Bị từ chối", lưu tệp và danh sách lỗi.
- 422 với `detail`: "Chưa chọn Nhóm thông tin." · "Nhóm thông tin không hợp lệ." · "Chưa chọn Năm dữ liệu." · "Năm dữ liệu phải từ 2025 đến 2031." · "Chưa chọn Loại tệp." · "Loại tệp không hợp lệ." · "Chưa chọn tệp." · "Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu lại đúng định dạng." (đuôi khác `.xlsx`, hoặc tệp hỏng) · "Nhóm {tên} chưa có thông tin: chưa khai báo loại tệp nên chưa nạp, chưa có lịch sử và chưa có dữ liệu."

### 3.3 `GET /uploads/{ma_tep_cho}` — màn Xác nhận

Chỉ người đã tải lên mới xem / huỷ / xác nhận được; người khác nhận 404 như tệp không có. Phần "so với dữ liệu đang có" tính lại lúc hỏi.

```json
{
  "ma_tep_cho": "…", "nhom": "HQKD", "nam": 2026,
  "loai": {"ma": "BAO_CAO_HQKH", "ten": "Báo cáo hiệu quả từng khách hàng", "phu": null},
  "ten_tep": "FORM MAU - HIEU QUA TUNG KHACH HANG T1-T7.26.xlsx", "size_bytes": 304901,
  "sheet": null,
  "kiem_tra": [
    {"bang": "fact_ket_qua_kd", "ten_bang": "Kết quả kinh doanh", "sheet": "TỔNG HỢP",
     "doc": 348, "thieu_bat_buoc": 0, "trung_bo": 0, "o_trong": 0, "o_trong_chi_tiet": [],
     "se_ghi": 348, "tong": 3193114446744.495, "ket_luan": "Hợp lệ"}
  ],
  "giong_het": null,
  "ghi_de": [], "moi": [1, 2, 3, 4, 5, 6, 7], "truoc": null,
  "theo_nhom": {
    "tieu_de": "Theo tháng", "cot_dau": "Tháng",
    "dong": [{"nhom": "Tháng 1/2026", "du_lieu": "Kết quả kinh doanh", "so_dong": 50,
              "so_cot": 15, "so_cot_tong": 15, "hien_co": null, "cach_ghi": "Ghi thêm"}],
    "tong": {"so_dong": 7308}
  }
}
```

- `kiem_tra` theo thứ tự hiển thị bảng. `tong`: tổng tiền (HQKD), tổng số lượng (HQ-MAU-GC), `null` với danh mục. `o_trong` = số ô không đổi được kiểu, sẽ để trống (QT-11); `o_trong_chi_tiet: [{cot, so_o}]`. `ket_luan`: "Hợp lệ".
- `giong_het` (QT-15): `{load_id, luc, nguoi}` — lần nạp đang có hiệu lực cùng nhóm, năm, loại tệp có cùng mã băm tệp.
- `hien_co` (mỗi dòng): `null` hoặc `{so_dong, load_id, luc, nguoi}` — dữ liệu đang có của nhóm dòng đó trong năm đã chọn. `cach_ghi`: "Ghi đè" / "Ghi thêm".
- **HQKD**: `ghi_de` / `moi` là số tháng; `truoc: null`; `theo_nhom` mỗi tháng 2 dòng (`du_lieu` "Kết quả kinh doanh" / "Chi phí"), tên tháng lặp ở cả hai dòng (giao diện tự ẩn ở dòng thứ hai).
- **HQ-MAU-GC**: `sheet` = sheet lấy dữ liệu ("30 Sep - OK", "Final 09.4"); `truoc`: `null` hoặc `{load_id, so_dong, luc, nguoi}` — dữ liệu đang có hiệu lực của cùng loại tệp, năm (sẽ bị ghi đè toàn bộ); `ghi_de` / `moi` = `["Lịch may mẫu"]` theo đó.
  - Lịch may mẫu: `theo_nhom.tieu_de` "Theo tháng giao mẫu", `cot_dau` "Tháng giao mẫu"; dòng `{nhom: "Tháng 6/2026", so_dong, so_luong, hien_co, cach_ghi}`, dòng cuối `{nhom: "Chưa có ngày giao mẫu", phu: "148 ô trống, 24 ô không đọc được ngày", …}`.
  - Đơn gia công ngoài: "Theo đơn vị gia công" / "Đơn vị gia công", thứ tự như trong tệp.
  - `tong`: `{so_dong, so_luong, hien_co}` (`hien_co` = số dòng đang có, hoặc `null`).

### 3.4 `DELETE /uploads/{ma_tep_cho}` — "Huỷ, không nạp"

`204`, không thân. Tệp chờ bị xoá, database không đổi. Không có / của người khác → 404.

### 3.5 `POST /uploads/{ma_tep_cho}/confirm` — "Xác nhận thêm mới dữ liệu"

Ghi 3 lớp trong một giao dịch dưới khoá (nhóm, loại tệp), đối chiếu, lệch thì huỷ cả lần (QT-12, QT-13).

`200 {"load_id": 7, "status": "success" | "mismatch" | "rejected"}`.
Tệp chờ không còn (đã xác nhận, đã huỷ, quá 24 giờ) → `404 {"detail": "Tệp này đã được nạp hoặc đã quá hạn chờ xác nhận. Hãy xem Lịch sử nạp, hoặc chọn lại tệp."}`.

### 3.6 `GET /loads?nhom&nam&loai&trang_thai&nguoi&tim&trang&moi`

`nhom` bắt buộc. `loai` = mã loại tệp; `trang_thai` ∈ `success|rejected|mismatch|rolled_back`; `nguoi` = tên người nạp (đúng như trong `nguoi_nap`); `tim` khớp mã (có thể kèm `#`) hoặc tên tệp. Mặc định `moi=25`. Mới nhất ở trên.

```json
{"tong": 2, "nguoi_nap": ["admin", "loader"],
 "dong": [{"id": 2, "ten_tep": "…xlsx", "nam": 2026, "loai": {"ma": "BAO_CAO_HQKH", "ten": "…"},
           "nguoi": "admin", "luc": "2026-10-02T…", "so_dong": 7561, "status": "success"}]}
```

`so_dong` = số dòng đọc được; lần nạp không thành công là 0.

### 3.7 `GET /loads/{id}`

```json
{
  "id": 7, "status": "success", "nhom": "HQKD", "nam": 2026,
  "loai": {"ma": "BAO_CAO_HQKH", "ten": "…", "phu": null},
  "ten_tep": "…xlsx", "size_bytes": 304901, "nguoi": "admin", "luc": "2026-10-02T…",
  "thang": "1 → 7", "sheet": null, "tong_so_dong": 7561, "so_dong_ghi": 7471, "so_sheet": 3,
  "buoc": [{"ma": "A1", "ten": "Nhận tệp", "ket_qua": "Đúng định dạng .xlsx, đọc được 3 sheet.",
            "ket_luan": "Đúng", "trang_thai": "ok"}],
  "loi": [{"sheet": "…", "vi_tri": "…", "van_de": "…", "cach_xu_ly": "…"}],
  "co_the_go": true, "co_hieu_luc": true, "bang_chinh": "fact_ket_qua_kd"
}
```

- `buoc`: đủ 10 bước A1–A5, B1–B5, câu chữ đúng mục 17. `ket_luan` là chữ: Đúng / Sai / Hợp lệ / Xong / Đã xác nhận / Khớp / Lệch / Đã huỷ / Đã chốt / Không chạy. `trang_thai`: `ok` (✓), `err` (!), `skip` (– : Không chạy, Đã huỷ). Bước B4 của HQ-MAU-GC có `ten` "Đối chiếu số lượng và các mã". Lần nạp cũ từ trước khi có API: `buoc: []`.
- `thang`: chỉ lần nạp thành công có kỳ tháng (HQKD), không thì `null`. `sheet`: sheet lấy dữ liệu của HQ-MAU-GC; `null` với HQKD hoặc lần bị từ chối.
- `tong_so_dong`: số dòng đọc được (0 nếu không thành công). `so_dong_ghi`: số dòng đã vào database (câu "{n} dòng đã vào database").
- `co_the_go`: thành công **và** là lần mới nhất của (nhóm, loại tệp) — QT-17. `co_hieu_luc` = `status == "success"`. Nút "Gỡ dữ liệu" vẫn hiện ở mọi lần thành công theo đặc tả; gỡ lần không mới nhất nhận 409.
- `bang_chinh`: bảng mở bằng "Xem dữ liệu vừa nạp" / "Xem dữ liệu liên quan".
- Không có → 404 "Không tìm thấy lần nạp này."

### 3.8 `GET /loads/{id}/reconcile?the&bang&cot&chia_theo&trang&moi`

Không có `the` → mọi thẻ theo đúng thứ tự mục 18. Có `the=<ma>` → chỉ thẻ đó (kèm tham số của thẻ). `the` không có ở lần nạp này → 404.

```text
The = {ma, tieu_de, so?, thong_bao?, cot: [{t, r?}], dong: [{o: [O], ket_luan?, ket_luan_phu?, phu?, mo?}],
       tong?: [O], tuy_chon?: [{ten, nhan, gia_tri, mac, lua_chon: [{v, t}]}], trang?: {trang, moi, tong}}
O  = number | string | null | {v, mo?}
Mo = {bang, lop: "gold"|"silver"|"bronze", nam?, ky?, tim?}  hoặc  {sheet: <số thứ tự sheet, từ 1>}
```

- `cot` gồm cả cột "Kết luận" ở cuối; `o` là các ô **trừ** cột Kết luận; `tong` đủ số cột (ô cuối `null`). `r: true` = căn phải. `phu` = dòng phụ ở ô đầu (tên bảng kỹ thuật, tên khoản mục, ghi chú ô tổng P10). `ket_luan_phu` = dòng phụ dưới nhãn kết luận.
- Số tiền là số, chưa định dạng.

| Nhóm | `ma` theo thứ tự | Tiêu đề |
|---|---|---|
| HQKD | `so_dong` | Đối chiếu số dòng: tệp gốc ↔ database |
| | `tong` | Đối chiếu tổng tiền cả bảng: tệp gốc ↔ database |
| | `tien_theo_nhom` | Đối chiếu tổng tiền theo tháng, cột tiền, nhóm — `tuy_chon`: `bang` (fact_ket_qua_kd / fact_chi_phi), `cot` (cột tiền; `tat_ca` = "Tất cả cột tiền cộng lại", chỉ khi bảng có nhiều cột tiền), `chia_theo` (`ky_thang` / `ma_nhom_kd` / `ma_khoan_cp` chỉ ở Chi phí). Đổi bảng thì cột tiền về cột đầu |
| | `ma` | Đối chiếu tháng, khách hàng, nhóm, khoản mục |
| | `truoc_sau` | Các tháng trong năm {năm} trước và sau lần nạp — 12 dòng; ô "Số dòng" dạng chuỗi "50 / 1.000" (Kết quả kinh doanh / Chi phí) |
| HQ-MAU-GC | `so_dong` | như trên, 1 dòng |
| | `tong` | Đối chiếu tổng: tệp gốc ↔ database — gồm dòng ô tổng P10 ("Ghi nhận") / P1 |
| | `o_trong` | Ô không đọc được ngày hoặc số, để trống trong database — `so` = tổng số ô; chỉ có khi có ô như vậy |
| | `theo_chieu` | Đối chiếu số lượng theo {chia theo} — `so` = số nhóm; `tuy_chon.chia_theo`: Lịch may mẫu `ngay_giao_mau` / `ma_nhom_kd` / `ten_khach` / `ma_giai_doan_mau`, Đơn gia công `ma_don_vi_gc` / `khu_vuc` / `ten_khach` / `ma_hang`; phân trang (`trang`, mặc định `moi=25`), `tong` cộng mọi nhóm |
| | `ma` | Đối chiếu các mã: tệp gốc ↔ database |
| | `truoc_sau` | Nhóm HQ-MAU-GC năm {năm} trước và sau lần nạp |

- Lần nạp bị từ chối: `{"the": [{"ma": "tu_choi", "tieu_de": "Đối chiếu tệp gốc ↔ database", "thong_bao": "Không có dữ liệu đối chiếu vì tệp bị từ chối ở bước kiểm tra cấu trúc, chưa có gì được ghi vào database.", "cot": [], "dong": []}]}`.
- Lỗi đối chiếu: thẻ `truoc_sau` có `thong_bao` "Lần nạp bị huỷ nên mọi tháng trong database giữ nguyên như trước lần nạp." và `dong: []`.
- Lần nạp cũ không có dữ liệu thẻ: `{"the": []}`.
- `mo` của số Gốc / Chuẩn hoá / Phân tích chỉ có khi lần nạp thành công (lần lỗi đối chiếu cũng có `mo` nhưng bảng không có dữ liệu của lần đó).

### 3.9 `GET /loads/{id}/errors.csv`

`text/csv; charset=utf-8` có BOM, `Content-Disposition: attachment; filename="loi-lan-nap-{id}.csv"`. Cột: Sheet, Vị trí, Vấn đề, Cách xử lý.

### 3.10 Tệp gốc

- `GET /loads/{id}/file` → tệp `.xlsx` đã lưu (`filename` = tên tệp gốc). Không còn tệp → 404 "Không còn tệp gốc của lần nạp này."
- `GET /loads/{id}/file/sheets` → `[{so, ten, so_dong, an, so_dong_an}]` — mọi sheet kể cả sheet ẩn, `so` từ 1, `so_dong` tới dòng cuối có dữ liệu.
- `GET /loads/{id}/file/sheets/{n}?trang&moi` (mặc định `moi=50`) →
  `{so, ten, an, cot: ["A","B",…], tong, so_dong_an, dong: [{rn, o: [chuỗi hiển thị | null], an}]}`. Giá trị như ô Excel hiện: ngày `DD/MM/YYYY`, số theo định dạng ô (chấm nghìn, phẩy thập phân). `an: true` = dòng đang bị bộ lọc Excel ẩn. Sheet không có → 404.

### 3.11 `DELETE /loads/{id}` — chỉ Admin

- Thành công → **Gỡ dữ liệu** (QT-17): xoá hẳn dữ liệu 3 lớp, kết quả đối chiếu, bản ghi lần nạp, tệp đã tải; dữ liệu lần trước được dùng lại. Không phải lần mới nhất → `409 {"detail": "Có {n} lần nạp sau lần này trên cùng nhóm thông tin. Hãy gỡ các lần nạp sau trước."}`.
- Bị từ chối / Lỗi đối chiếu / Đã gỡ → **Xoá lịch sử** (QT-18).
- `204` không thân. Ghi nhật ký `load.rollback` / `load.delete_history` với tài khoản Open WebUI.

### 3.12 `GET /tables?nhom&nam`

Thứ tự mục 19.1 (HQKD: Kết quả kinh doanh, Chi phí, Danh mục khách hàng, Danh mục chi phí; HQ-MAU-GC: May mẫu chào hàng, Đơn gia công ngoài).

```json
[{"bang": "fact_ket_qua_kd", "ten": "Kết quả kinh doanh", "mo_ta": "…", "loai": "fact",
  "nam": 2026, "thang": "1 → 7", "loai_tep": {"ma": "…", "ten": "…", "phu": null},
  "load_id": 7, "so_dong": 348, "cap_nhat": "2026-10-02T…"}]
```

`nam`: năm đang lọc với bảng số liệu, `null` với danh mục (hiện "Dùng chung mọi năm"). `thang`: `null` nếu không có kỳ tháng hoặc chưa có dữ liệu. `load_id`: lần thành công mới nhất của loại tệp trong năm đang lọc (`null` nếu chưa có). `so_dong = 0` ⇒ "Chưa nạp".

### 3.13 `GET /tables/{bang}?lop&nam&ky&tim&trang&moi`

`lop` ∈ `gold` (mặc định) / `silver` / `bronze`. `nam` chỉ áp cho bảng có cột `nam` (danh mục bỏ qua — QT-19). `ky` = tháng (HQKD). `tim` tìm trong cột chữ và cột ngày (ngày theo dạng `DD/MM/YYYY`, nên `tim=06/2026` ra tháng 6/2026). Mặc định `moi=50`.

```json
{
  "bang": "fact_ket_qua_kd", "ten": "Kết quả kinh doanh", "mo_ta": "…", "moi_dong_la": "…",
  "nhom": "HQKD", "loai": "fact", "loai_tep": {"ma": "…", "ten": "…", "phu": null},
  "lop": "gold", "nam": 2026, "thang_moi_nhat": "7/2026", "cap_nhat": "2026-10-02T…",
  "co_ky": true, "ky_ds": ["1", "2", "3", "4", "5", "6", "7"],
  "cot": [{"ten": "nam", "ten_nbc": "Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp",
           "kieu": "int", "kieu_hien": "Số nguyên", "bat_buoc": true, "y_nghia": "…",
           "dung_de": "…", "vi_du": "2026", "so_do": false}],
  "tong": 348, "dong": [[2026, 1, "EO-00050", "…"]], "dong_tong": null
}
```

- `cot` theo đúng thứ tự cột của `dong`; bảng số liệu có `nam` đứng đầu. `kieu` ∈ `text|int|money|ratio|number|date`; `kieu_hien` là chữ cho "Kiểu dữ liệu: …"; `bat_buoc` = cột định danh (thêm " · cột định danh, bắt buộc"). Cột không có trong tệp: `ten_nbc` "Không có trong tệp — để trống".
- `dong_tong`: chỉ khi có `ky` hoặc `tim` và lớp không phải gốc — mảng cùng độ dài `cot`, ô cột số đo là tổng, ô khác `null`.
- `co_ky`: bảng có chip "Tháng" (chỉ HQKD). `ky_ds`: các tháng đang có trong năm đã chọn.

### 3.14 `GET /tables/{bang}/export.xlsx?lop&nam&ky&tim`

Tệp `{NHÓM}-{bảng}-{lớp}[-{năm}].xlsx` (`Content-Disposition`), header `X-So-Dong`. Chỉ các dòng đang lọc, không theo trang. Sheet dữ liệu (tên = tên bảng) tiêu đề là tên biến; sheet `THONG_TIN`: Bảng, Tên bảng, Nội dung, Mỗi dòng là, Dùng để, Nhóm thông tin, Lớp dữ liệu, Bộ lọc, Số dòng, Xuất lúc; một dòng trống; bảng cột `ten_cot, ten_trong_tep_nbc, kieu_du_lieu, bat_buoc, y_nghia, dung_de, vi_du`.

### 3.15 Cấu hình database — chỉ Admin

- `GET /db-config` → `{"cau_hinh": {host, port, database, username, ghi_chu} | null, "ket_noi": {ok, mo_ta, ly_do} | null, "lan_thu": ISO | null, "luu_luc": ISO | null}`. Không bao giờ trả mật khẩu. `mo_ta` = "postgres@postgres:5432/aibi_database"; `ly_do` = câu lỗi khi `ok=false`.
- `POST /db-config/test` thân JSON `{host, port, database, username, password, ghi_chu}` → `{"ok": bool, "thong_bao": "Kết nối được. PostgreSQL 16.15" | câu lỗi DICH_LOI}`. Không lưu gì. `password` rỗng = dùng mật khẩu đang lưu.
- `PUT /db-config` (cùng thân) → thử trước; không được → `{"ok": false, "thong_bao": "<lỗi>"}`, giữ cấu hình cũ; được → `{"ok": true, "thong_bao": "Đã lưu và nối tới {user}@{host}:{port}/{db}."}`.
- `DELETE /db-config` → `{"thong_bao": "Đã bỏ cấu hình. Dữ liệu trong cơ sở dữ liệu đó không bị đụng tới."}`.
- Ô sai → `422 {"detail": "Cấu hình kết nối chưa hợp lệ.", "theo_o": {"host": "Chưa nhập địa chỉ máy chủ.", "port": "Cổng phải là số."}}` — câu theo mục 20.

## 4. Ghi chú cho người tích hợp

- Trường thêm ngoài hợp đồng frontend gửi: `theo_o` (422 cấu hình database), `ket_noi.ly_do`, `theo_nhom.tong.hien_co`, `nam` ở 3.13, `so_dong_an`/`so`/`ten`/`an` ở nội dung sheet, `ma_yeu_cau` ở lỗi 500. Không có trường nào bị bỏ.
- Ô "Năm dữ liệu" lưu ở cột `nam` của mọi bảng số liệu (`fact_*`) và ở `ctl.load.nam`.
- Kiểm thử (trong `backend/`): `python -m pytest open_webui/test/data_portal` — cần PostgreSQL đang chạy; database kiểm thử `DATA_PORTAL_TEST_DATABASE_URL` (mặc định `postgresql:///ai4bi_portal_test`) bị xoá và dựng lại mỗi lần chạy. Kiểm thử dùng tệp mẫu NBC thì cần `DATA_PORTAL_SAMPLE_DIR` trỏ tới thư mục `data_sources`; không có thì bỏ qua.
