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
	let orgName = '';
	let orgSubtitle = '';
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
			orgName = config.org_name || 'Nova Consumer Group';
			orgSubtitle = config.org_subtitle || 'Chương trình tư vấn chiến lược AI';

			await projectConfig.set({
				logo_url: config.logo_url,
				model_display_names: config.model_display_names || {},
				brand_color: config.brand_color || '',
				org_name: orgName,
				org_subtitle: orgSubtitle
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
				brand_color: brandColor || null,
				org_name: orgName,
				org_subtitle: orgSubtitle
			});

			await projectConfig.set({
				logo_url: config.logo_url,
				model_display_names: config.model_display_names || {},
				brand_color: config.brand_color || '',
				org_name: config.org_name || 'Nova Consumer Group',
				org_subtitle: config.org_subtitle || 'Chương trình tư vấn chiến lược AI'
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
	<div class="flex flex-col h-full max-w-5xl mx-auto px-6 py-6">
		<div class="overflow-y-auto scrollbar-hidden h-full space-y-5">
			<!-- Section: Logo -->
			<div
				class="rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-5"
			>
				<h3 class="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">Logo</h3>
				<p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
					Upload a project logo. Displayed in favicon and chat interface.
				</p>

				<div class="flex items-center gap-4">
					<div class="shrink-0">
						{#if logoUrl}
							<img
								src={`${WEBUI_BASE_URL}${logoUrl}`}
								alt="Project logo"
								class="h-16 w-16 rounded-xl object-cover border border-gray-200 dark:border-gray-700 shadow-sm"
							/>
						{:else}
							<div
								class="h-16 w-16 rounded-xl bg-gray-50 dark:bg-gray-800 flex items-center justify-center border border-dashed border-gray-300 dark:border-gray-600"
							>
								<svg
									class="h-7 w-7 text-gray-400"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.5"
								>
									<path d="M12 16V4m0 0l-3 3m3-3l3 3" />
									<path d="M2 17l.621 2.485A2 2 0 004.561 21h14.878a2 2 0 001.94-1.515L22 17" />
								</svg>
							</div>
						{/if}
					</div>

					<div class="flex flex-col gap-1.5">
						<div class="flex gap-2">
							<button
								class="px-3 py-1.5 text-xs font-medium rounded-lg bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200 transition"
								on:click={() => logoFileInput.click()}
							>
								Upload
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
						<p class="text-xs text-gray-400 dark:text-gray-500">PNG, JPG, SVG, WebP</p>
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

			<!-- Section: Organization Name & Subtitle -->
			<div
				class="rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-5"
			>
				<h3 class="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
					Organization Info
				</h3>
				<p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
					Displayed in the header next to the project logo.
				</p>

				<div class="space-y-3">
					<div>
						<label
							for="org-name-input"
							class="block text-xs text-gray-600 dark:text-gray-400 mb-1"
						>
							Organization Name
						</label>
						<input
							id="org-name-input"
							type="text"
							bind:value={orgName}
							placeholder="Nova Consumer Group"
							class="w-full px-2.5 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-black dark:focus:ring-white"
						/>
					</div>
					<div>
						<label
							for="org-subtitle-input"
							class="block text-xs text-gray-600 dark:text-gray-400 mb-1"
						>
							Subtitle
						</label>
						<input
							id="org-subtitle-input"
							type="text"
							bind:value={orgSubtitle}
							placeholder="Chương trình tư vấn chiến lược AI"
							class="w-full px-2.5 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 focus:outline-none focus:ring-1 focus:ring-black dark:focus:ring-white"
						/>
					</div>
				</div>
			</div>

			<!-- Section: Brand Color -->
			<div
				class="rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-5"
			>
				<h3 class="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">Brand Color</h3>
				<p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
					Color of the organization name ("{orgName || 'Nova Consumer Group'}") in the header.
				</p>

				<div class="flex items-center gap-3">
					<div class="relative">
						<input
							type="color"
							bind:value={brandColor}
							class="h-9 w-12 rounded-lg border border-gray-200 dark:border-gray-700 cursor-pointer bg-transparent"
						/>
					</div>
					<input
						type="text"
						bind:value={brandColor}
						placeholder="#86c52e"
						class="w-28 px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
					/>
					{#if brandColor}
						<span
							class="text-xs font-medium px-2.5 py-1 rounded-md"
							style="color: {brandColor}; background: {brandColor}15;"
						>
							Preview
						</span>
						<button
							class="px-2 py-1 text-xs rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
							on:click={() => (brandColor = '')}
						>
							Reset
						</button>
					{/if}
				</div>
			</div>

			<!-- Section: Model Display Names -->
			<div
				class="rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-5"
			>
				<h3 class="text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
					Model Display Names
				</h3>
				<p class="text-xs text-gray-500 dark:text-gray-400 mb-4">
					Rename models for display. The underlying model ID is not changed.
				</p>

				{#if availableModels.length === 0}
					<div class="text-gray-400 text-xs py-4 text-center">No models available.</div>
				{:else}
					<div class="space-y-1.5">
						{#each availableModels as model}
							<div
								class="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-800"
							>
								<div class="flex-1 min-w-0">
									<div class="text-[11px] text-gray-400 dark:text-gray-500 font-mono truncate">
										{model.id}
									</div>
									<div class="text-xs text-gray-600 dark:text-gray-300 truncate">{model.name}</div>
								</div>
								<div class="w-36 shrink-0">
									<input
										type="text"
										value={model.displayName}
										placeholder="Display name..."
										on:change={(e) => handleDisplayNameChange(model.id, e.target.value)}
										class="w-full px-2 py-1 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 focus:outline-none focus:ring-1 focus:ring-black dark:focus:ring-white"
									/>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<!-- Save Button -->
		<div class="pt-4 mt-2 border-t border-gray-100 dark:border-gray-800">
			<button
				class="px-4 py-2 text-xs font-medium rounded-xl bg-black text-white hover:bg-gray-800 dark:bg-white dark:text-black dark:hover:bg-gray-200 transition disabled:opacity-50"
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
