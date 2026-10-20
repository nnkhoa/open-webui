import { get } from 'svelte/store';

import { WEBUI_API_BASE_URL } from '$lib/constants';
import portalI18n from '$lib/components/data-portal/i18n';

import type {
	ConfirmedUpload,
	DbConfig,
	DbConfigForm,
	DbConfigResult,
	Domain,
	DownloadedFile,
	FormCheckRequest,
	FormCheckResult,
	Load,
	LoadFilter,
	LoadList,
	PendingUpload,
	PortalStatus,
	ReconcileCard,
	ReconcileQuery,
	SourceSheet,
	SourceSheetPage,
	TableData,
	TableFilter,
	TableSummary,
	UploadForm,
	UploadResult
} from './types';

const DATA_PORTAL_API_BASE_URL = `${WEBUI_API_BASE_URL}/data-portal`;

export class DataPortalApiError extends Error {
	status: number;
	fieldErrors: Record<string, string> | null;

	constructor(status: number, message: string, fieldErrors: Record<string, string> | null = null) {
		super(message);
		this.status = status;
		this.fieldErrors = fieldErrors;
	}
}

export const getDomains = async (token: string): Promise<Domain[]> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/domains`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createUpload = async (token: string, upload: UploadForm): Promise<UploadResult> => {
	let error = null;

	const body = new FormData();
	body.set('domain', upload.domain);
	body.set('year', upload.year);
	if (upload.month) {
		body.set('month', upload.month);
	}
	if (upload.fileType) {
		body.set('file_type', upload.fileType);
	}
	body.set('file', upload.file);

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/uploads`, {
		method: 'POST',
		headers: { Accept: 'application/json', authorization: `Bearer ${token}` },
		body
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const checkUploadForm = async (
	token: string,
	request: FormCheckRequest
): Promise<FormCheckResult> => {
	let error = null;

	const body = new FormData();
	body.set('domain', request.domain);
	if (request.fileType) {
		body.set('file_type', request.fileType);
	}
	body.set('file', request.file);

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/uploads/form-check`, {
		method: 'POST',
		headers: { Accept: 'application/json', authorization: `Bearer ${token}` },
		body
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getPendingUpload = async (
	token: string,
	pendingId: string
): Promise<PendingUpload> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/uploads/${pendingId}`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deletePendingUpload = async (token: string, pendingId: string): Promise<void> => {
	let error = null;

	await fetch(`${DATA_PORTAL_API_BASE_URL}/uploads/${pendingId}`, {
		method: 'DELETE',
		headers: jsonHeaders(token)
	})
		.then(checkStatus)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
		});

	if (error) {
		throw error;
	}
};

export const confirmPendingUpload = async (
	token: string,
	pendingId: string
): Promise<ConfirmedUpload> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/uploads/${pendingId}/confirm`, {
		method: 'POST',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getLoads = async (token: string, filter: LoadFilter): Promise<LoadList> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/loads${toQueryString(filter)}`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getLoad = async (token: string, loadId: number): Promise<Load> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteLoad = async (token: string, loadId: number): Promise<void> => {
	let error = null;

	await fetch(`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}`, {
		method: 'DELETE',
		headers: jsonHeaders(token)
	})
		.then(checkStatus)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
		});

	if (error) {
		throw error;
	}
};

export const getLoadReconciliation = async (
	token: string,
	loadId: number,
	query: ReconcileQuery = {}
): Promise<{ cards: ReconcileCard[] }> => {
	let error = null;

	const res = await fetch(
		`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}/reconcile${toQueryString(query)}`,
		{
			method: 'GET',
			headers: jsonHeaders(token)
		}
	)
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const downloadLoadErrors = async (token: string, loadId: number): Promise<DownloadedFile> =>
	downloadFile(
		token,
		`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}/errors.csv`,
		`load-${loadId}-errors.csv`
	);

export const downloadLoadFile = async (
	token: string,
	loadId: number,
	fallbackName: string
): Promise<DownloadedFile> =>
	downloadFile(token, `${DATA_PORTAL_API_BASE_URL}/loads/${loadId}/file`, fallbackName);

export const getLoadFileSheets = async (token: string, loadId: number): Promise<SourceSheet[]> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}/file/sheets`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getLoadFileSheet = async (
	token: string,
	loadId: number,
	index: number,
	page: number,
	pageSize: number
): Promise<SourceSheetPage> => {
	let error = null;

	const query = toQueryString({ page, page_size: pageSize });
	const res = await fetch(
		`${DATA_PORTAL_API_BASE_URL}/loads/${loadId}/file/sheets/${index}${query}`,
		{
			method: 'GET',
			headers: jsonHeaders(token)
		}
	)
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getTables = async (
	token: string,
	domain: string,
	year: string
): Promise<TableSummary[]> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/tables${toQueryString({ domain, year })}`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getTable = async (
	token: string,
	table: string,
	filter: TableFilter,
	page: number,
	pageSize: number
): Promise<TableData> => {
	let error = null;

	const query = toQueryString({ ...filter, page, page_size: pageSize });
	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/tables/${table}${query}`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const exportTable = async (
	token: string,
	table: string,
	filter: TableFilter
): Promise<DownloadedFile> =>
	downloadFile(
		token,
		`${DATA_PORTAL_API_BASE_URL}/tables/${table}/export.xlsx${toQueryString(filter)}`,
		`${table}.xlsx`
	);

export const getPortalStatus = async (token: string): Promise<PortalStatus> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/status`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDbConfig = async (token: string): Promise<DbConfig> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/db-config`, {
		method: 'GET',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const testDbConfig = async (token: string, form: DbConfigForm): Promise<DbConfigResult> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/db-config/test`, {
		method: 'POST',
		headers: jsonHeaders(token),
		body: JSON.stringify(form)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateDbConfig = async (
	token: string,
	form: DbConfigForm
): Promise<DbConfigResult> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/db-config`, {
		method: 'PUT',
		headers: jsonHeaders(token),
		body: JSON.stringify(form)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteDbConfig = async (token: string): Promise<{ message: string }> => {
	let error = null;

	const res = await fetch(`${DATA_PORTAL_API_BASE_URL}/db-config`, {
		method: 'DELETE',
		headers: jsonHeaders(token)
	})
		.then(readJson)
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

const downloadFile = async (
	token: string,
	url: string,
	fallbackName: string
): Promise<DownloadedFile> => {
	let error = null;

	const res = await fetch(url, {
		method: 'GET',
		headers: { authorization: `Bearer ${token}` }
	})
		.then(checkStatus)
		.then(async (res) => ({
			blob: await res.blob(),
			fileName: fileNameFromHeader(res.headers.get('content-disposition')) ?? fallbackName,
			rowCount: rowCountFromHeader(res.headers.get('x-row-count'))
		}))
		.catch((err) => {
			error = toApiError(err);
			console.error(err);
			return null;
		});

	if (error || !res) {
		throw error;
	}

	return res;
};

const jsonHeaders = (token: string) => ({
	Accept: 'application/json',
	'Content-Type': 'application/json',
	authorization: `Bearer ${token}`
});

const toQueryString = (params: Record<string, string | number | null | undefined>) => {
	const searchParams = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== null && value !== '') {
			searchParams.set(key, String(value));
		}
	}
	const query = searchParams.toString();
	return query ? `?${query}` : '';
};

const checkStatus = async (res: Response) => {
	if (!res.ok) {
		throw await readError(res);
	}
	return res;
};

const readJson = async (res: Response) => {
	await checkStatus(res);
	if (res.status === 204) {
		return null;
	}
	const text = await res.text();
	return text ? JSON.parse(text) : null;
};

const readError = async (res: Response) => {
	try {
		const body = await res.json();
		const detail = body?.detail ?? body?.message ?? connectionLostMessage();
		const message = typeof detail === 'string' ? detail : JSON.stringify(detail);
		return new DataPortalApiError(res.status, message, body?.field_errors ?? null);
	} catch {
		return new DataPortalApiError(res.status, connectionLostMessage());
	}
};

const toApiError = (err: unknown) =>
	err instanceof DataPortalApiError ? err : new DataPortalApiError(0, connectionLostMessage());

const connectionLostMessage = () =>
	get(portalI18n).t('Connection lost; the processing result could not be determined.');

const fileNameFromHeader = (header: string | null) => {
	const match = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(header ?? '');
	return match ? decodeURIComponent(match[1] ?? match[2]) : null;
};

const rowCountFromHeader = (header: string | null) => {
	const rowCount = Number(header ?? NaN);
	return Number.isNaN(rowCount) ? null : rowCount;
};
