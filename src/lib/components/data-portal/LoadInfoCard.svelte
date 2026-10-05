<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import { hasMultipleFileTypes, portalDomains } from '$lib/stores/dataPortal';
	import type { Load } from '$lib/apis/data-portal/types';

	import ReadonlyCard, { type ReadonlyField } from './ReadonlyCard.svelte';
	import { formatDateTime, formatNumber } from './format';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let load: Load;
	export let detailed = false;

	$: domain = $portalDomains.find((item) => item.code === load.domain);
	$: multipleFileTypes = hasMultipleFileTypes(domain);
	$: fields = [
		{ label: $i18n.t('Information group'), value: `${load.domain} · ${domain?.name ?? ''}` },
		{ label: $i18n.t('Data year'), value: load.year },
		...(multipleFileTypes
			? [{ label: $i18n.t('File type'), value: load.file_type.name ?? '' }]
			: []),
		{ label: $i18n.t('Uploaded by'), value: load.user },
		{ label: $i18n.t('Upload time'), value: formatDateTime(load.created_at) },
		...(detailed ? detailFields() : [])
	] as ReadonlyField[];

	const detailFields = (): ReadonlyField[] => [
		multipleFileTypes
			? {
					label: $i18n.t('Taken from sheet'),
					value: load.status === 'rejected' ? '—' : (load.sheet ?? '—')
				}
			: {
					label: $i18n.t('Data month'),
					value: load.status === 'success' ? (load.months ?? '—') : '—'
				},
		{ label: $i18n.t('Total rows'), value: formatNumber(load.total_rows) }
	];
</script>

<ReadonlyCard title={$i18n.t('Upload record information')} {fields} />
