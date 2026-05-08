<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { getSidebarPrompts, setSidebarPrompts } from '$lib/apis/ai4bi';

	const i18n = getContext('i18n');

	export let saveHandler: Function | undefined = undefined;

	let signalsPrompt = '';
	let heartbeatPrompt = '';
	let loading = true;
	let saving = false;

	onMount(async () => {
		try {
			const data = await getSidebarPrompts(localStorage.token);
			signalsPrompt = data?.signals_prompt ?? '';
			heartbeatPrompt = data?.heartbeat_prompt ?? '';
		} catch (e) {
			toast.error((e as { detail?: string })?.detail ?? 'Failed to load prompts');
		} finally {
			loading = false;
		}
	});

	const save = async () => {
		saving = true;
		try {
			await setSidebarPrompts(localStorage.token, {
				signals_prompt: signalsPrompt,
				heartbeat_prompt: heartbeatPrompt
			});
			toast.success('Sidebar prompts saved');
			if (saveHandler) saveHandler();
		} catch (e) {
			toast.error((e as { detail?: string })?.detail ?? 'Failed to save prompts');
		} finally {
			saving = false;
		}
	};
</script>

<form
	class="flex flex-col h-full justify-between space-y-3 text-sm"
	on:submit|preventDefault={save}
>
	<div class="space-y-4 overflow-y-scroll max-h-[24rem] lg:max-h-full pr-2">
		<div>
			<div class="mb-2 text-sm font-medium">User role left sidebar prompt</div>
			<div class="text-xs text-gray-500 mb-3">
				Applied globally to every User. Each User's sidebar only generates information from
				the tables their group has been granted access to. Leave empty = User sees no
				sidebar information.
			</div>
		</div>

		<div>
			<label class="text-xs font-medium mb-1 block" for="ai4bi-signals-prompt">
				Prompt for "Signals" section
			</label>
			<textarea
				id="ai4bi-signals-prompt"
				class="w-full rounded-lg p-3 text-sm bg-white dark:text-gray-300 dark:bg-gray-850 outline-none border border-gray-100 dark:border-gray-800 resize-vertical"
				rows="10"
				placeholder="e.g. You are a Senior Data Analyst. Analyse the granted tables and produce 3-5 signals (critical/watch/positive). Return a JSON array with: type, title, desc, fingerprint."
				bind:value={signalsPrompt}
				disabled={loading}
			/>
		</div>

		<div>
			<label class="text-xs font-medium mb-1 block" for="ai4bi-heartbeat-prompt">
				Prompt for "Heartbeat" section
			</label>
			<textarea
				id="ai4bi-heartbeat-prompt"
				class="w-full rounded-lg p-3 text-sm bg-white dark:text-gray-300 dark:bg-gray-850 outline-none border border-gray-100 dark:border-gray-800 resize-vertical"
				rows="10"
				placeholder="e.g. Generate 4-8 heartbeat KPIs from the granted tables. Return a JSON array with: label, value, delta, trend (up/down/neutral)."
				bind:value={heartbeatPrompt}
				disabled={loading}
			/>
		</div>
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button
			class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full disabled:opacity-50"
			type="submit"
			disabled={loading || saving}
		>
			{saving ? 'Saving...' : 'Save'}
		</button>
	</div>
</form>
