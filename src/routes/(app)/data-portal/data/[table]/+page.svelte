<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { resetUploadDraft, selectedDomain, selectedYear } from '$lib/stores/dataPortal';
	import { exportTable, getTable } from '$lib/apis/data-portal';
	import type { TableColumn, TableData, TableFilter } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import DomainYearChips from '$lib/components/data-portal/DomainYearChips.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import SearchBox from '$lib/components/data-portal/SearchBox.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Drawer from '$lib/components/data-portal/Drawer.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import ExcelGrid, { type ExcelRow } from '$lib/components/data-portal/ExcelGrid.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import {
		formatAmount,
		formatDate,
		formatDateTime,
		formatNumber,
		formatPercent,
		isBlank
	} from '$lib/components/data-portal/format';
	import { saveFile } from '$lib/components/data-portal/download';

	const i18n: Writable<i18nType> = getContext('i18n');

	type PreviewSheet = { name: string; columns: string[]; rows: ExcelRow[] };
	type ExportPreview = { fileName: string; sheets: PreviewSheet[]; tab: number; rowCount: number };

	const DEFAULT_LAYER = 'gold';
	const PREVIEW_ROW_LIMIT = 500;
	const NUMERIC_TYPES = ['int', 'money', 'ratio', 'number'];

	let layer = DEFAULT_LAYER;
	let period = '';
	let query = '';
	let currentPage = 1;
	let pageSize = 50;
	let table: TableData | null = null;
	let errorMessage = '';
	let showColumnGuide = false;
	let preview: ExportPreview | null = null;
	let initializedFor = '';

	$: tableName = $page.params.table ?? '';
	$: searchParams = $page.url.searchParams;

	$: if (initializedFor !== tableName) {
		initializedFor = tableName;
		layer = searchParams.get('layer') ?? DEFAULT_LAYER;
		period = searchParams.get('period') ?? '';
		query = searchParams.get('query') ?? '';
		if (searchParams.has('year')) selectedYear.set(searchParams.get('year') ?? '');
		currentPage = 1;
	}

	$: layerLabels = {
		gold: $i18n.t('Analytics data'),
		silver: $i18n.t('Standardized data'),
		bronze: $i18n.t('Raw data')
	} as Record<string, string>;

	const loadTable = async (name: string, filter: TableFilter, pageNumber: number, size: number) => {
		try {
			errorMessage = '';
			table = await getTable(localStorage.token, name, filter, pageNumber, size);
			if (table.domain && table.domain !== $selectedDomain) selectedDomain.set(table.domain);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	};

	$: filterYear = table?.kind === 'dim' ? '' : $selectedYear;
	$: loadTable(tableName, { layer, year: filterYear, period, query }, currentPage, pageSize);

	$: filtered = !!(period || query);
	$: subtitle = table ? tableSubtitle(table, $selectedYear, layer) : '';

	const tableSubtitle = (data: TableData, year: string, currentLayer: string) =>
		[
			data.file_type ? `${data.file_type.name} · ${data.file_type.subtitle ?? ''}` : '',
			data.has_period && data.latest_month
				? $i18n.t('Latest month {{month}}', { month: data.latest_month })
				: '',
			data.kind === 'dim'
				? $i18n.t('Shared across all years')
				: year
					? $i18n.t('Year {{year}}', { year })
					: $i18n.t('All years'),
			data.updated_at ? $i18n.t('Updated {{time}}', { time: formatDateTime(data.updated_at) }) : '',
			layerLabels[currentLayer]
		]
			.filter(Boolean)
			.join(' · ');

	const formatCell = (value: unknown, column: TableColumn) => {
		if (isBlank(value)) return '—';
		if (column.type === 'ratio') return formatPercent(value);
		if (column.type === 'date') return formatDate(value);
		if (typeof value === 'number')
			return column.type === 'money' ? formatAmount(value) : formatNumber(value);
		return String(value);
	};

	const alignRight = (column: TableColumn) =>
		NUMERIC_TYPES.includes(column.type) && layer !== 'bronze';

	const clearFilters = () => {
		period = '';
		query = '';
		currentPage = 1;
	};

	const startUpload = () => {
		resetUploadDraft();
		goto('/data-portal/upload');
	};

	const downloadExcel = async () => {
		const filter = { layer, year: filterYear, period, query };
		const { blob, fileName, rowCount } = await exportTable(localStorage.token, tableName, filter);
		saveFile(blob, fileName);
		try {
			preview = {
				fileName,
				sheets: await readPreviewSheets(blob),
				tab: 0,
				rowCount: rowCount ?? table?.total ?? 0
			};
		} catch (error) {
			console.error(error);
		}
	};

	const readPreviewSheets = async (blob: Blob): Promise<PreviewSheet[]> => {
		const XLSX = await import('xlsx');
		const workbook = XLSX.read(await blob.arrayBuffer(), { type: 'array' });
		return workbook.SheetNames.map((sheetName) => {
			const values = XLSX.utils.sheet_to_json<(string | number | null)[]>(
				workbook.Sheets[sheetName],
				{ header: 1, raw: false, defval: null }
			);
			const columnCount = Math.max(0, ...values.map((row) => row.length));
			return {
				name: sheetName,
				columns: Array.from({ length: columnCount }, (_, index) => XLSX.utils.encode_col(index)),
				rows: values.slice(0, PREVIEW_ROW_LIMIT).map((row, index) => ({
					rowNumber: index + 1,
					cells: row.map((value) => (value === null ? null : String(value)))
				}))
			};
		});
	};
</script>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !table}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else}
	<HeaderCard title={table.name} back={() => history.back()}>
		<svelte:fragment slot="actions">
			<button
				type="button"
				class="btn"
				title={$i18n.t('Meaning, data type and example of each column')}
				on:click={() => (showColumnGuide = true)}
				><Icon name="cols" size={16} />{$i18n.t('Explain the columns')}</button
			>
			<button
				type="button"
				class="btn primary"
				title={$i18n.t('Download exactly the filtered rows, with the THONG_TIN sheet')}
				on:click={downloadExcel}><Icon name="down" size={16} />{$i18n.t('Download Excel')}</button
			>
		</svelte:fragment>
	</HeaderCard>

	<div class="chiprow" aria-label={$i18n.t('Filter bar')}>
		<DomainYearChips
			yearLocked={table.kind === 'dim'}
			on:domain={() => goto('/data-portal/data')}
			on:year={() => (currentPage = 1)}
		>
			<svelte:fragment slot="month">
				{#if table.has_period}
					<Dropdown
						chipLabel={$i18n.t('Data month')}
						value={period}
						defaultValue=""
						options={[
							{ value: '', label: $i18n.t('All') },
							...table.periods.map((month) => ({
								value: month,
								label: $i18n.t('Month {{month}}', { month })
							}))
						]}
						on:change={(event) => {
							period = event.detail;
							currentPage = 1;
						}}
					/>
				{/if}
			</svelte:fragment>
		</DomainYearChips>
		<Dropdown
			chipLabel={$i18n.t('Data layer')}
			title={$i18n.t('View the table at layer')}
			value={layer}
			defaultValue={DEFAULT_LAYER}
			options={['gold', 'silver', 'bronze'].map((value) => ({
				value,
				label: layerLabels[value]
			}))}
			on:change={(event) => {
				layer = event.detail;
				currentPage = 1;
			}}
		/>
		<SearchBox
			value={query}
			placeholder={$i18n.t('Search by code or name, press Enter to search')}
			on:search={(event) => {
				query = event.detail;
				currentPage = 1;
			}}
		/>
		{#if filtered}<button type="button" class="clear-filters" on:click={clearFilters}
				>{$i18n.t('Clear filters')}</button
			>{/if}
	</div>

	<section class="card">
		<div class="card-h">
			<div>
				<h2>{$i18n.t('{{rows}} rows', { rows: formatNumber(table.total) })}</h2>
				<div class="sub">{subtitle}</div>
			</div>
		</div>
		<div class="tw scroll">
			<div class="tbox">
				<table>
					<thead>
						<tr
							>{#each table.columns as column}<th
									class:r={alignRight(column)}
									title={column.source_name}>{column.name}</th
								>{/each}</tr
						>
					</thead>
					<tbody>
						{#each table.rows as row}
							<tr>
								{#each row as value, index}
									<td
										class:r={alignRight(table.columns[index])}
										class:s={index === 0}
										class:neg={table.columns[index].is_measure &&
											typeof value === 'number' &&
											value < 0}
										style={value === null || value === '' ? 'color:var(--faint)' : ''}
										>{formatCell(value, table.columns[index])}</td
									>
								{/each}
							</tr>
						{:else}
							<tr>
								<td
									colspan={table.columns.length}
									style="text-align:center;padding:24px;color:var(--muted)"
								>
									{#if filtered}
										{$i18n.t('No rows match the filters.')}
										<button type="button" class="link" on:click={clearFilters}
											>{$i18n.t('Clear filters')}</button
										>
									{:else if $selectedYear && table.kind === 'fact'}
										{$i18n.t('Year {{year}} has no data yet.', { year: $selectedYear })}
										<button type="button" class="link" on:click={startUpload}
											>{$i18n.t('Upload data')}</button
										>
										{$i18n.t('or choose another year.')}
									{:else}
										{$i18n.t('The table has no rows yet.')}
										<button type="button" class="link" on:click={startUpload}
											>{$i18n.t('Upload data')}</button
										>
									{/if}
								</td>
							</tr>
						{/each}
						{#if filtered && table.total && table.total_row && layer !== 'bronze'}
							<tr class="total">
								{#each table.total_row as value, index}
									<td class:r={index > 0} class:neg={typeof value === 'number' && value < 0}
										>{index === 0
											? $i18n.t('Total of filtered data')
											: value === null
												? ''
												: formatCell(value, table.columns[index])}</td
									>
								{/each}
							</tr>
						{/if}
					</tbody>
				</table>
			</div>
		</div>
		{#if table.total}
			<Pager
				total={table.total}
				page={currentPage}
				{pageSize}
				on:change={(event) => {
					currentPage = event.detail.page;
					pageSize = event.detail.pageSize;
				}}
			/>
		{/if}
	</section>
{/if}

{#if showColumnGuide && table}
	<Drawer label={$i18n.t('Explain the columns')} on:close={() => (showColumnGuide = false)}>
		<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
			<h2 style="margin:0;font-size:18px;font-weight:500">{$i18n.t('Explain the columns')}</h2>
			<button type="button" class="btn sm" on:click={() => (showColumnGuide = false)}
				>{$i18n.t('Close')}</button
			>
		</div>
		<p class="desc" style="font-size:13px;margin-bottom:10px">
			{table.name} — {table.grain || table.description}
		</p>
		{#each table.columns as column}
			<div class="column-guide">
				<b>{column.name}</b>
				<div>{$i18n.t('Name in the NBC file: {{name}}', { name: column.source_name })}</div>
				<div>
					{$i18n.t('Data type: {{type}}', {
						type: column.type_label ?? column.type
					})}{column.required ? ` · ${$i18n.t('identifier column, required')}` : ''}
				</div>
				<div>{column.meaning}</div>
				<div>{$i18n.t('Used for: {{purpose}}', { purpose: column.purpose })}</div>
				{#if column.example}<div>{$i18n.t('For example:')} <code>{column.example}</code></div>{/if}
			</div>
		{/each}
	</Drawer>
{/if}

{#if preview}
	<Dialog wide label={$i18n.t('View the downloaded file')} on:close={() => (preview = null)}>
		<div style="display:flex;gap:12px;align-items:center">
			<span class="fileic"><Icon name="doc" size={20} /></span>
			<div style="min-width:0">
				<h2 style="word-break:break-all">{preview.fileName}</h2>
				<p class="desc">
					{$i18n.t('Downloaded · {{rows}} rows · {{sheets}} sheets', {
						rows: formatNumber(preview.rowCount),
						sheets: preview.sheets.length
					})}
				</p>
			</div>
		</div>
		<div class="subtabs" style="padding:0">
			{#each preview.sheets as sheet, index}
				<button
					type="button"
					class="subtab"
					class:on={index === preview.tab}
					on:click={() => preview && (preview.tab = index)}>{sheet.name}</button
				>
			{/each}
		</div>
		<ExcelGrid
			columns={preview.sheets[preview.tab].columns}
			rows={preview.sheets[preview.tab].rows}
		/>
		<div class="row" style="justify-content:flex-end">
			<button type="button" class="btn" on:click={() => (preview = null)}>{$i18n.t('Close')}</button
			>
		</div>
	</Dialog>
{/if}
