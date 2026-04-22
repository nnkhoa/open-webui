import { writable } from 'svelte/store';

export const projectConfig = writable({
	logo_url: null as string | null,
	model_display_names: {} as Record<string, string>,
	brand_color: null as string | null
});
