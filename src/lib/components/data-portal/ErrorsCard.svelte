<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import { downloadLoadErrors } from '$lib/apis/data-portal';
	import type { LoadError } from '$lib/apis/data-portal/types';

	import Card from './Card.svelte';
	import DataTable from './DataTable.svelte';
	import Icon from './Icon.svelte';
	import { saveFile } from './download';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let loadId: number;
	export let errors: LoadError[] = [];

	const downloadErrors = async () => {
		const { blob, fileName } = await downloadLoadErrors(localStorage.token, loadId);
		saveFile(blob, fileName);
	};
</script>

<Card title={$i18n.t('Errors to fix')} count={errors.length} padded={false}>
	<button slot="right" type="button" class="btn sm" on:click={downloadErrors}
		><Icon name="down" size={14} />{$i18n.t('Download error list')}</button
	>
	<DataTable
		headers={[
			{ label: $i18n.t('Sheet') },
			{ label: $i18n.t('Error location') },
			{ label: $i18n.t('Issue') },
			{ label: $i18n.t('Resolution') }
		]}
		rows={errors.map((error) => ({
			cells: [
				{ value: error.sheet, className: 's' },
				{ value: error.location, className: 's' },
				{ value: error.issue, className: 's' },
				error.resolution
			]
		}))}
	/>
</Card>
