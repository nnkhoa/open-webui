# API JSON của Data Portal

Hợp đồng thực tế của `open_webui/data_portal/api` — đúng với mã nguồn và bộ kiểm thử `open_webui/test/data_portal/`.

## 1. Quy ước chung

- Ứng dụng FastAPI con, chạy trong process Open WebUI, gắn ở `/api/v1/data-portal` (`open_webui/main.py`). Đường dẫn ở phần 3 viết tương đối: `GET /loads` là `GET /api/v1/data-portal/loads`.
- JSON UTF-8. Số trả dạng số: số nguyên là `int`, số có phần lẻ là `float`. Thời gian theo ISO 8601 (`2026-10-02T04:30:12.345+00:00`). Giao diện tự định dạng.
- Phân trang: `page` (từ 1), `page_size` ∈ {25, 50, 100}. Giá trị khác trả 422.
- Lỗi: mã HTTP 4xx/5xx, thân `{"detail": "<câu tiếng Việt>"}`.

| Mã | Khi nào |
|---|---|
| 401 | Chưa đăng nhập Open WebUI hoặc phiên hết hạn |
| 403 | Vai trò không phải `admin` / `data_uploader` ("Bạn không có quyền vào Data Portal. Liên hệ Admin nếu cần nạp dữ liệu."); Data Loader gọi đường dẫn chỉ Admin ("Bạn không có quyền thực hiện thao tác này") |
| 404 | Không tìm thấy (lần nạp, tệp chờ, bảng, sheet, đường dẫn) |
| 409 | Gỡ lần nạp không phải mới nhất |
| 422 | Dữ liệu gửi lên sai. Riêng cấu hình database có thêm `field_errors: {host, port, database, username}` — lỗi theo từng ô |
| 503 | Data Portal đang khởi động; chưa cấu hình / mất kết nối database; `detail` là lý do |
| 500 | Lỗi ngoài dự kiến; thân có thêm `request_id` để tra nhật ký |

Đường dẫn không tồn tại vẫn kiểm danh tính trước (401/403) rồi mới trả 404.

## 2. Danh tính

- Người gọi là tài khoản Open WebUI đang đăng nhập (`get_verified_user`, token Bearer như mọi API khác của Open WebUI).
- Cột Người nạp và nhật ký `ctl_audit_event` ghi tên hiển thị của tài khoản; `user_id` là mã người dùng Open WebUI.
- Quyền: **A** = chỉ `admin`; **A, L** = `admin` và `data_uploader`.

## 3. Danh sách API

| Phương thức, đường dẫn | Quyền | Phần |
|---|---|---|
| `GET /domains` | A, L | 3.1 |
| `POST /uploads` | A, L | 3.2 |
| `GET /uploads/{pending_id}` | A, L | 3.3 |
| `DELETE /uploads/{pending_id}` | A, L | 3.4 |
| `POST /uploads/{pending_id}/confirm` | A, L | 3.5 |
| `GET /loads` | A, L | 3.6 |
| `GET /loads/{id}` | A, L | 3.7 |
| `GET /loads/{id}/reconcile` | A, L | 3.8 |
| `GET /loads/{id}/errors.csv` | A, L | 3.9 |
| `GET /loads/{id}/file` | A, L | 3.10 |
| `GET /loads/{id}/file/sheets` | A, L | 3.10 |
| `GET /loads/{id}/file/sheets/{index}` | A, L | 3.10 |
| `DELETE /loads/{id}` | A | 3.11 |
| `GET /tables` | A, L | 3.12 |
| `GET /tables/{table}` | A, L | 3.13 |
| `GET /tables/{table}/export.xlsx` | A, L | 3.14 |
| `GET /db-config` · `POST /db-config/test` · `PUT /db-config` · `DELETE /db-config` | A | 3.15 |

### 3.1 `GET /domains`

```json
[
  {"code": "HQKD", "name": "Hiệu quả kinh doanh theo nhóm và khách hàng",
   "subtitle": "HQKD · Báo cáo hiệu quả từng khách hàng",
   "file_types": [{"code": "BAO_CAO_HQKH", "name": "Báo cáo hiệu quả từng khách hàng", "subtitle": null}]},
  {"code": "HQ-MAU-GC", "name": "Hiệu quả may mẫu chào hàng, gia công ngoài",
   "subtitle": "HQ-MAU-GC · Lịch may mẫu, Đơn gia công ngoài",
   "file_types": [{"code": "LICH_MAY_MAU", "name": "Lịch may mẫu", "subtitle": "SAMPLE MAKING SCHEDULE"},
                  {"code": "DON_GIA_CONG", "name": "Đơn gia công ngoài", "subtitle": "TOTAL PO SUBCON"}]}
]
```

`file_types` rỗng ⇒ nhóm chưa khai loại tệp (màn trống "Chưa có thông tin"). Danh sách năm cố định 2025–2031, giao diện tự có.

### 3.2 `POST /uploads` — Kiểm tra tệp (chỉ đọc)

`multipart/form-data`: `domain` (mã nhóm), `year` (2025–2031), `file_type` (mã loại tệp — bắt buộc khi nhóm có nhiều loại tệp, bỏ trống được khi nhóm chỉ có một), `file`.

- Hợp lệ → `200 {"pending_id": "<32 ký tự hex>"}`. Database không đổi.
- Có lỗi cấu trúc / dữ liệu → `200 {"load_id": 12, "status": "rejected"}`. Đã tạo lần nạp "Bị từ chối", lưu tệp và danh sách lỗi.
- 422 với `detail`: "Chưa chọn Nhóm thông tin." · "Nhóm thông tin không hợp lệ." · "Chưa chọn Năm dữ liệu." · "Năm dữ liệu phải từ 2025 đến 2031." · "Chưa chọn Loại tệp." · "Loại tệp không hợp lệ." · "Chưa chọn tệp." · "Portal chỉ nhận tệp .xlsx. Hãy mở tệp trong Excel và lưu lại đúng định dạng." (đuôi khác `.xlsx`, hoặc tệp hỏng) · "Nhóm {tên} chưa có thông tin: chưa khai báo loại tệp nên chưa nạp, chưa có lịch sử và chưa có dữ liệu."

### 3.3 `GET /uploads/{pending_id}` — màn Xác nhận

Chỉ người đã tải lên mới xem / huỷ / xác nhận được; người khác nhận 404 như tệp không có. Phần "so với dữ liệu đang có" tính lại lúc hỏi.

```json
{
  "pending_id": "…", "domain": "HQKD", "year": 2026,
  "file_type": {"code": "BAO_CAO_HQKH", "name": "Báo cáo hiệu quả từng khách hàng", "subtitle": null},
  "file_name": "FORM MAU - HIEU QUA TUNG KHACH HANG T1-T7.26.xlsx", "size_bytes": 304901,
  "sheet": null,
  "checks": [
    {"table": "fact_ket_qua_kd", "table_name": "Kết quả kinh doanh", "sheet": "TỔNG HỢP",
     "read": 348, "missing_required": 0, "duplicates": 0, "empty_cells": 0, "empty_cell_details": [],
     "to_write": 348, "total": 3193114446744.495, "verdict": "Hợp lệ"}
  ],
  "identical": null,
  "overwrite": [], "new": [1, 2, 3, 4, 5, 6, 7], "previous": null,
  "by_group": {
    "title": "Theo tháng", "first_column": "Tháng",
    "rows": [{"group": "Tháng 1/2026", "data": "Kết quả kinh doanh", "row_count": 50,
              "column_count": 15, "total_column_count": 15, "existing": null, "write_mode": "Ghi thêm"}],
    "total": {"row_count": 7308}
  }
}
```

- `checks` theo thứ tự hiển thị bảng. `total`: tổng tiền (HQKD), tổng số lượng (HQ-MAU-GC), `null` với danh mục. `empty_cells` = số ô không đổi được kiểu, sẽ để trống; `empty_cell_details: [{column, cell_count}]`. `verdict`: "Hợp lệ".
- `identical`: `{load_id, created_at, user}` — lần nạp đang có hiệu lực cùng nhóm, năm, loại tệp có cùng mã băm tệp.
- `existing` (mỗi dòng): `null` hoặc `{row_count, load_id, created_at, user}` — dữ liệu đang có của nhóm dòng đó trong năm đã chọn. `write_mode`: "Ghi đè" / "Ghi thêm".
- **HQKD**: `overwrite` / `new` là số tháng; `previous: null`; `by_group` mỗi tháng 2 dòng (`data` "Kết quả kinh doanh" / "Chi phí"), tên tháng lặp ở cả hai dòng (giao diện tự ẩn ở dòng thứ hai).
- **HQ-MAU-GC**: `sheet` = sheet lấy dữ liệu ("30 Sep - OK", "Final 09.4"); `previous`: `null` hoặc `{row_count, load_id, created_at, user}` — dữ liệu đang có hiệu lực của cùng loại tệp, năm (sẽ bị ghi đè toàn bộ); `overwrite` / `new` = `["Lịch may mẫu"]` theo đó.
  - Lịch may mẫu: `by_group.title` "Theo tháng giao mẫu", `first_column` "Tháng giao mẫu"; dòng `{group: "Tháng 6/2026", row_count, quantity, existing, write_mode}`, dòng cuối `{group: "Chưa có ngày giao mẫu", subtitle: "148 ô trống, 24 ô không đọc được ngày", …}`.
  - Đơn gia công ngoài: "Theo đơn vị gia công" / "Đơn vị gia công", thứ tự như trong tệp.
  - `total`: `{row_count, quantity, existing}` (`existing` = số dòng đang có, hoặc `null`).

### 3.4 `DELETE /uploads/{pending_id}` — "Huỷ, không nạp"

`204`, không thân. Tệp chờ bị xoá, database không đổi. Không có / của người khác → 404.

### 3.5 `POST /uploads/{pending_id}/confirm` — "Xác nhận thêm mới dữ liệu"

Ghi 3 lớp trong một giao dịch dưới khoá (nhóm, loại tệp), đối chiếu, lệch thì huỷ cả lần.

`200 {"load_id": 7, "status": "success" | "mismatch" | "rejected"}`.
Tệp chờ không còn (đã xác nhận, đã huỷ, quá 24 giờ) → `404 {"detail": "Tệp này đã được nạp hoặc đã quá hạn chờ xác nhận. Hãy xem Lịch sử nạp, hoặc chọn lại tệp."}`.

### 3.6 `GET /loads?domain&year&file_type&status&user&query&page&page_size`

`domain` bắt buộc. `file_type` = mã loại tệp; `status` ∈ `success|rejected|mismatch|rolled_back`; `user` = tên người nạp (đúng như trong `uploaders`); `query` khớp mã (có thể kèm `#`) hoặc tên tệp. Mặc định `page_size=25`. Mới nhất ở trên.

```json
{"total": 2, "uploaders": ["admin", "loader"],
 "items": [{"id": 2, "file_name": "…xlsx", "year": 2026, "file_type": {"code": "BAO_CAO_HQKH", "name": "…"},
            "user": "admin", "created_at": "2026-10-02T…", "row_count": 7561, "status": "success"}]}
```

`row_count` = số dòng đọc được; lần nạp không thành công là 0.

### 3.7 `GET /loads/{id}`

```json
{
  "id": 7, "status": "success", "domain": "HQKD", "year": 2026,
  "file_type": {"code": "BAO_CAO_HQKH", "name": "…", "subtitle": null},
  "file_name": "…xlsx", "size_bytes": 304901, "user": "admin", "created_at": "2026-10-02T…",
  "months": "1 → 7", "sheet": null, "total_rows": 7561, "rows_written": 7471, "sheet_count": 3,
  "steps": [{"code": "A1", "name": "Nhận tệp", "result": "Đúng định dạng .xlsx, đọc được 3 sheet.",
             "verdict": "Đúng", "status": "ok"}],
  "errors": [{"sheet": "…", "location": "…", "issue": "…", "resolution": "…"}],
  "can_rollback": true, "is_active": true, "primary_table": "fact_ket_qua_kd"
}
```

- `steps`: đủ 10 bước A1–A5, B1–B5. `verdict` là chữ: Đúng / Sai / Hợp lệ / Xong / Đã xác nhận / Khớp / Lệch / Đã huỷ / Đã chốt / Không chạy. `status`: `ok` (✓), `err` (!), `skip` (– : Không chạy, Đã huỷ). Bước B4 của HQ-MAU-GC có `name` "Đối chiếu số lượng và các mã".
- `months`: chỉ lần nạp thành công có kỳ tháng (HQKD), không thì `null`. `sheet`: sheet lấy dữ liệu của HQ-MAU-GC; `null` với HQKD hoặc lần bị từ chối.
- `total_rows`: số dòng đọc được (0 nếu không thành công). `rows_written`: số dòng đã vào database (câu "{n} dòng đã vào database").
- `can_rollback`: thành công **và** là lần mới nhất của (nhóm, loại tệp). `is_active` = `status == "success"`. Nút "Gỡ dữ liệu" vẫn hiện ở mọi lần thành công; gỡ lần không mới nhất nhận 409.
- `primary_table`: bảng mở bằng "Xem dữ liệu vừa nạp" / "Xem dữ liệu liên quan".
- Không có → 404 "Không tìm thấy lần nạp này."

### 3.8 `GET /loads/{id}/reconcile?card&table&column&group_by&page&page_size`

Không có `card` → mọi thẻ theo thứ tự cố định. Có `card=<key>` → chỉ thẻ đó (kèm tham số của thẻ). `card` không có ở lần nạp này → 404.

```text
{cards: [Card]}
Card = {key, title, count?, message?, columns: [{label, align_right?}],
        rows: [{cells: [Cell], verdict, verdict_note?, note?, link?}],
        totals?: [Cell], options?: [{name, label, value, default, choices: [{value, label}]}],
        pagination?: {page, page_size, total}}
Cell = number | string | null | {value, link?}
Link = {table, layer: "gold"|"silver"|"bronze", year?, period?, query?}  hoặc  {sheet: <số thứ tự sheet, từ 1>}
```

- `columns` gồm cả cột "Kết luận" ở cuối; `cells` là các ô **trừ** cột Kết luận; `totals` đủ số cột (ô cuối `null`). `align_right: true` = căn phải. `note` = dòng phụ ở ô đầu (tên bảng kỹ thuật, tên khoản mục, ghi chú ô tổng P10). `verdict_note` = dòng phụ dưới nhãn kết luận.
- Số tiền là số, chưa định dạng. Tên tuỳ chọn (`options[].name`) trùng tên tham số truy vấn: `table`, `column`, `group_by`.

| Nhóm | `key` theo thứ tự | Tiêu đề |
|---|---|---|
| HQKD | `row_count` | Đối chiếu số dòng: tệp gốc ↔ database |
| | `totals` | Đối chiếu tổng tiền cả bảng: tệp gốc ↔ database |
| | `amount_by_group` | Đối chiếu tổng tiền theo tháng, cột tiền, nhóm — `options`: `table` (fact_ket_qua_kd / fact_chi_phi), `column` (cột tiền; `all` = "Tất cả cột tiền cộng lại", chỉ khi bảng có nhiều cột tiền), `group_by` (`ky_thang` / `ma_nhom_kd` / `ma_khoan_cp` chỉ ở Chi phí). Đổi bảng thì cột tiền về cột đầu |
| | `codes` | Đối chiếu tháng, khách hàng, nhóm, khoản mục |
| | `before_after` | Các tháng trong năm {năm} trước và sau lần nạp — 12 dòng; ô "Số dòng" dạng chuỗi "50 / 1.000" (Kết quả kinh doanh / Chi phí) |
| HQ-MAU-GC | `row_count` | như trên, 1 dòng |
| | `totals` | Đối chiếu tổng: tệp gốc ↔ database — gồm dòng ô tổng P10 ("Ghi nhận") / P1 |
| | `empty_cells` | Ô không đọc được ngày hoặc số, để trống trong database — `count` = tổng số ô; chỉ có khi có ô như vậy |
| | `by_dimension` | Đối chiếu số lượng theo {chia theo} — `count` = số nhóm; `options` `group_by`: Lịch may mẫu `ngay_giao_mau` / `ma_nhom_kd` / `ten_khach` / `ma_giai_doan_mau`, Đơn gia công `ma_don_vi_gc` / `khu_vuc` / `ten_khach` / `ma_hang`; phân trang (`page`, mặc định `page_size=25`), `totals` cộng mọi nhóm |
| | `codes` | Đối chiếu các mã: tệp gốc ↔ database |
| | `before_after` | Nhóm HQ-MAU-GC năm {năm} trước và sau lần nạp |

- Lần nạp bị từ chối: `{"cards": [{"key": "rejected", "title": "Đối chiếu tệp gốc ↔ database", "message": "Không có dữ liệu đối chiếu vì tệp bị từ chối ở bước kiểm tra cấu trúc, chưa có gì được ghi vào database.", "columns": [], "rows": []}]}`.
- Lỗi đối chiếu: thẻ `before_after` có `message` "Lần nạp bị huỷ nên mọi tháng trong database giữ nguyên như trước lần nạp." và `rows: []`.
- Lần nạp không có dữ liệu thẻ: `{"cards": []}`.
- `link` của số Gốc / Chuẩn hoá / Phân tích chỉ có khi lần nạp thành công (lần lỗi đối chiếu cũng có `link` nhưng bảng không có dữ liệu của lần đó).

### 3.9 `GET /loads/{id}/errors.csv`

`text/csv; charset=utf-8` có BOM, `Content-Disposition: attachment; filename="loi-lan-nap-{id}.csv"`. Cột: Sheet, Vị trí, Vấn đề, Cách xử lý.

### 3.10 Tệp gốc

- `GET /loads/{id}/file` → tệp `.xlsx` đã lưu (`filename` = tên tệp gốc). Không còn tệp → 404 "Không còn tệp gốc của lần nạp này."
- `GET /loads/{id}/file/sheets` → `[{index, name, row_count, hidden, hidden_row_count}]` — mọi sheet kể cả sheet ẩn, `index` từ 1, `row_count` tới dòng cuối có dữ liệu.
- `GET /loads/{id}/file/sheets/{index}?page&page_size` (mặc định `page_size=50`) →
  `{index, name, hidden, columns: ["A","B",…], total, hidden_row_count, rows: [{row_number, cells: [chuỗi hiển thị | null], hidden}]}`. Giá trị như ô Excel hiện: ngày `DD/MM/YYYY`, số theo định dạng ô (chấm nghìn, phẩy thập phân). `hidden: true` = dòng đang bị bộ lọc Excel ẩn. Sheet không có → 404.

### 3.11 `DELETE /loads/{id}` — chỉ Admin

- Thành công → **Gỡ dữ liệu**: xoá hẳn dữ liệu 3 lớp, kết quả đối chiếu, bản ghi lần nạp, tệp đã tải; dữ liệu lần trước được dùng lại. Không phải lần mới nhất → `409 {"detail": "Có {n} lần nạp sau lần này trên cùng nhóm thông tin. Hãy gỡ các lần nạp sau trước."}`.
- Bị từ chối / Lỗi đối chiếu / Đã gỡ → **Xoá lịch sử**.
- `204` không thân. Ghi nhật ký `load.rollback` / `load.delete_history` với tài khoản Open WebUI.

### 3.12 `GET /tables?domain&year`

Thứ tự cố định (HQKD: Kết quả kinh doanh, Chi phí, Danh mục khách hàng, Danh mục chi phí; HQ-MAU-GC: May mẫu chào hàng, Đơn gia công ngoài).

```json
[{"table": "fact_ket_qua_kd", "name": "Kết quả kinh doanh", "description": "…", "kind": "fact",
  "year": 2026, "months": "1 → 7", "file_type": {"code": "…", "name": "…", "subtitle": null},
  "load_id": 7, "row_count": 348, "updated_at": "2026-10-02T…"}]
```

`year`: năm đang lọc với bảng số liệu, `null` với danh mục (hiện "Dùng chung mọi năm"). `months`: `null` nếu không có kỳ tháng hoặc chưa có dữ liệu. `load_id`: lần thành công mới nhất của loại tệp trong năm đang lọc (`null` nếu chưa có). `row_count = 0` ⇒ "Chưa nạp".

### 3.13 `GET /tables/{table}?layer&year&period&query&page&page_size`

`layer` ∈ `gold` (mặc định) / `silver` / `bronze`. `year` chỉ áp cho bảng có cột `nam` (danh mục bỏ qua). `period` = tháng (HQKD). `query` tìm trong cột chữ và cột ngày (ngày theo dạng `DD/MM/YYYY`, nên `query=06/2026` ra tháng 6/2026). Mặc định `page_size=50`.

```json
{
  "table": "fact_ket_qua_kd", "name": "Kết quả kinh doanh", "description": "…", "grain": "…",
  "domain": "HQKD", "kind": "fact", "file_type": {"code": "…", "name": "…", "subtitle": null},
  "layer": "gold", "year": 2026, "latest_month": "7/2026", "updated_at": "2026-10-02T…",
  "has_period": true, "periods": ["1", "2", "3", "4", "5", "6", "7"],
  "columns": [{"name": "nam", "source_name": "Không có trong tệp — lấy từ ô Năm dữ liệu chọn lúc nạp",
               "type": "int", "type_label": "Số nguyên", "required": true, "meaning": "…",
               "purpose": "…", "example": "2026", "is_measure": false}],
  "total": 348, "rows": [[2026, 1, "EO-00050", "…"]], "total_row": null
}
```

- `columns` theo đúng thứ tự cột của `rows`; bảng số liệu có `nam` đứng đầu. `type` ∈ `text|int|money|ratio|number|date`; `type_label` là chữ cho "Kiểu dữ liệu: …"; `required` = cột định danh (thêm " · cột định danh, bắt buộc"). Cột không có trong tệp: `source_name` "Không có trong tệp — để trống".
- `total_row`: chỉ khi có `period` hoặc `query` và lớp không phải gốc — mảng cùng độ dài `columns`, ô cột số đo là tổng, ô khác `null`.
- `has_period`: bảng có chip "Tháng" (chỉ HQKD). `periods`: các tháng đang có trong năm đã chọn.

### 3.14 `GET /tables/{table}/export.xlsx?layer&year&period&query`

Tệp `{NHÓM}-{bảng}-{lớp}[-{năm}].xlsx` (`Content-Disposition`), header `X-Row-Count`. Chỉ các dòng đang lọc, không theo trang. Sheet dữ liệu (tên = tên bảng) tiêu đề là tên biến; sheet `THONG_TIN`: Bảng, Tên bảng, Nội dung, Mỗi dòng là, Dùng để, Nhóm thông tin, Lớp dữ liệu, Bộ lọc, Số dòng, Xuất lúc; một dòng trống; bảng cột `ten_cot, ten_trong_tep_nbc, kieu_du_lieu, bat_buoc, y_nghia, dung_de, vi_du`.

### 3.15 Cấu hình database — chỉ Admin

- `GET /db-config` → `{"config": {host, port, database, username, note} | null, "connection": {ok, description, reason} | null, "last_tested_at": ISO | null, "saved_at": ISO | null}`. Không bao giờ trả mật khẩu. `description` = "postgres@postgres:5432/aibi_database"; `reason` = câu lỗi khi `ok=false`.
- `POST /db-config/test` thân JSON `{host, port, database, username, password, note}` → `{"ok": bool, "message": "Kết nối được. PostgreSQL 16.15" | câu lỗi đã dịch}`. Không lưu gì. `password` rỗng = dùng mật khẩu đang lưu.
- `PUT /db-config` (cùng thân) → thử trước; không được → `{"ok": false, "message": "<lỗi>"}`, giữ cấu hình cũ; được → `{"ok": true, "message": "Đã lưu và nối tới {user}@{host}:{port}/{db}."}`.
- `DELETE /db-config` → `{"message": "Đã bỏ cấu hình. Dữ liệu trong cơ sở dữ liệu đó không bị đụng tới."}`.
- Ô sai → `422 {"detail": "Cấu hình kết nối chưa hợp lệ.", "field_errors": {"host": "Chưa nhập địa chỉ máy chủ.", "port": "Cổng phải là số."}}`.

## 4. Ghi chú cho người tích hợp

- Ô "Năm dữ liệu" lưu ở cột `nam` của mọi bảng số liệu (`fact_*`) và ở `ctl.load.year`.
- Kiểm thử (trong `backend/`): `python -m pytest open_webui/test/data_portal` — cần PostgreSQL đang chạy; database kiểm thử `DATA_PORTAL_TEST_DATABASE_URL` (mặc định `postgresql:///ai4bi_portal_test`) bị xoá và dựng lại mỗi lần chạy. Kiểm thử dùng tệp mẫu NBC thì cần `DATA_PORTAL_SAMPLE_DIR` trỏ tới thư mục `data_sources`; không có thì bỏ qua.
