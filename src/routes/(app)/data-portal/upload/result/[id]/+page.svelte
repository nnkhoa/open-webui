<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import {
		hasMultipleFileTypes,
		loadPortalDomains,
		portalDomains,
		resetUploadDraft
	} from '$lib/stores/dataPortal';
	import { getLoad } from '$lib/apis/data-portal';
	import type { Load } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Collapsible from '$lib/components/data-portal/Collapsible.svelte';
	import StepsCard from '$lib/components/data-portal/StepsCard.svelte';
	import ReconcileCards from '$lib/components/data-portal/ReconcileCards.svelte';
	import ErrorsCard from '$lib/components/data-portal/ErrorsCard.svelte';
	import LoadInfoCard from '$lib/components/data-portal/LoadInfoCard.svelte';
	import { formatNumber, LOAD_STATUS_BADGES } from '$lib/components/data-portal/format';

	const i18n: Writable<i18nType> = getContext('i18n');

	const FALLBACK_TABLE = 'fact_ket_qua_kd';
	const CHECK_STEP = 1;
	const RECONCILE_STEP = 3;

	let load: Load | null = null;
	let errorMessage = '';
	let stepsOpen = false;
	let reconcileOpen = false;

	$: loadId = Number($page.params.id);
	$: multipleFileTypes = hasMultipleFileTypes(
		$portalDomains.find((domain) => domain.code === load?.domain)
	);
	$: statusBadge = load ? LOAD_STATUS_BADGES[load.status] : null;
	$: failedStep =
		load?.status === 'rejected' ? CHECK_STEP : load?.status === 'mismatch' ? RECONCILE_STEP : -1;

	onMount(async () => {
		try {
			await loadPortalDomains();
			load = await getLoad(localStorage.token, loadId);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	});

	const uploadAnother = () => {
		resetUploadDraft();
		goto('/data-portal/upload');
	};

	const viewUploadedData = () =>
		load &&
		goto(`/data-portal/data/${load.primary_table ?? FALLBACK_TABLE}?layer=gold&year=${load.year}`);
</script>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !load}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else}
	<HeaderCard
		title={$i18n.t('Upload result · upload #{{id}}', { id: load.id })}
		description={load.file_name}
	>
		<span slot="after"
			>{#if statusBadge}<Badge
					label={$i18n.t(statusBadge.label)}
					tone={statusBadge.tone}
				/>{/if}</span
		>
		<svelte:fragment slot="actions">
			<button type="button" class="btn" on:click={() => goto('/data-portal/history')}
				>{$i18n.t('Back to upload history')}</button
			>
			{#if load.status === 'success'}
				<button
					type="button"
					class="btn"
					title={$i18n.t('Go back to step 1 to upload the next file')}
					on:click={uploadAnother}>{$i18n.t('Upload another file')}</button
				>
				<button type="button" class="btn primary" on:click={viewUploadedData}
					>{$i18n.t('View the uploaded data')}</button
				>
			{:else if load.status === 'rejected'}
				<button
					type="button"
					class="btn primary"
					title={$i18n.t('Go back to step 1 to choose the corrected file')}
					on:click={uploadAnother}>{$i18n.t('Choose the corrected file')}</button
				>
			{:else}
				<button
					type="button"
					class="btn primary"
					on:click={() => goto(`/data-portal/history/${load?.id}?tab=reconcile`)}
					>{$i18n.t('View upload details')}</button
				>
			{/if}
		</svelte:fragment>
	</HeaderCard>

	<StepBar current={4} {failedStep} withFileType={multipleFileTypes} />

	<LoadInfoCard {load} />

	{#if load.status === 'success'}
		<Banner
			tone="ok"
			icon="check"
			big
			title={$i18n.t('Data uploaded successfully')}
			description={$i18n.t(
				'{{rows}} rows went into the database. Every reconciliation step matched.',
				{ rows: formatNumber(load.rows_written) }
			)}
		/>
	{:else if load.status === 'rejected'}
		<Banner
			tone="err"
			icon="x"
			big
			title={$i18n.t('The file was not processed')}
			description={$i18n.t('The file has {{count}} errors; nothing was written to the database.', {
				count: load.errors.length
			})}
		/>
		<ErrorsCard loadId={load.id} errors={load.errors} />
	{:else}
		<Banner
			tone="err"
			icon="alert"
			big
			title={$i18n.t('Differences found during reconciliation')}
			description={$i18n.t('Everything was cancelled; existing data is unchanged.')}
		/>
	{/if}

	<Collapsible title={$i18n.t('Processing steps')} bind:open={stepsOpen}>
		<StepsCard steps={load.steps} />
	</Collapsible>
	{#if load.status !== 'rejected'}
		<Collapsible title={$i18n.t('Reconcile source file ↔ database')} bind:open={reconcileOpen}>
			<ReconcileCards loadId={load.id} year={load.year} />
		</Collapsible>
	{/if}
{/if}
