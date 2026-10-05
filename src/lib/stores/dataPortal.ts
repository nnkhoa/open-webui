import { get, writable } from 'svelte/store';

import { getDomains } from '$lib/apis/data-portal';
import type { Domain } from '$lib/apis/data-portal/types';

export const DATA_PORTAL_ROLES = ['admin', 'data_uploader'];
export const DATA_YEARS = ['2025', '2026', '2027', '2028', '2029', '2030', '2031'];

export const selectedDomain = writable<string>('HQKD');
export const selectedYear = writable<string>('');

export const portalDomains = writable<Domain[]>([]);

export type UploadDraft = {
	domain: string;
	year: string;
	fileType: string;
	file: File | null;
	selectedAt: string;
};

const EMPTY_UPLOAD_DRAFT: UploadDraft = {
	domain: '',
	year: '',
	fileType: '',
	file: null,
	selectedAt: ''
};

export const uploadDraft = writable<UploadDraft>({ ...EMPTY_UPLOAD_DRAFT });

export const resetUploadDraft = () => uploadDraft.set({ ...EMPTY_UPLOAD_DRAFT });

export const loadPortalDomains = async () => {
	if (!get(portalDomains).length) {
		portalDomains.set(await getDomains(localStorage.token));
	}
};

export const hasMultipleFileTypes = (domain: Domain | undefined) =>
	(domain?.file_types.length ?? 0) > 1;
