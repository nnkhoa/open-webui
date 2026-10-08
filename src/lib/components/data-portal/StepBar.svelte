<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let current = 0;
	export let failedStep = -1;
	export let withFileType = false;
	export let backLinks: Record<number, { title: string; onClick: () => void }> = {};

	$: labels = [
		withFileType
			? $i18n.t('Select group, month, year, file type and file')
			: $i18n.t('Select group, year and file'),
		$i18n.t('Check file'),
		$i18n.t('Confirm adding new data'),
		$i18n.t('Result')
	];

	const stepState = (index: number) => {
		if (failedStep >= 0) return index < failedStep ? 'done' : index === failedStep ? 'err' : '';
		return index < current ? 'done' : index === current ? 'on' : '';
	};

	const stepMarker = (index: number) => {
		const state = stepState(index);
		return state === 'done' ? '✓' : state === 'err' ? '!' : String(index + 1);
	};
</script>

<section class="card flowbar" aria-label={$i18n.t('Upload steps')}>
	{#each labels as label, index}
		{#if index}<span class="fs-line" aria-hidden="true"></span>{/if}
		{#if backLinks[index]}
			<button
				type="button"
				class="fs {stepState(index)} fs-back"
				title={backLinks[index].title}
				on:click={backLinks[index].onClick}
			>
				<span class="n">{stepMarker(index)}</span>{label}
			</button>
		{:else}
			<span
				class="fs {stepState(index)}"
				aria-current={stepState(index) === 'on' || stepState(index) === 'err' ? 'step' : undefined}
			>
				<span class="n">{stepMarker(index)}</span>{label}
			</span>
		{/if}
	{/each}
</section>
