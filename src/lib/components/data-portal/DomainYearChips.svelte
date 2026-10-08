<script lang="ts">
	import { createEventDispatcher, getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import {
		DATA_YEARS,
		loadPortalDomains,
		portalDomains,
		selectedDomain,
		selectedYear
	} from '$lib/stores/dataPortal';

	import Dropdown from './Dropdown.svelte';
	import LockedChip from './LockedChip.svelte';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let yearLocked = false;

	const dispatch = createEventDispatcher<{ domain: string; year: string }>();

	onMount(loadPortalDomains);
</script>

<Dropdown
	chipLabel={$i18n.t('Information group')}
	title={$i18n.t('Select information group')}
	value={$selectedDomain}
	defaultValue={$selectedDomain}
	options={$portalDomains.map((domain) => ({
		value: domain.code,
		label: domain.name,
		code: domain.code,
		subtitle: domain.subtitle ?? domain.code
	}))}
	on:change={(event) => {
		selectedDomain.set(event.detail);
		dispatch('domain', event.detail);
	}}
/>
<slot name="month" />
{#if yearLocked}
	<LockedChip label={$i18n.t('Data year')} value={$i18n.t('Every year')} />
{:else}
	<Dropdown
		chipLabel={$i18n.t('Data year')}
		title={$i18n.t('Data year')}
		value={$selectedYear}
		defaultValue=""
		options={[
			{ value: '', label: $i18n.t('All years') },
			...DATA_YEARS.map((year) => ({ value: year, label: year }))
		]}
		on:change={(event) => {
			selectedYear.set(event.detail);
			dispatch('year', event.detail);
		}}
	/>
{/if}
