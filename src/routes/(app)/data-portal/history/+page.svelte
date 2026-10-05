<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';

	import {
		hasMultipleFileTypes,
		portalDomains,
		resetUploadDraft,
		selectedDomain,
		selectedYear
	} from '$lib/stores/dataPortal';
	import { getLoads } from '$lib/apis/data-portal';
	import type { LoadFilter, LoadList, LoadListItem, LoadStatus } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import DomainYearChips from '$lib/components/data-portal/DomainYearChips.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import SearchBox from '$lib/components/data-portal/SearchBox.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import DataTable, { type TableRow } from '$lib/components/data-portal/DataTable.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import EmptyState from '$lib/components/data-portal/EmptyState.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import {
		formatDateTime,
		formatNumber,
		LOAD_STATUS_BADGES
	} from '$lib/components/data-portal/format';

	const i18n: Writable<i18nType> = getContext('i18n');

	const DETAIL_TABS: Record<LoadStatus, string> = {
		success: 'steps',
		rolled_back: 'steps',
		rejected: 'errors',
		mismatch: 'reconcile'
	};

	let fileType = '';
	let status = '';
	let uploader = '';
	let query = '';
	let currentPage = 1;
	let pageSize = 25;
	let loads: LoadList | null = null;
	let errorMessage = '';

	$: domain = $portalDomains.find((item) => item.code === $selectedDomain);
	$: multipleFileTypes = hasMultipleFileTypes(domain);
	$: filtered = !!(query || status || uploader || (multipleFileTypes && fileType));

	const loadHistory = async (filter: LoadFilter) => {
		try {
			errorMessage = '';
			loads = await getLoads(localStorage.token, {
				...filter,
				file_type: multipleFileTypes ? filter.file_type : ''
			});
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	};

	$: loadHistory({
		domain: $selectedDomain,
		year: $selectedYear,
		file_type: fileType,
		status,
		user: uploader,
		query,
		page: currentPage,
		page_size: pageSize
	});

	const clearFilters = () => {
		query = '';
		status = '';
		uploader = '';
		fileType = '';
		currentPage = 1;
	};

	const startUpload = () => {
		resetUploadDraft();
		goto('/data-portal/upload');
	};

	const loadCells = (load: LoadListItem, multiple: boolean) => {
		const badge = LOAD_STATUS_BADGES[load.status];
		return [
			{ value: `#${load.id}`, bold: true, className: 's' },
			{
				value: load.file_name,
				file: true,
				action: () => goto(`/data-portal/history/${load.id}/file`),
				actionTitle: $i18n.t('View source file')
			},
			{ value: load.year, className: 's' },
			...(multiple ? [{ value: load.file_type.name, className: 's' }] : []),
			load.user,
			{ value: formatDateTime(load.created_at), className: 'nowrap' },
			{ value: formatNumber(load.row_count), className: 's' },
			{ badge: { label: $i18n.t(badge.label), tone: badge.tone } }
		];
	};

	$: rows = (loads?.items ?? []).map(
		(load): TableRow => ({
			cells: loadCells(load, multipleFileTypes),
			onClick: () => goto(`/data-portal/history/${load.id}?tab=${DETAIL_TABS[load.status]}`),
			title: $i18n.t('View details of upload #{{id}}', { id: load.id })
		})
	);

	$: headers = [
		{ label: $i18n.t('Code') },
		{ label: $i18n.t('File') },
		{ label: $i18n.t('Data year') },
		...(multipleFileTypes ? [{ label: $i18n.t('File type') }] : []),
		{ label: $i18n.t('Uploaded by') },
		{ label: $i18n.t('Upload time') },
		{ label: $i18n.t('Row count'), alignRight: true },
		{ label: $i18n.t('Upload status') }
	];
</script>

<HeaderCard title={$i18n.t('Upload history')}>
	<button slot="actions" type="button" class="btn primary" on:click={startUpload}
		>{$i18n.t('Upload a new file')}</button
	>
</HeaderCard>

<div class="chiprow" aria-label={$i18n.t('Filter bar')}>
	<DomainYearChips
		on:domain={() => {
			fileType = '';
			currentPage = 1;
		}}
		on:year={() => (currentPage = 1)}
	/>
	{#if multipleFileTypes}
		<Dropdown
			chipLabel={$i18n.t('File type')}
			value={fileType}
			defaultValue=""
			options={[
				{ value: '', label: $i18n.t('All') },
				...(domain?.file_types ?? []).map((item) => ({ value: item.code, label: item.name }))
			]}
			on:change={(event) => {
				fileType = event.detail;
				currentPage = 1;
			}}
		/>
	{/if}
	<Dropdown
		chipLabel={$i18n.t('Upload status')}
		value={status}
		defaultValue=""
		options={[
			{ value: '', label: $i18n.t('All') },
			...Object.entries(LOAD_STATUS_BADGES).map(([value, badge]) => ({
				value,
				label: $i18n.t(badge.label)
			}))
		]}
		on:change={(event) => {
			status = event.detail;
			currentPage = 1;
		}}
	/>
	<Dropdown
		chipLabel={$i18n.t('Uploaded by')}
		value={uploader}
		defaultValue=""
		options={[
			{ value: '', label: $i18n.t('All') },
			...(loads?.uploaders ?? []).map((name) => ({ value: name, label: name }))
		]}
		on:change={(event) => {
			uploader = event.detail;
			currentPage = 1;
		}}
	/>
	<SearchBox
		value={query}
		placeholder={$i18n.t('Search code or file name, press Enter to search')}
		on:search={(event) => {
			query = event.detail;
			currentPage = 1;
		}}
	/>
	{#if filtered}<button type="button" class="clear-filters" on:click={clearFilters}
			>{$i18n.t('Clear filters')}</button
		>{/if}
</div>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !loads}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else if !loads.items.length}
	<section class="card">
		{#if filtered}
			<EmptyState
				icon="list"
				title={$i18n.t('No matching results')}
				description={$i18n.t('Change the keyword or remove some filters.')}
			>
				<button type="button" class="btn" on:click={clearFilters}>{$i18n.t('Clear filters')}</button
				>
			</EmptyState>
		{:else if $selectedYear}
			<EmptyState
				icon="list"
				title={$i18n.t('Year {{year}} has no uploads yet', { year: $selectedYear })}
				description={$i18n.t(
					'Choose another year in the Data year field, or upload a file with Data year {{year}}.',
					{ year: $selectedYear }
				)}
			>
				<button type="button" class="btn primary" on:click={startUpload}
					>{$i18n.t('Upload a new file')}</button
				>
			</EmptyState>
		{:else}
			<EmptyState
				icon="list"
				title={$i18n.t('No uploads yet')}
				description={$i18n.t(
					'Information group {{name}} has no uploads yet. Upload the first file to get started.',
					{ name: domain?.name ?? '' }
				)}
			>
				<button type="button" class="btn primary" on:click={startUpload}
					>{$i18n.t('Upload the first file')}</button
				>
			</EmptyState>
		{/if}
	</section>
{:else}
	<Card title={$i18n.t('Upload list')} count={loads.total} padded={false}>
		<DataTable {headers} {rows} />
		<Pager
			total={loads.total}
			page={currentPage}
			{pageSize}
			on:change={(event) => {
				currentPage = event.detail.page;
				pageSize = event.detail.pageSize;
			}}
		/>
	</Card>
{/if}
