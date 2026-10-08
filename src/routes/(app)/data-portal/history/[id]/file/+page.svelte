<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	import { hasMultipleFileTypes, loadPortalDomains, portalDomains } from '$lib/stores/dataPortal';
	import {
		downloadLoadFile,
		getLoad,
		getLoadFileSheet,
		getLoadFileSheets
	} from '$lib/apis/data-portal';
	import type { Load, SourceSheet, SourceSheetPage } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import ReadonlyCard from '$lib/components/data-portal/ReadonlyCard.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import ExcelGrid from '$lib/components/data-portal/ExcelGrid.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { formatDateTime, formatNumber } from '$lib/components/data-portal/format';
	import { saveFile } from '$lib/components/data-portal/download';

	const i18n: Writable<i18nType> = getContext('i18n');

	let load: Load | null = null;
	let sheets: SourceSheet[] = [];
	let sheetPage: SourceSheetPage | null = null;
	let errorMessage = '';
	let currentPage = 1;
	let pageSize = 50;
	let opening = false;

	$: loadId = Number($page.params.id);
	$: requestedSheet = Number($page.url.searchParams.get('sheet') ?? '-1');
	$: domain = $portalDomains.find((item) => item.code === load?.domain);
	$: multipleFileTypes = hasMultipleFileTypes(domain);
	$: monthRequired = domain?.file_types.some((item) => item.month_required) ?? false;
	$: currentSheet =
		sheets.find((sheet) => sheet.index === requestedSheet) ??
		sheets.find((sheet) => sheet.name === load?.sheet) ??
		sheets.find((sheet) => !sheet.hidden) ??
		sheets[0];

	onMount(async () => {
		try {
			await loadPortalDomains();
			[load, sheets] = await Promise.all([
				getLoad(localStorage.token, loadId),
				getLoadFileSheets(localStorage.token, loadId)
			]);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	});

	const loadSheet = async (sheet: SourceSheet | undefined, pageNumber: number, size: number) => {
		if (!sheet) return;
		opening = true;
		try {
			sheetPage = await getLoadFileSheet(localStorage.token, loadId, sheet.index, pageNumber, size);
		} catch (error) {
			errorMessage = (error as Error).message;
		} finally {
			opening = false;
		}
	};

	$: loadSheet(currentSheet, currentPage, pageSize);

	const selectSheet = (sheet: SourceSheet) => {
		currentPage = 1;
		goto(`/data-portal/history/${loadId}/file?sheet=${sheet.index}`, {
			replaceState: true,
			noScroll: true
		});
	};

	const downloadSourceFile = async () => {
		const { blob, fileName } = await downloadLoadFile(
			localStorage.token,
			loadId,
			load?.file_name ?? 'tep.xlsx'
		);
		saveFile(blob, fileName);
	};
</script>

{#if errorMessage}
	<Banner tone="err" icon="x" title={errorMessage} />
{:else if !load}
	<p class="desc">{$i18n.t('Opening file…')}</p>
{:else}
	<HeaderCard
		title={$i18n.t('Source file · upload #{{id}}', { id: load.id })}
		description={load.file_name}
		back={() => history.back()}
	>
		<svelte:fragment slot="actions">
			<button type="button" class="btn" on:click={downloadSourceFile}
				><Icon name="down" size={16} />{$i18n.t('Download source file')}</button
			>
			<button
				type="button"
				class="btn primary"
				on:click={() => goto(`/data-portal/history/${loadId}`)}
				>{$i18n.t('View upload details')}</button
			>
		</svelte:fragment>
	</HeaderCard>

	<ReadonlyCard
		title={$i18n.t('File information')}
		fields={[
			{ label: $i18n.t('Information group'), value: `${load.domain} · ${domain?.name ?? ''}` },
			...(monthRequired ? [{ label: $i18n.t('Data month'), value: load.month ?? '—' }] : []),
			{ label: $i18n.t('Data year'), value: load.year },
			...(multipleFileTypes ? [{ label: $i18n.t('File type'), value: load.file_type.name }] : []),
			{ label: $i18n.t('Uploaded by'), value: load.user },
			{ label: $i18n.t('Upload time'), value: formatDateTime(load.created_at) },
			{ label: $i18n.t('Sheet count'), value: formatNumber(sheets.length) }
		]}
	/>

	<section class="card">
		<div class="card-h">
			<div><h2>{$i18n.t('File contents')}</h2></div>
		</div>
		<div class="subtabs" role="tablist">
			{#each sheets as sheet (sheet.index)}
				<button
					type="button"
					role="tab"
					class="subtab"
					class:on={sheet.index === currentSheet?.index}
					aria-selected={sheet.index === currentSheet?.index}
					on:click={() => selectSheet(sheet)}
				>
					{sheet.name} <span class="count">{formatNumber(sheet.row_count)}</span>
					{#if sheet.hidden}<span class="hidden-tag">{$i18n.t('hidden')}</span>{/if}
				</button>
			{/each}
		</div>
		{#if currentSheet?.hidden_row_count}
			<p class="hint" style="padding:10px 24px 0;margin:0">
				{$i18n.t(
					'{{rows}} rows are hidden in Excel (faded text). The portal reads hidden rows too.',
					{ rows: formatNumber(currentSheet.hidden_row_count) }
				)}
			</p>
		{/if}
		{#if opening && !sheetPage}
			<p class="desc" style="padding:16px 24px">{$i18n.t('Opening file…')}</p>
		{:else if sheetPage}
			<div style="padding:12px 0 0">
				<ExcelGrid
					columns={sheetPage.columns}
					rows={sheetPage.rows.map((row) => ({
						rowNumber: row.row_number,
						cells: row.cells,
						hidden: row.hidden
					}))}
				/>
			</div>
			<Pager
				total={sheetPage.total}
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
