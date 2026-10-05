<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { toast } from 'svelte-sonner';

	import { ADMIN_ROLE } from '$lib/constants';
	import { user } from '$lib/stores';
	import { hasMultipleFileTypes, loadPortalDomains, portalDomains } from '$lib/stores/dataPortal';
	import { deleteLoad, getLoad } from '$lib/apis/data-portal';
	import type { Load } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Tabs from '$lib/components/data-portal/Tabs.svelte';
	import StepsCard from '$lib/components/data-portal/StepsCard.svelte';
	import ReconcileCards from '$lib/components/data-portal/ReconcileCards.svelte';
	import ErrorsCard from '$lib/components/data-portal/ErrorsCard.svelte';
	import LoadInfoCard from '$lib/components/data-portal/LoadInfoCard.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import { formatNumber, LOAD_STATUS_BADGES } from '$lib/components/data-portal/format';

	const i18n: Writable<i18nType> = getContext('i18n');

	let load: Load | null = null;
	let errorMessage = '';
	let pendingAction: '' | 'rollback' | 'delete' = '';
	let busy = false;

	$: loadId = Number($page.params.id);
	$: tab = $page.url.searchParams.get('tab') ?? 'steps';
	$: isAdmin = $user?.role === ADMIN_ROLE;
	$: multipleFileTypes = hasMultipleFileTypes(
		$portalDomains.find((domain) => domain.code === load?.domain)
	);
	$: statusBadge = load ? LOAD_STATUS_BADGES[load.status] : null;

	onMount(async () => {
		try {
			await loadPortalDomains();
			load = await getLoad(localStorage.token, loadId);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	});

	const changeTab = (target: string) =>
		goto(`/data-portal/history/${loadId}?tab=${target}`, { replaceState: true, noScroll: true });

	const viewData = () => {
		if (!load) return;
		if (multipleFileTypes)
			goto(`/data-portal/data/${load.primary_table}?layer=gold&year=${load.year}`);
		else goto(`/data-portal/data?year=${load.year}`);
	};

	const removeLoad = async () => {
		busy = true;
		try {
			await deleteLoad(localStorage.token, loadId);
			pendingAction = '';
			goto('/data-portal/history');
		} catch (error) {
			pendingAction = '';
			toast.error((error as Error).message);
		} finally {
			busy = false;
		}
	};
</script>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !load}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else}
	<HeaderCard
		title={$i18n.t('Upload #{{id}}', { id: load.id })}
		description={load.file_name}
		back={() => goto('/data-portal/history')}
	>
		<span slot="after"
			>{#if statusBadge}<Badge
					label={$i18n.t(statusBadge.label)}
					tone={statusBadge.tone}
				/>{/if}</span
		>
		<svelte:fragment slot="actions">
			{#if isAdmin}
				{#if load.status === 'success'}
					<button
						type="button"
						class="btn danger"
						title={$i18n.t('Permanently delete the data of this upload from the database')}
						on:click={() => (pendingAction = 'rollback')}>{$i18n.t('Roll back data')}</button
					>
				{:else}
					<button type="button" class="btn danger" on:click={() => (pendingAction = 'delete')}
						>{$i18n.t('Delete history')}</button
					>
				{/if}
			{/if}
			<button type="button" class="btn" on:click={() => goto(`/data-portal/history/${loadId}/file`)}
				>{$i18n.t('View source file')}</button
			>
			{#if load.status === 'success'}
				<button type="button" class="btn primary" on:click={viewData}
					>{$i18n.t('View related data')}</button
				>
			{/if}
		</svelte:fragment>
	</HeaderCard>

	<LoadInfoCard {load} detailed />

	<Tabs
		active={tab}
		tabs={[
			{ id: 'steps', label: $i18n.t('Processing steps') },
			{ id: 'reconcile', label: $i18n.t('Reconcile source file ↔ database') },
			{ id: 'errors', label: $i18n.t('Errors'), count: load.errors.length }
		]}
		on:change={(event) => changeTab(event.detail)}
	/>

	{#if tab === 'steps'}
		{#if load.status === 'rejected'}
			<Banner
				tone="err"
				icon="x"
				title={$i18n.t('The file was not processed')}
				description={$i18n.t(
					'The file has {{count}} errors; nothing was written to the database.',
					{
						count: load.errors.length
					}
				)}
			/>
		{:else if load.status === 'mismatch'}
			<Banner
				tone="err"
				icon="alert"
				title={$i18n.t('Differences found during reconciliation')}
				description={$i18n.t('Everything was cancelled; existing data is unchanged.')}
			/>
		{/if}
		<StepsCard steps={load.steps} />
	{:else if tab === 'reconcile'}
		<ReconcileCards loadId={load.id} year={load.year} />
	{:else if load.errors.length}
		<ErrorsCard loadId={load.id} errors={load.errors} />
	{:else}
		<Card title={$i18n.t('Errors to fix')}
			><p class="desc">{$i18n.t('This upload has no errors.')}</p></Card
		>
	{/if}
{/if}

{#if pendingAction && load}
	<Dialog
		label={pendingAction === 'rollback' ? $i18n.t('Roll back data') : $i18n.t('Delete history')}
		on:close={() => (pendingAction = '')}
	>
		{#if pendingAction === 'rollback'}
			<h2>{$i18n.t('Roll back the data of upload #{{id}}?', { id: load.id })}</h2>
			<p>
				{$i18n.t(
					'File {{file}} has {{rows}} source rows. All information of this upload will be permanently deleted: data in all three layers (raw, standardized, analytics), reconciliation results, history and the uploaded file. If this upload replaced the data of a previous upload ({{scope}}), the previous data is used again.',
					{
						file: load.file_name,
						rows: formatNumber(load.total_rows),
						scope: multipleFileTypes ? $i18n.t('same file type') : $i18n.t('same month')
					}
				)}
			</p>
		{:else}
			<h2>{$i18n.t('Delete upload #{{id}} from history?', { id: load.id })}</h2>
			<p>
				{$i18n.t(
					'This deletes the history record of file {{file}}. This file has no data in use.',
					{ file: load.file_name }
				)}
			</p>
		{/if}
		<div class="row" style="justify-content:flex-end;margin-top:4px">
			<button type="button" class="btn" on:click={() => (pendingAction = '')}
				>{$i18n.t('Dismiss')}</button
			>
			<button type="button" class="btn danger-solid" disabled={busy} on:click={removeLoad}
				>{pendingAction === 'rollback'
					? $i18n.t('Roll back data')
					: $i18n.t('Delete history')}</button
			>
		</div>
	</Dialog>
{/if}
