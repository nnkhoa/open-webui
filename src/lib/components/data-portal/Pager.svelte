<script lang="ts">
	// Phân trang (đặc tả 12.7).
	import { createEventDispatcher } from 'svelte';
	import Dropdown from './Dropdown.svelte';
	import Icon from './Icon.svelte';
	import { so } from './fmt';

	export let tong = 0;
	export let trang = 1;
	export let moi = 25;

	const dispatch = createEventDispatcher<{ change: { trang: number; moi: number } }>();

	$: soTrang = Math.max(1, Math.ceil(tong / moi));
	$: tu = (trang - 1) * moi;
	$: den = Math.min(trang * moi, tong);
	$: nums = (() => {
		const ds: (number | '…')[] = [];
		for (let i = 1; i <= soTrang; i++) {
			if (i === 1 || i === soTrang || Math.abs(i - trang) <= 1) ds.push(i);
			else if (ds[ds.length - 1] !== '…') ds.push('…');
		}
		return ds;
	})();
	const di = (t: number) => dispatch('change', { trang: t, moi });
</script>

<div class="pager">
	<div class="l">
		<span>Số dòng / trang</span>
		<Dropdown
			value={String(moi)}
			up
			options={[
				{ v: '25', t: '25' },
				{ v: '50', t: '50' },
				{ v: '100', t: '100' }
			]}
			on:change={(e) => dispatch('change', { trang: 1, moi: Number(e.detail) })}
		/>
		<span>{so(tong ? tu + 1 : 0)}–{so(den)} trên {so(tong)} dòng</span>
	</div>
	<nav class="pg" aria-label="Phân trang">
		<button type="button" disabled={trang <= 1} on:click={() => di(trang - 1)}
			><Icon name="back" size={14} />Lùi</button
		>
		{#each nums as n}
			{#if n === '…'}
				<span class="gap">…</span>
			{:else}
				<button
					type="button"
					class:on={n === trang}
					aria-current={n === trang ? 'page' : undefined}
					on:click={() => di(Number(n))}>{n}</button
				>
			{/if}
		{/each}
		<button type="button" disabled={trang >= soTrang} on:click={() => di(trang + 1)}
			>Tới<Icon name="fwd" size={14} /></button
		>
	</nav>
</div>
