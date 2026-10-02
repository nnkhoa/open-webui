import { writable } from 'svelte/store';

// Nhóm thông tin và Năm đang lọc, dùng chung giữa Lịch sử nạp và Dữ liệu (đặc tả CN-02).
export const dpNhom = writable<string>('HQKD');
export const dpNam = writable<string>(''); // '' = Tất cả năm

export const DP_ROLES = ['admin', 'data_uploader'];
export const DP_NAM = ['2025', '2026', '2027', '2028', '2029', '2030', '2031'];

// Bước 1 của màn Nạp dữ liệu: giữ lựa chọn khi quay lại từ màn Xác nhận (đặc tả 15.3).
export type NapState = { nhom: string; nam: string; loai: string; file: File | null; luc: string };
export const NAP_TRONG: NapState = { nhom: '', nam: '', loai: '', file: null, luc: '' };
export const dpNap = writable<NapState>({ ...NAP_TRONG });

// Danh sách nhóm thông tin lấy từ GET /domains.
export type LoaiTep = { ma: string; ten: string; phu?: string };
export type Domain = { code: string; name: string; phu?: string; loai_tep: LoaiTep[] };
export const dpDomains = writable<Domain[]>([]);
