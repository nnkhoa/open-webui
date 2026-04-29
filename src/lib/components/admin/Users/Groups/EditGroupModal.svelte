<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import General from './General.svelte';
	import Permissions from './Permissions.svelte';
	import Users from './Users.svelte';
	import AI4BIConfig from './AI4BIConfig.svelte';
	import { DEFAULT_PERMISSIONS } from '$lib/constants/permissions';
	import UserPlusSolid from '$lib/components/icons/UserPlusSolid.svelte';
	import WrenchSolid from '$lib/components/icons/WrenchSolid.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	export let onSubmit: Function = () => {};
	export let onDelete: Function = () => {};

	export let show = false;
	export let edit = false;

	export let group = null;
	export let defaultPermissions = {};

	export let custom = true;

	export let tabs = ['general', 'permissions', 'ai4bi', 'users'];

	let selectedTab = 'general';
	let loading = false;
	let showDeleteConfirmDialog = false;

	let userCount = 0;

	export let name = '';
	export let description = '';
	export let data = {};

	export let permissions = DEFAULT_PERMISSIONS;

	const submitHandler = async () => {
		loading = true;

		const group = {
			name,
			description,
			data,
			permissions
		};

		await onSubmit(group);

		loading = false;
		show = false;
	};

	const init = () => {
		if (group) {
			name = group.name;
			description = group.description;
			const loadedPermissions = group?.permissions ?? {};
			permissions = {
				workspace: { ...DEFAULT_PERMISSIONS.workspace, ...loadedPermissions.workspace },
				sharing: { ...DEFAULT_PERMISSIONS.sharing, ...loadedPermissions.sharing },
				access_grants: { ...DEFAULT_PERMISSIONS.access_grants, ...loadedPermissions.access_grants },
				chat: { ...DEFAULT_PERMISSIONS.chat, ...loadedPermissions.chat },
				features: { ...DEFAULT_PERMISSIONS.features, ...loadedPermissions.features },
				settings: { ...DEFAULT_PERMISSIONS.settings, ...loadedPermissions.settings }
			};
			data = group?.data ?? {};
			if (!data.ai4bi) {
				data.ai4bi = { mcp_url: '', allowed_tables: [], denied_message: '' };
			}

			userCount = group?.member_count ?? 0;
		}
	};

	$: if (show) {
		init();
	}

	onMount(() => {
		selectedTab = tabs[0];
		init();
	});
</script>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		onDelete();
		show = false;
	}}
/>

<Modal size="lg" bind:show>
	<div>
		<div class=" flex justify-between dark:text-gray-100 px-5 pt-4 mb-1.5">
			<div class=" text-lg font-medium self-center font-primary">
				{#if custom}
					{#if edit}
						{$i18n.t('Edit User Group')}
					{:else}
						{$i18n.t('Add User Group')}
					{/if}
				{:else}
					{$i18n.t('Edit Default Permissions')}
				{/if}
			</div>
			<button
				class="self-center"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="flex flex-col md:flex-row w-full px-4 pb-4 md:space-x-4 dark:text-gray-200">
			<div class=" flex flex-col w-full sm:flex-row sm:justify-center sm:space-x-6">
				<form
					class="flex flex-col w-full"
					on:submit={(e) => {
						e.preventDefault();
						submitHandler();
					}}
				>
					<div class="flex flex-col lg:flex-row w-full h-full pb-2 lg:space-x-4">
						<div
							id="admin-settings-tabs-container"
							class="tabs flex flex-row overflow-x-auto gap-2.5 max-w-full lg:gap-1 lg:flex-col lg:flex-none lg:w-40 dark:text-gray-200 text-sm font-medium text-left scrollbar-none"
						>
							{#if tabs.includes('general')}
								<button
									class="px-0.5 py-1 max-w-fit w-fit rounded-lg flex-1 lg:flex-none flex text-right transition {selectedTab ===
									'general'
										? ''
										: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
									on:click={() => {
										selectedTab = 'general';
									}}
									type="button"
								>
									<div class=" self-center mr-2">⚙️</div>
									<div class=" self-center">{$i18n.t('General')}</div>
								</button>
							{/if}

							{#if tabs.includes('permissions')}
								<button
									class="px-0.5 py-1 max-w-fit w-fit rounded-lg flex-1 lg:flex-none flex text-right transition {selectedTab ===
									'permissions'
										? ''
										: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
									on:click={() => {
										selectedTab = 'permissions';
									}}
									type="button"
								>
									<div class=" self-center mr-2">
										<WrenchSolid />
									</div>
									<div class=" self-center">{$i18n.t('Permissions')}</div>
								</button>
							{/if}

							{#if tabs.includes('ai4bi')}
								<button
									class="px-0.5 py-1 max-w-fit w-fit rounded-lg flex-1 lg:flex-none flex text-right transition {selectedTab ===
									'ai4bi'
										? ''
										: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
									on:click={() => {
										selectedTab = 'ai4bi';
									}}
									type="button"
								>
									<div class=" self-center mr-2">🗃️</div>
									<div class=" self-center">AI4BI Config</div>
								</button>
							{/if}

							{#if tabs.includes('users')}
								<button
									class="px-0.5 py-1 max-w-fit w-fit rounded-lg flex-1 lg:flex-none flex text-right transition {selectedTab ===
									'users'
										? ''
										: ' text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'}"
									on:click={() => {
										selectedTab = 'users';
									}}
									type="button"
								>
									<div class=" self-center mr-2">
										<UserPlusSolid />
									</div>
									<div class=" self-center">{$i18n.t('Users')}</div>
								</button>
							{/if}
						</div>

						<div class="flex-1 mt-1 lg:mt-1 lg:h-[30rem] lg:max-h-[30rem] flex flex-col">
							<div class="w-full h-full overflow-y-auto scrollbar-hidden">
								{#if selectedTab == 'general'}
									<General
										bind:name
										bind:description
										bind:data
										{edit}
										onDelete={() => {
											showDeleteConfirmDialog = true;
										}}
									/>
								{:else if selectedTab == 'permissions'}
									<Permissions bind:permissions {defaultPermissions} />
								{:else if selectedTab == 'ai4bi'}
									<AI4BIConfig bind:data />
								{:else if selectedTab == 'users'}
									<Users bind:userCount groupId={group?.id} />
								{/if}
							</div>

							{#if ['general', 'permissions', 'ai4bi'].includes(selectedTab)}
								<div class="flex justify-end pt-3 text-sm font-medium gap-1.5">
									<button
										class="px-3.5 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full flex items-center gap-2 whitespace-nowrap {loading
											? ' cursor-not-allowed'
											: ''}"
										type="submit"
										disabled={loading}
									>
										{$i18n.t('Save')}

										{#if loading}
											<span class="shrink-0">
												<Spinner />
											</span>
										{/if}
									</button>
								</div>
							{/if}
						</div>
					</div>
				</form>
			</div>
		</div>
	</div>
</Modal>
