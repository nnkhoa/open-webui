<script lang="ts">
	// Ô chọn dùng chung — một kiểu cho mọi danh sách chọn (đặc tả 12.3).
	import { createEventDispatcher, onDestroy } from 'svelte';
	import Icon from './Icon.svelte';

	export let value: string = '';
	export let options: { v: string; t: string; phu?: string; ma?: string }[] = [];
	export let placeholder = '';
	export let title = '';
	export let chip = ''; // nhãn dạng chip "Nhãn: giá trị"
	export let mac = ''; // giá trị mặc định của chip (khác thì tô tím)
	export let up = false; // xổ lên trên (ô "Số dòng / trang")
	export let disabled = false;
	export let id = '';

	const dispatch = createEventDispatcher<{ change: string }>();
	let open = false;
	let el: HTMLDivElement;

	$: cur = options.find((o) => o.v === value);
	$: set = !!chip && value !== mac;

	const chon = (v: string) => {
		open = false;
		if (v !== value) {
			value = v;
			dispatch('change', v);
		}
	};
	const ngoai = (e: MouseEvent) => {
		if (open && el && !el.contains(e.target as Node)) open = false;
	};
	const phim = (e: KeyboardEvent) => {
		if (open && e.key === 'Escape') open = false;
	};
	if (typeof document !== 'undefined') {
		document.addEventListener('mousedown', ngoai);
		document.addEventListener('keydown', phim);
	}
	onDestroy(() => {
		if (typeof document !== 'undefined') {
			document.removeEventListener('mousedown', ngoai);
			document.removeEventListener('keydown', phim);
		}
	});
</script>

<div class="dom" class:f={!chip && !up} bind:this={el}>
	<button
		type="button"
		{id}
		class="dom-pill"
		class:chip={!!chip}
		class:set
		aria-haspopup="listbox"
		aria-expanded={open}
		{disabled}
		on:click={() => (open = !open)}
	>
		{#if chip}<span class="k">{chip}:</span>{/if}
		{#if cur?.ma}<b>{cur.ma}</b><span class="sep">·</span>{/if}
		<span class="nm" style={cur ? '' : 'color:var(--faint)'}>{cur ? cur.t : placeholder}</span>
		<Icon name="chev" size={14} stroke={2.5} />
	</button>
	{#if open}
		<div class="panel" role="listbox" style={up ? 'top:auto;bottom:calc(100% + 6px)' : ''}>
			{#if title}<div class="panel-h">{title}</div>{/if}
			{#each options as o (o.v)}
				<button
					type="button"
					class="dd-item"
					class:on={o.v === value}
					role="option"
					aria-selected={o.v === value}
					on:click={() => chon(o.v)}
				>
					<span class="dom-t" style="flex:1">
						{#if o.phu}<small>{o.phu}</small>{/if}
						<b>{o.t}</b>
					</span>
					{#if o.v === value}<Icon name="check" size={18} className="i-ok" />{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
