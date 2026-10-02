<script lang="ts">
	// Thẻ thu gọn (đặc tả 12.11): cả thẻ là một nút, nội dung hiện ngay bên dưới. Mặc định đóng.
	import Icon from './Icon.svelte';
	export let title: string;
	export let open = false;
</script>

<button type="button" class="card xp" aria-expanded={open} on:click={() => (open = !open)}>
	<span class="xp-t"><b>{title}</b></span>
	<span class="xp-r">{open ? 'Thu gọn' : 'Xem chi tiết'}<Icon name={open ? 'chevUp' : 'chev'} size={16} stroke={2.2} /></span>
</button>
{#if open}<slot />{/if}
