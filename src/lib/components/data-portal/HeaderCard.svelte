<script lang="ts">
	// Thẻ đầu trang (đặc tả 12.1).
	import Icon from './Icon.svelte';
	export let title: string;
	export let desc = '';
	export let back: (() => void) | null = null;
</script>

<section class="card hcard">
	<div class="l">
		{#if back}
			<button type="button" class="back" aria-label="Quay lại" title="Quay lại" on:click={back}>
				<Icon name="arrowL" size={20} />
			</button>
		{/if}
		<div style="min-width:0">
			<h1>{title}<slot name="after" /></h1>
			{#if desc}<p class="desc">{desc}</p>{/if}
		</div>
	</div>
	{#if $$slots.actions}<div class="row"><slot name="actions" /></div>{/if}
</section>
