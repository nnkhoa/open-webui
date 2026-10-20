import type { LoadStatus } from '$lib/apis/data-portal/types';

const NUMBER_LOCALE = 'de-DE';
const EMPTY = '—';

export type Tone = 'ok' | 'err' | 'warn' | 'info' | 'muted';

export const LOAD_STATUS_BADGES: Record<LoadStatus, { label: string; tone: Tone }> = {
	success: { label: 'Succeeded', tone: 'ok' },
	rejected: { label: 'Rejected', tone: 'err' },
	mismatch: { label: 'Reconciliation error', tone: 'err' },
	rolled_back: { label: 'Rolled back', tone: 'warn' }
};

const VERDICT_TONES: Record<string, Tone> = {
	Đúng: 'ok',
	Khớp: 'ok',
	Đủ: 'ok',
	'Hợp lệ': 'ok',
	'Đã xác nhận': 'ok',
	'Đã chốt': 'ok',
	'Giữ nguyên': 'ok',
	Xong: 'ok',
	'Ghi thêm': 'ok',
	Sai: 'err',
	Lệch: 'err',
	Thiếu: 'err',
	Thừa: 'err',
	'Đã huỷ': 'err',
	'Ghi đè': 'warn',
	'Ghi nhận': 'info',
	'Không chạy': 'muted',
	'Không đụng tới': 'muted',
	'Chưa upload': 'muted',
	'Chưa nạp': 'muted'
};

const CANCELLED_VERDICT = 'Đã huỷ';

export const verdictTone = (verdict: string, skipped = false): Tone =>
	skipped && verdict === CANCELLED_VERDICT ? 'muted' : (VERDICT_TONES[verdict] ?? 'muted');

export const isBlank = (value: unknown) => value === null || value === undefined || value === '';

export const formatNumber = (value: unknown): string => {
	if (isBlank(value)) return EMPTY;
	if (typeof value === 'number') return Math.round(value).toLocaleString(NUMBER_LOCALE);
	return String(value);
};

export const formatAmount = (value: unknown): string => {
	if (isBlank(value)) return EMPTY;
	const amount = Number(value);
	if (Number.isNaN(amount)) return String(value);
	if (Number.isInteger(amount)) return amount.toLocaleString(NUMBER_LOCALE);
	return amount.toLocaleString(NUMBER_LOCALE, {
		minimumFractionDigits: 2,
		maximumFractionDigits: 2
	});
};

export const formatPercent = (value: unknown): string =>
	isBlank(value) ? EMPTY : (Number(value) * 100).toFixed(2).replace('.', ',') + '%';

export const formatDateTime = (value: unknown): string => {
	if (!value) return EMPTY;
	const date = new Date(String(value));
	if (Number.isNaN(date.getTime())) return String(value);
	const day = `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`;
	return `${day} - ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

export const formatDate = (value: unknown): string => {
	if (!value) return EMPTY;
	const text = String(value);
	const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
	return match ? `${match[3]}/${match[2]}/${match[1]}` : text;
};

export const formatKilobytes = (bytes: unknown): string => {
	const size = Number(bytes ?? 0);
	const kilobytes = (size / 1024).toLocaleString(NUMBER_LOCALE, {
		minimumFractionDigits: 1,
		maximumFractionDigits: 1
	});
	return `${kilobytes} KB`;
};

export const joinWithAnd = (items: string[], and: string): string =>
	items.length <= 1
		? items.join('')
		: `${items.slice(0, -1).join(', ')} ${and} ${items[items.length - 1]}`;

const pad = (value: number) => String(value).padStart(2, '0');
