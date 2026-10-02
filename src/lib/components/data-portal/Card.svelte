<script lang="ts">
	export let title = '';
	export let count: string | number = '';
	export let sub = '';
	export let pad = true;
</script>

<section class="card">
	{#if title || $$slots.right}
		<div class="card-h">
			<div>
				<h2>{title}{#if count !== ''} <span class="count">{count}</span>{/if}</h2>
				{#if sub}<div class="sub">{sub}</div>{/if}
				<slot name="sub" />
			</div>
			<slot name="right" />
		</div>
	{/if}
	{#if pad}<div class="card-b"><slot /></div>{:else}<slot />{/if}
</section>
