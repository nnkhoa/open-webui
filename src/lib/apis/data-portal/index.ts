import { WEBUI_API_BASE_URL } from '$lib/constants';

// Gọi API Data Portal qua router chuyển tiếp của Open WebUI (đặc tả mục 9).
const BASE = `${WEBUI_API_BASE_URL}/data-portal`;

export class DpError extends Error {
	status: number;
	body: any;
	constructor(status: number, message: string, body: any = null) {
		super(message);
		this.status = status;
		this.body = body;
	}
}

const token = () => (typeof localStorage !== 'undefined' ? localStorage.token : '');

const query = (params?: Record<string, unknown>) => {
	if (!params) return '';
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v !== undefined && v !== null && v !== '') q.set(k, String(v));
	}
	const s = q.toString();
	return s ? `?${s}` : '';
};

const docLoi = async (res: Response) => {
	let msg = 'Mất kết nối, chưa xác định được kết quả xử lý.';
	let body: any = null;
	try {
		body = await res.json();
		msg = body?.detail ?? body?.message ?? msg;
		if (typeof msg !== 'string') msg = JSON.stringify(msg);
	} catch {
		/* thân lỗi không phải JSON */
	}
	return new DpError(res.status, msg, body);
};

const goi = async (method: string, path: string, init: RequestInit = {}) => {
	let res: Response;
	try {
		res = await fetch(`${BASE}/${path}`, {
			method,
			...init,
			headers: { authorization: `Bearer ${token()}`, ...(init.headers ?? {}) }
		});
	} catch {
		throw new DpError(0, 'Mất kết nối, chưa xác định được kết quả xử lý.');
	}
	if (!res.ok) throw await docLoi(res);
	return res;
};

export const dpGet = async <T = any>(path: string, params?: Record<string, unknown>): Promise<T> => {
	const res = await goi('GET', `${path}${query(params)}`, { headers: { Accept: 'application/json' } });
	return res.json();
};

export const dpSend = async <T = any>(method: 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown): Promise<T | null> => {
	const res = await goi(method, path, {
		headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (res.status === 204) return null;
	const text = await res.text();
	return text ? JSON.parse(text) : null;
};

export const dpUpload = async <T = any>(path: string, form: FormData): Promise<T> => {
	const res = await goi('POST', path, { body: form, headers: { Accept: 'application/json' } });
	return res.json();
};

// Tải tệp (CSV, .xlsx): trả nội dung và tên tệp theo Content-Disposition.
export const dpDownload = async (path: string, params?: Record<string, unknown>, tenMacDinh = 'tep') => {
	const res = await goi('GET', `${path}${query(params)}`);
	const blob = await res.blob();
	const cd = res.headers.get('content-disposition') ?? '';
	const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
	const ten = m ? decodeURIComponent(m[1] ?? m[2]) : tenMacDinh;
	const soDong = Number(res.headers.get('x-so-dong') ?? NaN);
	return { blob, ten, soDong };
};

export const luuTep = (blob: Blob, ten: string) => {
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = ten;
	document.body.appendChild(a);
	a.click();
	a.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
};
