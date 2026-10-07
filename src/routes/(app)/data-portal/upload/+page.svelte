<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { user } from '$lib/stores';
	import {
		DATA_YEARS,
		hasMultipleFileTypes,
		loadPortalDomains,
		portalDomains,
		resetUploadDraft,
		uploadDraft,
		type UploadDraft
	} from '$lib/stores/dataPortal';
	import { checkUploadForm, createUpload } from '$lib/apis/data-portal';
	import type { LoadError } from '$lib/apis/data-portal/types';

	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import Icon from '$lib/components/data-portal/Icon.svelte';
	import { formatDateTime, formatKilobytes, joinWithAnd } from '$lib/components/data-portal/format';
	import { saveFile } from '$lib/components/data-portal/download';

	const i18n: Writable<i18nType> = getContext('i18n');

	const XLSX_EXTENSION = '.xlsx';
	const RECEIVED_STEP_DELAY_MS = 400;

	let checking = false;
	let checkProgress = 0;
	let invalidFile = false;
	let errorMessage = '';
	let dragging = false;
	let formCheck: 'idle' | 'checking' | 'ok' | 'mismatch' = 'idle';
	let formErrors: LoadError[] = [];
	let checkedKey: unknown[] = [];

	onMount(async () => {
		try {
			await loadPortalDomains();
		} catch (error) {
			errorMessage = (error as Error).message;
		}
	});

	$: draft = $uploadDraft;
	$: domain = $portalDomains.find((item) => item.code === draft.domain);
	$: multipleFileTypes = hasMultipleFileTypes(domain);
	$: fileType =
		domain?.file_types.find((item) => item.code === draft.fileType) ??
		(!multipleFileTypes ? domain?.file_types[0] : undefined);
	$: missingFields = [
		!draft.domain && $i18n.t('Information group'),
		!draft.year && $i18n.t('Data year'),
		multipleFileTypes && !draft.fileType && $i18n.t('File type')
	].filter(Boolean) as string[];
	$: missingSelection = missingFields.length
		? $i18n.t('Select {{fields}}', { fields: joinWithAnd(missingFields, $i18n.t('and')) })
		: '';
	$: missingInput =
		missingSelection || (!draft.file ? $i18n.t('Choose a file in the Attachment section') : '');
	$: fileLocked = checking || !!missingSelection;
	$: validFile = !!draft.file && draft.file.name.toLowerCase().endsWith(XLSX_EXTENSION);
	$: fileTypeName = multipleFileTypes
		? draft.fileType
			? (fileType?.name ?? '')
			: ''
		: (fileType?.name ?? $portalDomains[0]?.file_types[0]?.name ?? '');

	$: runFormCheck(draft.file, draft.domain, fileType?.code);

	const runFormCheck = async (file: File | null, domainCode: string, fileTypeCode?: string) => {
		const key = [file, domainCode, fileTypeCode];
		if (key.every((value, index) => value === checkedKey[index])) return;
		checkedKey = key;
		formErrors = [];
		if (!file || !domainCode || !file.name.toLowerCase().endsWith(XLSX_EXTENSION)) {
			formCheck = 'idle';
			return;
		}
		formCheck = 'checking';
		try {
			const result = await checkUploadForm(localStorage.token, {
				domain: domainCode,
				fileType: fileTypeCode,
				file
			});
			if (checkedKey !== key) return;
			formCheck = result.ok ? 'ok' : 'mismatch';
			formErrors = result.errors;
		} catch (error) {
			if (checkedKey !== key) return;
			formCheck = 'mismatch';
			formErrors = [
				{ sheet: null, location: null, issue: (error as Error).message, resolution: null }
			];
		}
	};

	const updateDraft = (changes: Partial<UploadDraft>) =>
		uploadDraft.update((current) => ({ ...current, ...changes }));

	const selectFile = (file: File | undefined | null) => {
		if (!file) return;
		if (fileLocked) {
			toast(
				multipleFileTypes
					? $i18n.t('Select the information group, data year and file type before choosing a file.')
					: $i18n.t('Select the information group and data year before choosing a file.')
			);
			return;
		}
		invalidFile = false;
		updateDraft({ file, selectedAt: formatDateTime(new Date().toISOString()) });
	};

	const checkFile = async () => {
		if (!draft.file) return;
		if (!validFile) {
			invalidFile = true;
			updateDraft({ file: null, selectedAt: '' });
			return;
		}
		invalidFile = false;
		checking = true;
		checkProgress = 0;
		const timer = setTimeout(() => (checkProgress = 1), RECEIVED_STEP_DELAY_MS);
		try {
			const result = await createUpload(localStorage.token, {
				domain: draft.domain,
				year: draft.year,
				fileType: fileType?.code,
				file: draft.file
			});
			if (result.pending_id) {
				goto(`/data-portal/upload/confirm/${result.pending_id}`);
			} else if (result.load_id) {
				resetUploadDraft();
				goto(`/data-portal/upload/result/${result.load_id}`);
			}
		} catch (error) {
			errorMessage = (error as Error).message;
		} finally {
			clearTimeout(timer);
			checking = false;
		}
	};
</script>

<HeaderCard title={$i18n.t('Upload data')}>
	<svelte:fragment slot="actions">
		<button
			type="button"
			class="btn primary"
			disabled={!!missingInput || checking || formCheck !== 'ok'}
			title={missingInput
				? $i18n.t('{{reason}} to continue', { reason: missingInput })
				: formCheck === 'checking'
					? $i18n.t('Checking whether the file matches the form…')
					: formCheck === 'mismatch'
						? $i18n.t('The file does not match the form. Choose the correct file.')
						: $i18n.t(
								'Read the file and compare it with the existing data. Nothing is written to the database yet.'
							)}
			on:click={checkFile}
		>
			{#if checking}<span class="spin" aria-hidden="true"></span>{$i18n.t('Checking…')}{:else}<Icon
					name="up"
					size={16}
				/>{$i18n.t('Check file')}{/if}
		</button>
	</svelte:fragment>
</HeaderCard>

<StepBar current={checking ? 1 : 0} withFileType={multipleFileTypes} />

{#if invalidFile}
	<Banner
		tone="err"
		icon="x"
		title={$i18n.t('This file cannot be selected')}
		description={$i18n.t(
			'The portal only accepts .xlsx files. Open the file in Excel and save it in the correct format.'
		)}
	/>
{/if}
{#if formCheck === 'mismatch'}
	<Banner
		tone="err"
		icon="x"
		title={$i18n.t('The file does not match the form {{form}}', { form: fileTypeName })}
		description={formErrors
			.map((error) => [error.issue, error.resolution].filter(Boolean).join(' — '))
			.join('; ')}
	/>
{/if}
{#if errorMessage}
	<Banner
		tone="err"
		icon="x"
		title={$i18n.t('Could not check the file')}
		description={errorMessage}
	/>
{/if}

{#if checking}
	<Card title={$i18n.t('Checking the file')}>
		<div class="steps">
			<div class="step {checkProgress >= 1 ? 'done' : 'on'}">
				<span class="n">{checkProgress >= 1 ? '✓' : '1'}</span>{$i18n.t('Receive file')}
			</div>
			<div class="step {checkProgress >= 1 ? 'on' : ''}">
				<span class="n">2</span>{$i18n.t('Check the file structure and the data of each row')}
				{#if checkProgress >= 1}<span class="spin" aria-hidden="true"></span>{/if}
			</div>
			<div class="step"><span class="n">3</span>{$i18n.t('Compare with the existing data')}</div>
			<p class="desc">
				{$i18n.t('Please stay on this page. Processing time depends on the file size.')}
			</p>
		</div>
	</Card>
{/if}

<section class="card">
	<div class="card-h">
		<div>
			<h2>{$i18n.t('Upload information')}</h2>
			<div class="sub">
				{$i18n.t('Please fill in the details below; fields marked')} (<span style="color:var(--req)"
					>*</span
				>) {$i18n.t('are required.')}
			</div>
		</div>
	</div>
	<div class="form-grid">
		<div class="field s2">
			<span class="lbl">{$i18n.t('Information group')} <span class="req">*</span></span>
			{#if checking}
				<div class="ro locked"><Icon name="lock" size={13} />{domain?.code} · {domain?.name}</div>
			{:else}
				<Dropdown
					value={draft.domain}
					placeholder={$i18n.t('Select information group')}
					title={$i18n.t('Select information group')}
					options={$portalDomains.map((item) => ({
						value: item.code,
						label: item.name,
						code: item.code,
						subtitle: item.subtitle ?? item.code
					}))}
					on:change={(event) =>
						updateDraft({ domain: event.detail, fileType: '', file: null, selectedAt: '' })}
				/>
			{/if}
		</div>
		<div class="field">
			<span class="lbl">{$i18n.t('Data year')} <span class="req">*</span></span>
			{#if checking}
				<div class="ro locked"><Icon name="lock" size={13} />{draft.year}</div>
			{:else}
				<Dropdown
					value={draft.year}
					placeholder={$i18n.t('Select year')}
					title={$i18n.t('Year of the figures in the file')}
					options={DATA_YEARS.map((year) => ({ value: year, label: year }))}
					on:change={(event) => updateDraft({ year: event.detail })}
				/>
			{/if}
		</div>
		{#if multipleFileTypes}
			<div class="field s3">
				<span class="lbl">{$i18n.t('File type')} <span class="req">*</span></span>
				{#if checking}
					<div class="ro locked"><Icon name="lock" size={13} />{fileType?.name}</div>
				{:else}
					<Dropdown
						value={draft.fileType}
						placeholder={$i18n.t('Select file type')}
						title={$i18n.t('File type')}
						options={(domain?.file_types ?? []).map((item) => ({
							value: item.code,
							label: item.name,
							subtitle: item.subtitle
						}))}
						on:change={(event) =>
							updateDraft({ fileType: event.detail, file: null, selectedAt: '' })}
					/>
				{/if}
			</div>
		{/if}
	</div>
</section>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<section
	class="card"
	class:over={dragging}
	on:dragover|preventDefault={() => (dragging = !fileLocked)}
	on:dragleave={() => (dragging = false)}
	on:drop|preventDefault={(event) => {
		dragging = false;
		selectFile(event.dataTransfer?.files?.[0]);
	}}
>
	<div class="card-h">
		<div>
			<h2>{$i18n.t('Attachment')}</h2>
			<div class="sub">{$i18n.t('{{count}}/1 File', { count: draft.file ? 1 : 0 })}</div>
		</div>
	</div>
	<div class="tw">
		<div class="tbox">
			<table>
				<thead>
					<tr>
						<th>{$i18n.t('File kind')}</th><th>{$i18n.t('Document name')}</th><th class="r"
							>{$i18n.t('Size')}</th
						><th>{$i18n.t('Uploader')}</th><th>{$i18n.t('Upload date')}</th><th
							>{$i18n.t('Upload status')}</th
						><th></th>
					</tr>
				</thead>
				<tbody>
					<tr>
						<td class="s">{fileTypeName}</td>
						<td class="s" style="word-break:break-all">{draft.file?.name ?? ''}</td>
						<td class="r">{draft.file ? formatKilobytes(draft.file.size) : '0,0 KB'}</td>
						<td>{draft.file ? ($user?.name ?? '') : ''}</td>
						<td>{draft.file ? draft.selectedAt : '-'}</td>
						<td>
							{#if !draft.file}<Badge label={$i18n.t('Not uploaded yet')} tone="muted" />
							{:else if !validFile}<Badge label={$i18n.t('Not an .xlsx file')} tone="err" />
							{:else if formCheck === 'ok'}<Badge
									label={$i18n.t('Selected · matches the form')}
									tone="ok"
								/>
							{:else if formCheck === 'mismatch'}<Badge
									label={$i18n.t('Does not match the form')}
									tone="err"
								/>
							{:else}<Badge label={$i18n.t('Checking the form…')} tone="muted" />{/if}
						</td>
						<td>
							<div class="row" style="gap:6px;flex-wrap:nowrap;justify-content:flex-end">
								<label
									class="iconbtn"
									class:off={fileLocked}
									title={missingSelection
										? $i18n.t('{{reason}} before choosing a file', { reason: missingSelection })
										: $i18n.t('Choose a file from your computer')}
									aria-disabled={fileLocked}
									style="cursor:{fileLocked ? 'not-allowed' : 'pointer'}"
								>
									<Icon name="up" size={16} /><span class="sr">{$i18n.t('Choose file')}</span>
									<input
										type="file"
										accept=".xlsx,.xls"
										hidden
										disabled={fileLocked}
										on:change={(event) => {
											selectFile(event.currentTarget.files?.[0]);
											event.currentTarget.value = '';
										}}
									/>
								</label>
								<button
									type="button"
									class="iconbtn"
									disabled={!draft.file || checking}
									title={$i18n.t('Download the selected file')}
									aria-label={$i18n.t('Download the selected file')}
									on:click={() => draft.file && saveFile(draft.file, draft.file.name)}
									><Icon name="down" size={16} /></button
								>
								<button
									type="button"
									class="iconbtn"
									disabled={!draft.file || checking}
									title={$i18n.t('Remove the selected file')}
									aria-label={$i18n.t('Remove the selected file')}
									on:click={() => updateDraft({ file: null, selectedAt: '' })}
									><Icon name="trash" size={16} /></button
								>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		{#if missingSelection && !draft.file}
			<p class="hint" style="margin:10px 0 0">
				<Icon name="lock" size={12} />
				{$i18n.t('{{reason}} in the card above first, then you can choose a file.', {
					reason: missingSelection
				})}
			</p>
		{/if}
	</div>
</section>
