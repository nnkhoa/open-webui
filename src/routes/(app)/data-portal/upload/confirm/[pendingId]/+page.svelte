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
		resetUploadDraft,
		uploadDraft
	} from '$lib/stores/dataPortal';
	import {
		confirmPendingUpload,
		createUpload,
		deletePendingUpload,
		getPendingUpload
	} from '$lib/apis/data-portal';
	import type {
		ExistingData,
		PendingUpload,
		TableCheck,
		UploadGroupRow
	} from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import ReadonlyCard from '$lib/components/data-portal/ReadonlyCard.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import DataTable, {
		type TableCell,
		type TableRow
	} from '$lib/components/data-portal/DataTable.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import {
		formatAmount,
		formatDateTime,
		formatKilobytes,
		formatNumber
	} from '$lib/components/data-portal/format';

	const i18n: Writable<i18nType> = getContext('i18n');

	const OVERWRITE_MODE = 'Ghi đè';
	const UPLOAD_PATH = '/data-portal/upload';

	let pending: PendingUpload | null = null;
	let errorMessage = '';
	let busy = false;

	$: pendingId = $page.params.pendingId ?? '';
	$: domain = $portalDomains.find((item) => item.code === pending?.domain);
	$: multipleFileTypes = hasMultipleFileTypes(domain);
	$: otherFileTypeName =
		domain?.file_types.find((item) => item.code !== pending?.file_type.code)?.name ?? '';

	onMount(async () => {
		try {
			await loadPortalDomains();
			pending = await getPendingUpload(localStorage.token, pendingId);
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	});

	const joinItems = (items: (string | number)[]) => items.join(', ');

	const backToFirstStep = () => goto(UPLOAD_PATH);

	const cancelUpload = async () => {
		busy = true;
		try {
			await deletePendingUpload(localStorage.token, pendingId);
		} catch (error) {
			console.error(error);
		}
		uploadDraft.update((draft) => ({ ...draft, file: null, selectedAt: '' }));
		goto(UPLOAD_PATH);
	};

	const recheckFile = async () => {
		const draft = $uploadDraft;
		if (!draft.file) return backToFirstStep();
		busy = true;
		try {
			await deletePendingUpload(localStorage.token, pendingId).catch(() => null);
			const result = await createUpload(localStorage.token, {
				domain: draft.domain,
				year: draft.year,
				month: pending?.month ? String(pending.month) : undefined,
				fileType: pending?.file_type.code,
				file: draft.file
			});
			if (result.pending_id) {
				pending = null;
				await goto(`/data-portal/upload/confirm/${result.pending_id}`, { replaceState: true });
				pending = await getPendingUpload(localStorage.token, result.pending_id);
			} else if (result.load_id) {
				resetUploadDraft();
				goto(`/data-portal/upload/result/${result.load_id}`);
			}
		} catch (error) {
			errorMessage = (error as Error).message;
		} finally {
			busy = false;
		}
	};

	const confirmUpload = async () => {
		busy = true;
		try {
			const result = await confirmPendingUpload(localStorage.token, pendingId);
			resetUploadDraft();
			if (result) goto(`/data-portal/upload/result/${result.load_id}`);
		} catch (error) {
			errorMessage = (error as Error).message;
			busy = false;
		}
	};

	const existingCell = (existing: ExistingData | null): TableCell =>
		existing
			? {
					value: $i18n.t('{{rows}} rows', { rows: formatNumber(existing.row_count) }),
					subtitle: $i18n.t('upload #{{id}} · {{time}} · {{user}}', {
						id: existing.load_id,
						time: formatDateTime(existing.created_at),
						user: existing.user
					}),
					className: 's'
				}
			: '—';

	const writeModeCell = (mode: string): TableCell => ({
		badge: { label: mode, tone: mode === OVERWRITE_MODE ? 'warn' : 'ok' }
	});

	const checkCells = (check: TableCheck, multiple: boolean): TableCell[] =>
		multiple
			? [
					{ value: check.table_name, bold: true, className: 's' },
					formatNumber(check.read),
					formatNumber(check.missing_required),
					formatNumber(check.duplicates),
					{
						value: formatNumber(check.empty_cells),
						subtitle: check.empty_cell_details?.length
							? $i18n.t('unreadable: {{cells}}', {
									cells: check.empty_cell_details
										.map((detail) => `${detail.column} ${detail.cell_count}`)
										.join(' · ')
								})
							: undefined
					},
					formatNumber(check.to_write),
					formatNumber(check.total),
					{ badge: { label: check.verdict, tone: 'ok' } }
				]
			: [
					{ value: check.table_name, className: 's' },
					check.sheet,
					formatNumber(check.read),
					formatNumber(check.missing_required),
					formatNumber(check.duplicates),
					formatNumber(check.to_write),
					check.total === null ? '—' : formatAmount(check.total),
					{ badge: { label: check.verdict, tone: 'ok' } }
				];

	const sum = (checks: TableCheck[], value: (check: TableCheck) => number) =>
		formatNumber(checks.reduce((total, check) => total + value(check), 0));

	const groupCells = (
		row: UploadGroupRow,
		index: number,
		rows: UploadGroupRow[],
		multiple: boolean
	): TableCell[] => {
		if (multiple) {
			return [
				{ value: row.group, bold: true, subtitle: row.subtitle, className: 's' },
				formatNumber(row.row_count),
				formatNumber(row.quantity),
				existingCell(row.existing),
				writeModeCell(row.write_mode)
			];
		}
		const firstOfGroup = index === 0 || rows[index - 1].group !== row.group;
		return [
			firstOfGroup ? { value: row.group, bold: true, className: 's' } : '',
			{ value: row.data ?? '', className: 's' },
			formatNumber(row.row_count),
			`${formatNumber(row.column_count)} / ${formatNumber(row.total_column_count)}`,
			existingCell(row.existing),
			writeModeCell(row.write_mode)
		];
	};

	$: checkRows = (pending?.checks ?? []).map(
		(check): TableRow => ({ cells: checkCells(check, multipleFileTypes) })
	);

	$: checkTotals =
		!multipleFileTypes && pending
			? [
					{ value: $i18n.t('Total') },
					'',
					sum(pending.checks, (check) => check.read),
					sum(pending.checks, (check) => check.missing_required),
					sum(pending.checks, (check) => check.duplicates),
					sum(pending.checks, (check) => check.to_write),
					'',
					''
				]
			: null;

	$: groupRows = (pending?.by_group?.rows ?? []).map(
		(row, index, rows): TableRow => ({ cells: groupCells(row, index, rows, multipleFileTypes) })
	);

	$: groupTotals =
		multipleFileTypes && pending?.by_group?.total
			? [
					$i18n.t('Total'),
					formatNumber(pending.by_group.total.row_count),
					formatNumber(pending.by_group.total.quantity),
					pending.by_group.total.existing ? formatNumber(pending.by_group.total.existing) : '—',
					''
				]
			: null;

	$: infoFields = pending
		? multipleFileTypes
			? [
					{ label: $i18n.t('Information group'), value: `${domain?.code} · ${domain?.name}` },
					...(pending.month ? [{ label: $i18n.t('Data month'), value: pending.month }] : []),
					{ label: $i18n.t('Data year'), value: pending.year },
					{ label: $i18n.t('File type'), value: pending.file_type.name },
					{ label: $i18n.t('Taken from sheet'), value: pending.sheet ?? '—' },
					{ label: $i18n.t('Uploaded file name'), value: pending.file_name },
					{ label: $i18n.t('Size'), value: formatKilobytes(pending.size_bytes) }
				]
			: [
					{ label: $i18n.t('Information group'), value: `${domain?.code} · ${domain?.name}` },
					{ label: $i18n.t('File kind'), value: pending.file_type.name },
					{ label: $i18n.t('Data year'), value: pending.year },
					{ label: $i18n.t('Uploaded file name'), value: pending.file_name, span: 2 },
					{ label: $i18n.t('Size'), value: formatKilobytes(pending.size_bytes) }
				]
		: [];

	$: checkHeaders = multipleFileTypes
		? [
				{ label: $i18n.t('Table name') },
				{ label: $i18n.t('Rows read'), alignRight: true },
				{ label: $i18n.t('Missing required values'), alignRight: true },
				{ label: $i18n.t('Duplicate rows to drop'), alignRight: true },
				{ label: $i18n.t('Empty cells'), alignRight: true },
				{ label: $i18n.t('Rows to write'), alignRight: true },
				{ label: $i18n.t('Total quantity'), alignRight: true },
				{ label: $i18n.t('Verdict') }
			]
		: [
				{ label: $i18n.t('Table name') },
				{ label: $i18n.t('Taken from sheet') },
				{ label: $i18n.t('Rows read'), alignRight: true },
				{ label: $i18n.t('Missing required values'), alignRight: true },
				{ label: $i18n.t('Duplicate rows to drop'), alignRight: true },
				{ label: $i18n.t('Rows to write'), alignRight: true },
				{ label: $i18n.t('Total amount in the file'), alignRight: true },
				{ label: $i18n.t('Verdict') }
			];

	$: groupHeaders = multipleFileTypes
		? [
				{ label: pending?.by_group?.first_column ?? '' },
				{ label: $i18n.t('Rows in the file'), alignRight: true },
				{ label: $i18n.t('Quantity'), alignRight: true },
				{ label: $i18n.t('Currently in the system') },
				{ label: $i18n.t('How data is written on upload') }
			]
		: [
				{ label: $i18n.t('Data month') },
				{ label: $i18n.t('Data') },
				{ label: $i18n.t('Rows in the file'), alignRight: true },
				{ label: $i18n.t('Columns used'), alignRight: true },
				{ label: $i18n.t('Currently in the system') },
				{ label: $i18n.t('How data is written on upload') }
			];
</script>

<HeaderCard title={$i18n.t('Confirm data upload')} back={backToFirstStep}>
	<svelte:fragment slot="actions">
		<button
			type="button"
			class="btn danger"
			disabled={busy}
			title={$i18n.t('Discard this file. Data in the database stays unchanged.')}
			on:click={cancelUpload}>{$i18n.t('Cancel, do not upload')}</button
		>
		<button type="button" class="btn primary" disabled={busy || !pending} on:click={confirmUpload}
			><Icon name="up" size={16} />{$i18n.t('Confirm adding new data')}</button
		>
	</svelte:fragment>
</HeaderCard>

<StepBar
	current={2}
	withFileType={multipleFileTypes}
	backLinks={{
		0: {
			title: multipleFileTypes
				? $i18n.t('Back to step 1: change group, year, file type or file')
				: $i18n.t('Back to step 1: change group, year or file'),
			onClick: backToFirstStep
		},
		1: { title: $i18n.t('Run the file check step again'), onClick: recheckFile }
	}}
/>

{#if errorMessage}<Banner tone="err" icon="x" title={errorMessage} />{/if}

{#if !pending && !errorMessage}
	<p class="desc">{$i18n.t('Loading data…')}</p>
{:else if pending}
	<ReadonlyCard title={$i18n.t('Pending file information')} fields={infoFields} />

	<Card title={$i18n.t('Data check results for the file')} padded={false}>
		<DataTable headers={checkHeaders} rows={checkRows} totals={checkTotals} />
	</Card>

	{#if pending.identical}
		<Banner
			tone="warn"
			icon="alert"
			title={$i18n.t('This file is identical to upload #{{id}}', { id: pending.identical.load_id })}
			description={$i18n.t(
				'Uploaded at {{time}} by {{user}}. The content has not changed, so uploading again will not change the data.',
				{ time: formatDateTime(pending.identical.created_at), user: pending.identical.user }
			)}
		/>
	{:else if multipleFileTypes && pending.previous}
		<Banner
			tone="warn"
			icon="alert"
			title={$i18n.t('{{fileType}} for {{year}} already has data — it will be fully overwritten', {
				fileType: pending.file_type.name,
				year: pending.year
			})}
			description={$i18n.t(
				'{{previousRows}} rows of upload #{{id}} will be replaced by {{rows}} rows from the file. {{other}} stays unchanged.',
				{
					previousRows: formatNumber(pending.previous.row_count),
					id: pending.previous.load_id,
					rows: formatNumber(pending.by_group?.total?.row_count),
					other: otherFileTypeName
				}
			)}
		/>
	{:else if multipleFileTypes}
		<Banner
			tone="info"
			icon="info"
			title={$i18n.t('{{fileType}} for {{year}} is new data', {
				fileType: pending.file_type.name,
				year: pending.year
			})}
			description={$i18n.t(
				'The system has no {{fileType}} for {{year}} yet. Uploading will add {{rows}} rows. {{other}} stays unchanged.',
				{
					fileType: pending.file_type.name,
					year: pending.year,
					rows: formatNumber(pending.by_group?.total?.row_count),
					other: otherFileTypeName
				}
			)}
		/>
	{:else if pending.overwrite.length}
		<Banner
			tone="warn"
			icon="alert"
			title={$i18n.t('Month {{months}} of {{year}} already has data — it will be overwritten', {
				months: joinItems(pending.overwrite),
				year: pending.year
			})}
			description={[
				pending.overwrite.length === 1
					? $i18n.t('Existing data of this month will be replaced by the data in the file.')
					: $i18n.t('Existing data of these months will be replaced by the data in the file.'),
				pending.new.length
					? $i18n.t('Month {{months}} is new.', { months: joinItems(pending.new) })
					: '',
				$i18n.t('Months not in the file stay unchanged.')
			]
				.filter(Boolean)
				.join(' ')}
		/>
	{:else}
		<Banner
			tone="info"
			icon="info"
			title={$i18n.t('Month {{months}} of {{year}} is new data', {
				months: joinItems(pending.new),
				year: pending.year
			})}
			description={pending.new.length === 1
				? $i18n.t(
						'The system has no data for this month yet. Uploading will add data and overwrite no month.'
					)
				: $i18n.t(
						'The system has no data for these months yet. Uploading will add data and overwrite no month.'
					)}
		/>
	{/if}

	<Card title={pending.by_group?.title ?? ''} padded={false}>
		<DataTable headers={groupHeaders} rows={groupRows} totals={groupTotals} />
	</Card>
{/if}
