import { WEBUI_API_BASE_URL } from '$lib/constants';

export interface ProjectConfig {
	logo_url: string | null;
	model_display_names: Record<string, string>;
	brand_color: string | null;
	org_name: string;
	org_subtitle: string;
}

export const getProjectConfig = async (token: string): Promise<ProjectConfig> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/configs/project`, {
		method: 'GET',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const setProjectConfig = async (
	token: string,
	config: Partial<ProjectConfig>
): Promise<ProjectConfig> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/configs/project`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ ...config })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const uploadProjectLogo = async (
	token: string,
	file: File
): Promise<{ logo_url: string }> => {
	let error = null;

	const formData = new FormData();
	formData.append('file', file);

	const res = await fetch(`${WEBUI_API_BASE_URL}/configs/project/logo`, {
		method: 'POST',
		headers: {
			Authorization: `Bearer ${token}`
		},
		body: formData
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteProjectLogo = async (
	token: string
): Promise<{ logo_url: null }> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/configs/project/logo`, {
		method: 'DELETE',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			console.error(err);
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
