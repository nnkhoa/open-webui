<script lang="ts">
	import { WEBUI_BASE_URL } from '$lib/constants';
	import { OPEN_WEBUI_LOGO_PATH, OPEN_WEBUI_NAME } from '$lib/branding';

	export let className = '';
</script>

<div class="flex items-center gap-2 select-none {className}">
	<img
		src="{WEBUI_BASE_URL}{OPEN_WEBUI_LOGO_PATH}"
		class="size-6 rounded-full"
		alt=""
		draggable="false"
	/>
	<span class="hidden sm:inline text-sm font-medium font-primary text-gray-850 dark:text-white">
		{OPEN_WEBUI_NAME}
	</span>
</div>
