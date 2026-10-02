<script lang="ts">
	// Ô chọn bị khoá (ví dụ "Năm dữ liệu: Mọi năm").
	import Icon from './Icon.svelte';
	export let label: string;
	export let value: string;
</script>

<span class="dom-pill chip khoa"><Icon name="lock" size={13} /><span class="k">{label}:</span><span class="nm">{value}</span></span>
