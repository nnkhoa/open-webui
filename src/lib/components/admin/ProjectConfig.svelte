<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { models } from '$lib/stores';
	import { projectConfig } from '$lib/stores/projectConfig';
	import {
		getProjectConfig,
		setProjectConfig,
		uploadProjectLogo,
		deleteProjectLogo
	} from '$lib/apis/configs/project';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import { WEBUI_BASE_URL } from '$lib/constants';

	const i18n = getContext('i18n');

	let loading = true;
	let saving = false;

	// Local state
	let logoUrl: string | null = null;
	let displayNames: Record<string, string> = {};
	let brandColor = '';
	let logoFileInput: HTMLInputElement;

	// Get models list for display name editing
	$: availableModels = ($models ?? []).map((m) => ({
		id: m.id,
		name: m.name,
		displayName: displayNames[m.id] || ''
	}));

	const init = async () => {
		try {
			const config = await getProjectConfig(localStorage.token);
			logoUrl = config.logo_url;
			displayNames = config.model_display_names || {};
			brandColor = config.brand_color || '';

			await projectConfig.set({
				logo_url: config.logo_url,
				model_display_names: config.model_display_names || {},
				brand_color: config.brand_color || ''
			});
		} catch (err) {
			console.error('Failed to load project config:', err);
			toast.error('Failed to load project config');
		}
		loading = false;
	};

	const handleLogoUpload = async (event: Event) => {
		const input = event.target as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;

		try {
			const result = await uploadProjectLogo(localStorage.token, file);
			logoUrl = result.logo_url;
			await projectConfig.update((c) => ({ ...c, logo_url: result.logo_url }));
			toast.success('Logo uploaded');
		} catch (err) {
			toast.error('Failed to upload logo');
		}
		input.value = '';
	};

	const handleLogoDelete = async () => {
		try {
			await deleteProjectLogo(localStorage.token);
			logoUrl = null;
			await projectConfig.update((c) => ({ ...c, logo_url: null }));
			toast.success('Logo removed');
		} catch (err) {
			toast.error('Failed to remove logo');
		}
	};

	const handleDisplayNameChange = (modelId: string, value: string) => {
		if (value.trim()) {
			displayNames = { ...displayNames, [modelId]: value.trim() };
		} else {
			const updated = { ...displayNames };
			delete updated[modelId];
			displayNames = updated;
		}
	};

	const save = async () => {
		saving = true;
		try {
			const config = await setProjectConfig(localStorage.token, {
				logo_url: logoUrl,
				model_display_names: displayNames,
				brand_color: brandColor || null
			});

			await projectConfig.set({
				logo_url: config.logo_url,
				model_display_names: config.model_display_names || {},
				brand_color: config.brand_color || ''
			});

			toast.success('Project config saved');
		} catch (err) {
			toast.error('Failed to save project config');
		}
		saving = false;
	};

	onMount(() => {
		init();
	});
</script>

{#if loading}
	<div class="flex justify-center py-8">
		<Spinner className="size-6" />
	</div>
{:else}
	<div class="flex flex-col h-full justify-between space-y-4 text-sm max-w-4xl">
		<div class="overflow-y-auto scrollbar-hidden h-full pr-1.5 space-y-6">
			<!-- Section: Logo -->
			<div>
				<div class="mt-0.5 mb-2.5 text-base font-medium">Logo</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="flex items-center gap-4 mt-3">
					<div class="shrink-0">
						{#if logoUrl}
							<img
								src={`${WEBUI_BASE_URL}${logoUrl}`}
								alt="Project logo"
								class="h-14 w-14 rounded-xl object-cover border border-slate-200 shadow-sm"
							/>
						{:else}
							<div
								class="h-14 w-14 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center border border-slate-200"
							>
								<svg
									class="h-6 w-6 text-gray-400"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
								>
									<rect x="3" y="3" width="18" height="18" rx="2" />
									<circle cx="8.5" cy="8.5" r="1.5" />
									<path d="M21 15l-5-5L5 21" />
								</svg>
							</div>
						{/if}
					</div>

					<div class="flex flex-col gap-2">
						<div class="flex gap-2">
							<button
								class="px-3 py-1.5 text-xs font-medium rounded-lg bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200 transition"
								on:click={() => logoFileInput.click()}
							>
								Upload Logo
							</button>
							{#if logoUrl}
								<button
									class="px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950 transition"
									on:click={handleLogoDelete}
								>
									Remove
								</button>
							{/if}
						</div>
						<p class="text-xs text-gray-500 dark:text-gray-400"
							>PNG, JPG, SVG, WebP.</p
						>
					</div>

					<input
						bind:this={logoFileInput}
						type="file"
						accept="image/png,image/jpeg,image/svg+xml,image/webp,image/gif"
						class="hidden"
						on:change={handleLogoUpload}
					/>
				</div>
			</div>

			<!-- Section: Brand Color -->
			<div>
				<div class="mt-0.5 mb-2.5 text-base font-medium">Brand Color</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

				<div class="flex items-center gap-3 mt-3">
					<input
						type="color"
						bind:value={brandColor}
						class="h-10 w-14 rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer"
					/>
					<input
						type="text"
						bind:value={brandColor}
						placeholder="#19226D"
						class="w-32 px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-transparent dark:bg-gray-900"
					/>
					{#if brandColor}
						<span class="text-sm font-medium" style="color: {brandColor}"
							>Preview text</span
						>
					{/if}
					{#if brandColor}
						<button
							class="px-2 py-1 text-xs rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
							on:click={() => (brandColor = '')}
						>
							Reset
						</button>
					{/if}
				</div>
				<p class="text-xs text-gray-500 dark:text-gray-400 mt-1.5"
					>Applied to headings and accent text across the UI.</p
				>
			</div>

			<!-- Section: Model Display Names -->
			<div>
				<div class="mt-0.5 mb-2.5 text-base font-medium">Model Display Names</div>
				<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />
				<p class="text-xs text-gray-500 dark:text-gray-400 mb-3"
					>Rename models for display purposes. The underlying model ID is not changed.</p
				>

				{#if availableModels.length === 0}
					<div class="text-gray-400 text-sm py-4 text-center">No models available.</div>
				{:else}
					<div class="space-y-2">
						{#each availableModels as model}
							<div
								class="flex items-center gap-3 px-3 py-2 rounded-xl bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800"
							>
								<div class="flex-1 min-w-0">
									<div class="text-xs text-gray-500 dark:text-gray-400 font-mono truncate"
										>{model.id}</div
									>
									<div class="text-sm text-gray-700 dark:text-gray-300 truncate"
										>{model.name}</div
									>
								</div>
								<div class="w-48 shrink-0">
									<input
										type="text"
										value={model.displayName}
										placeholder="Display name..."
										on:change={(e) =>
											handleDisplayNameChange(model.id, e.target.value)}
										class="w-full px-2.5 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-gray-950"
									/>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<!-- Save Button -->
		<div class="pt-3 border-t border-gray-100 dark:border-gray-800">
			<button
				class="px-5 py-2.5 text-sm font-medium rounded-xl bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200 transition disabled:opacity-50"
				on:click={save}
				disabled={saving}
			>
				{#if saving}
					Saving...
				{:else}
					Save Changes
				{/if}
			</button>
		</div>
	</div>
{/if}
