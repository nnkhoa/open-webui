<script lang="ts">
	// Thanh các bước nạp (đặc tả 12.10). i = bước đang làm (4 = xong hết); loi = bước bị lỗi.
	export let i = 0;
	export let loi = -1;
	export let gc = false;
	export let quay: Record<number, { title: string; onClick: () => void }> = {};

	$: ten = [
		gc ? 'Chọn nhóm, năm, loại tệp và tệp' : 'Chọn nhóm, năm và tệp',
		'Kiểm tra tệp',
		'Xác nhận thêm mới dữ liệu',
		'Kết quả'
	];
	const tt = (k: number) =>
		loi >= 0 ? (k < loi ? 'done' : k === loi ? 'err' : '') : k < i ? 'done' : k === i ? 'on' : '';
</script>

<section class="card flowbar" aria-label="Các bước nạp">
	{#each ten as t, k}
		{#if k}<span class="fs-line" aria-hidden="true"></span>{/if}
		{#if quay[k]}
			<button type="button" class="fs {tt(k)} fs-back" title={quay[k].title} on:click={quay[k].onClick}>
				<span class="n">{tt(k) === 'done' ? '✓' : tt(k) === 'err' ? '!' : k + 1}</span>{t}
			</button>
		{:else}
			<span class="fs {tt(k)}" aria-current={tt(k) === 'on' || tt(k) === 'err' ? 'step' : undefined}>
				<span class="n">{tt(k) === 'done' ? '✓' : tt(k) === 'err' ? '!' : k + 1}</span>{t}
			</span>
		{/if}
	{/each}
</section>
