<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import {
		hasMultipleFileTypes,
		portalDomains,
		resetUploadDraft,
		selectedDomain,
		selectedYear
	} from '$lib/stores/dataPortal';
	import { getTables } from '$lib/apis/data-portal';
	import type { TableSummary } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import DomainYearChips from '$lib/components/data-portal/DomainYearChips.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import DataTable, { type TableRow } from '$lib/components/data-portal/DataTable.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import { formatDateTime, formatNumber } from '$lib/components/data-portal/format';

	const i18n: Writable<i18nType> = getContext('i18n');

	let tables: TableSummary[] | null = null;
	let errorMessage = '';

	onMount(() => {
		const year = $page.url.searchParams.get('year');
		if (year !== null) selectedYear.set(year);
	});

	const loadTables = async (domain: string, year: string) => {
		try {
			errorMessage = '';
			tables = await getTables(localStorage.token, domain, year);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	};

	$: loadTables($selectedDomain, $selectedYear);

	$: multipleFileTypes = hasMultipleFileTypes(
		$portalDomains.find((domain) => domain.code === $selectedDomain)
	);
	$: yearHasNoData =
		!!$selectedYear &&
		!!tables &&
		tables.filter((table) => table.kind === 'fact').every((table) => !table.row_count);

	const openTable = (table: TableSummary) => () => {
		const year = $selectedYear && table.kind === 'fact' ? `&year=${$selectedYear}` : '';
		goto(`/data-portal/data/${table.table}?layer=gold${year}`);
	};

	const startUpload = () => {
		resetUploadDraft();
		goto('/data-portal/upload');
	};

	const updatedCell = (table: TableSummary) =>
		table.row_count
			? formatDateTime(table.updated_at)
			: { badge: { label: $i18n.t('Not uploaded'), tone: 'muted' } };

	const tableCells = (table: TableSummary, multiple: boolean) =>
		multiple
			? [
					{ value: table.name, bold: true, subtitle: table.description, className: 's' },
					table.year ?? '—',
					{
						value: table.file_type.name,
						subtitle: table.file_type.subtitle ?? undefined,
						className: 's'
					},
					table.load_id ? `#${table.load_id}` : '—',
					{ value: formatNumber(table.row_count), className: 's' },
					updatedCell(table)
				]
			: [
					{ value: table.name, bold: true, subtitle: table.description, className: 's' },
					table.kind === 'dim' ? $i18n.t('Shared across all years') : (table.year ?? '—'),
					table.kind === 'dim' ? '—' : (table.months ?? '—'),
					{ value: formatNumber(table.row_count), className: 's' },
					updatedCell(table)
				];

	$: rows = (tables ?? []).map(
		(table): TableRow => ({
			cells: tableCells(table, multipleFileTypes),
			onClick: table.row_count ? openTable(table) : undefined,
			title: $i18n.t('Open table {{name}}', { name: table.name })
		})
	);

	$: headers = multipleFileTypes
		? [
				{ label: $i18n.t('Table name') },
				{ label: $i18n.t('Year') },
				{ label: $i18n.t('File type') },
				{ label: $i18n.t('Upload run') },
				{ label: $i18n.t('Row count'), alignRight: true },
				{ label: $i18n.t('Updated at') }
			]
		: [
				{ label: $i18n.t('Table name') },
				{ label: $i18n.t('Year') },
				{ label: $i18n.t('Data month') },
				{ label: $i18n.t('Row count'), alignRight: true },
				{ label: $i18n.t('Updated at') }
			];
</script>

<HeaderCard title={$i18n.t('Data')} />

<div class="chiprow" aria-label={$i18n.t('Filter bar')}>
	<DomainYearChips />
</div>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !tables}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else}
	<Card title={$i18n.t('Data tables')} count={tables.length} padded={false}>
		{#if yearHasNoData}
			<p class="desc" style="padding:0 24px 12px">
				{$i18n.t('Year {{year}} has no data yet.', { year: $selectedYear })}
				<button type="button" class="link" on:click={startUpload}>{$i18n.t('Upload data')}</button>
			</p>
		{/if}
		<DataTable {headers} {rows} />
	</Card>
{/if}
