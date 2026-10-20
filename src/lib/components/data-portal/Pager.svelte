<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Dropdown from './Dropdown.svelte';
	import Icon from './Icon.svelte';
	import { formatNumber } from './format';

	const i18n: Writable<i18nType> = getContext('i18n');

	const PAGE_SIZES = ['25', '50', '100'];
	const GAP = '…';

	export let total = 0;
	export let page = 1;
	export let pageSize = 25;

	const dispatch = createEventDispatcher<{ change: { page: number; pageSize: number } }>();

	$: pageCount = Math.max(1, Math.ceil(total / pageSize));
	$: firstRow = total ? (page - 1) * pageSize + 1 : 0;
	$: lastRow = Math.min(page * pageSize, total);
	$: pageNumbers = visiblePages(page, pageCount);

	const visiblePages = (currentPage: number, count: number) => {
		const pages: (number | typeof GAP)[] = [];
		for (let number = 1; number <= count; number++) {
			if (number === 1 || number === count || Math.abs(number - currentPage) <= 1)
				pages.push(number);
			else if (pages[pages.length - 1] !== GAP) pages.push(GAP);
		}
		return pages;
	};

	const goTo = (target: number) => dispatch('change', { page: target, pageSize });
</script>

<div class="pager">
	<div class="l">
		<span>{$i18n.t('Rows per page')}</span>
		<Dropdown
			value={String(pageSize)}
			dropUp
			options={PAGE_SIZES.map((size) => ({ value: size, label: size }))}
			on:change={(event) => dispatch('change', { page: 1, pageSize: Number(event.detail) })}
		/>
		<span
			>{$i18n.t('{{first}}–{{last}} of {{total}} rows', {
				first: formatNumber(firstRow),
				last: formatNumber(lastRow),
				total: formatNumber(total)
			})}</span
		>
	</div>
	<nav class="pg" aria-label={$i18n.t('Pagination')}>
		<button type="button" disabled={page <= 1} on:click={() => goTo(page - 1)}
			><Icon name="back" size={14} />{$i18n.t('Previous')}</button
		>
		{#each pageNumbers as number}
			{#if number === GAP}
				<span class="gap">{GAP}</span>
			{:else}
				<button
					type="button"
					class:on={number === page}
					aria-current={number === page ? 'page' : undefined}
					on:click={() => goTo(Number(number))}>{number}</button
				>
			{/if}
		{/each}
		<button type="button" disabled={page >= pageCount} on:click={() => goTo(page + 1)}
			>{$i18n.t('Next')}<Icon name="fwd" size={14} /></button
		>
	</nav>
</div>
