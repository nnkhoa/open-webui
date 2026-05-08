import { writable } from 'svelte/store';

export const projectConfig = writable({
	logo_url: null as string | null,
	model_display_names: {} as Record<string, string>,
	brand_color: null as string | null,
	org_name: 'Nova Consumer Group' as string,
	org_subtitle: 'Chương trình tư vấn chiến lược AI' as string,
	app_name: '' as string,
	enable_new_chat_on_model_change: true as boolean
});
