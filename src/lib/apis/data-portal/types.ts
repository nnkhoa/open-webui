// Kiểu dữ liệu trả về từ API Data Portal (đặc tả mục 9).
export type LoaiTep = { ma: string; ten: string; phu?: string };
export type Buoc = { ma: string; ten: string; ket_qua: string; ket_luan: string; trang_thai: 'ok' | 'err' | 'skip' };
export type Loi = { sheet: string; vi_tri: string; van_de: string; cach_xu_ly: string };
export type LanNap = {
	id: number;
	status: 'success' | 'rejected' | 'mismatch' | 'rolled_back';
	nhom: string;
	nam: string | number;
	loai: LoaiTep | null;
	ten_tep: string;
	size_bytes: number;
	nguoi: string;
	luc: string;
	thang: string | null;
	sheet: string | null;
	tong_so_dong: number;
	so_dong_ghi: number;
	so_sheet: number;
	buoc: Buoc[];
	loi: Loi[];
	co_the_go: boolean;
	co_hieu_luc: boolean;
	bang_chinh?: string; // bảng mở bằng nút "Xem dữ liệu vừa nạp"
};
