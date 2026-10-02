<script context="module" lang="ts">
	export type Buoc = {
		ma: string; // A1…B5
		ten: string;
		ket_qua: string;
		ket_luan: [string, string]; // [chữ, màu]
		trang_thai: 'ok' | 'err' | 'skip';
		nut?: { t: string; onClick: () => void } | null;
	};
</script>

<script lang="ts">
	// Thẻ "Các bước xử lý" (đặc tả mục 17).
	import Badge from './Badge.svelte';
	export let nhom: { h: string; buoc: Buoc[] }[] = [];
</script>

<section class="card">
	<div class="card-h"><div><h2>Các bước xử lý</h2></div></div>
	{#each nhom as g}
		<div class="tl-g"><h3>{g.h}</h3></div>
		<div class="tl">
			{#each g.buoc as b}
				<div class="tl-i {b.trang_thai}">
					<span class="n">{b.trang_thai === 'ok' ? '✓' : b.trang_thai === 'err' ? '!' : '–'}</span>
					<div style="min-width:0">
						<h4>{b.ma}. {b.ten}</h4>
						<p class="kt">{b.ket_qua}</p>
					</div>
					<div class="tl-r">
						<Badge t={b.ket_luan[0]} k={b.ket_luan[1]} />
						{#if b.nut}<button type="button" class="btn sm" on:click={b.nut.onClick}>{b.nut.t}</button>{/if}
					</div>
				</div>
			{/each}
		</div>
	{/each}
</section>
