// Định dạng số, thời gian theo đặc tả mục 13.3.
const VI = 'de-DE'; // dấu chấm nghìn, dấu phẩy thập phân

export const so = (n: unknown): string => {
	if (n === null || n === undefined || n === '') return '—';
	if (typeof n === 'number') return Math.round(n).toLocaleString(VI);
	return String(n);
};

export const soTien = (x: unknown): string => {
	if (x === null || x === undefined || x === '') return '—';
	const n = Number(x);
	if (Number.isNaN(n)) return String(x);
	if (Number.isInteger(n)) return n.toLocaleString(VI);
	return n.toLocaleString(VI, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export const tyLe = (x: unknown): string =>
	x === null || x === undefined || x === '' ? '—' : (Number(x) * 100).toFixed(2).replace('.', ',') + '%';

const p2 = (n: number) => String(n).padStart(2, '0');

// YYYY/MM/DD - HH:mm
export const thoiGian = (iso: unknown): string => {
	if (!iso) return '—';
	const d = new Date(String(iso));
	if (Number.isNaN(d.getTime())) return String(iso);
	return `${d.getFullYear()}/${p2(d.getMonth() + 1)}/${p2(d.getDate())} - ${p2(d.getHours())}:${p2(d.getMinutes())}`;
};

// DD/MM/YYYY
export const ngay = (iso: unknown): string => {
	if (!iso) return '—';
	const s = String(iso);
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
	return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
};

// "822,6 KB"
export const kb = (bytes: unknown): string => {
	const n = Number(bytes ?? 0);
	return (n / 1024).toLocaleString(VI, { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' KB';
};

// Nối danh sách: "A, B và C"
export const noi = (ds: string[]): string =>
	ds.length <= 1 ? ds.join('') : ds.slice(0, -1).join(', ') + ' và ' + ds[ds.length - 1];

export const TRANG_THAI: Record<string, [string, string]> = {
	success: ['Thành công', 'ok'],
	rejected: ['Bị từ chối', 'err'],
	mismatch: ['Lỗi đối chiếu', 'err'],
	rolled_back: ['Đã gỡ', 'warn']
};

// Màu nhãn kết luận (đặc tả 12.8).
const MAU_KET_LUAN: Record<string, string> = {
	'Đúng': 'ok', 'Khớp': 'ok', 'Đủ': 'ok', 'Hợp lệ': 'ok', 'Đã xác nhận': 'ok', 'Đã chốt': 'ok',
	'Giữ nguyên': 'ok', 'Xong': 'ok', 'Ghi thêm': 'ok',
	'Sai': 'err', 'Lệch': 'err', 'Thiếu': 'err', 'Thừa': 'err', 'Đã huỷ': 'err',
	'Ghi đè': 'warn', 'Ghi nhận': 'info',
	'Không chạy': 'muted', 'Không đụng tới': 'muted', 'Chưa upload': 'muted', 'Chưa nạp': 'muted'
};
export const mauKetLuan = (t: string, boQua = false): string =>
	boQua && t === 'Đã huỷ' ? 'muted' : (MAU_KET_LUAN[t] ?? 'muted');
