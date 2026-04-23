import { WEBUI_API_BASE_URL } from '$lib/constants';

const AI4BI_API_BASE_URL = `${WEBUI_API_BASE_URL}/ai4bi`;

const parseJson = async (response: Response) => {
	if (!response.ok) {
		let error: { detail?: string } | null = null;
		try {
			error = await response.json();
		} catch {
			error = { detail: `HTTP ${response.status}` };
		}
		throw error;
	}
	return response.json();
};

export const getSidebarSignals = async (
	token: string,
	{
		limit = 4,
		offset = 0,
		instruction = ''
	}: { limit?: number; offset?: number; instruction?: string } = {}
) => {
	const searchParams = new URLSearchParams({
		limit: String(limit),
		offset: String(offset)
	});

	if (instruction.trim()) {
		searchParams.set('instruction', instruction.trim());
	}

	return fetch(`${AI4BI_API_BASE_URL}/signals?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token ? { authorization: `Bearer ${token}` } : {})
		}
	}).then(parseJson);
};

export const getSidebarHeartbeat = async (
	token: string,
	{
		limit = 4,
		offset = 0,
		instruction = ''
	}: { limit?: number; offset?: number; instruction?: string } = {}
) => {
	const searchParams = new URLSearchParams({
		limit: String(limit),
		offset: String(offset)
	});

	if (instruction.trim()) {
		searchParams.set('instruction', instruction.trim());
	}

	return fetch(`${AI4BI_API_BASE_URL}/heartbeat?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			...(token ? { authorization: `Bearer ${token}` } : {})
		}
	}).then(parseJson);
};
