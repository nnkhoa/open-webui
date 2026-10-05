<script lang="ts">
	export let title = '';
	export let count: string | number = '';
	export let padded = true;
</script>

<section class="card">
	{#if title || $$slots.right}
		<div class="card-h">
			<div>
				<h2>
					{title}{#if count !== ''}
						<span class="count">{count}</span>{/if}
				</h2>
			</div>
			<slot name="right" />
		</div>
	{/if}
	{#if padded}<div class="card-b"><slot /></div>{:else}<slot />{/if}
</section>
