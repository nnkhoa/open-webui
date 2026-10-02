<script lang="ts">
	// Hai ô chọn đầu hàng lọc: Nhóm thông tin, Năm dữ liệu — dùng chung giữa các màn (đặc tả 12.4, CN-02).
	import { createEventDispatcher, onMount } from 'svelte';
	import Dropdown from './Dropdown.svelte';
	import LockedChip from './LockedChip.svelte';
	import { dpNhom, dpNam, dpDomains, DP_NAM } from '$lib/stores/dataPortal';
	import { dpGet } from '$lib/apis/data-portal';

	export let khoaNam = false; // bảng danh mục: "Năm dữ liệu: Mọi năm"
	export let coNam = true;
	const dispatch = createEventDispatcher<{ nhom: string; nam: string }>();

	onMount(async () => {
		if (!$dpDomains.length) dpDomains.set(await dpGet('domains'));
	});
</script>

<Dropdown
	chip="Nhóm thông tin"
	title="Chọn nhóm thông tin"
	value={$dpNhom}
	mac={$dpNhom}
	options={$dpDomains.map((d) => ({ v: d.code, t: d.name, ma: d.code, phu: d.phu ?? d.code }))}
	on:change={(e) => {
		dpNhom.set(e.detail);
		dispatch('nhom', e.detail);
	}}
/>
{#if coNam}
	{#if khoaNam}
		<LockedChip label="Năm dữ liệu" value="Mọi năm" />
	{:else}
		<Dropdown
			chip="Năm dữ liệu"
			title="Năm dữ liệu"
			value={$dpNam}
			mac=""
			options={[{ v: '', t: 'Tất cả năm' }, ...DP_NAM.map((y) => ({ v: y, t: y }))]}
			on:change={(e) => {
				dpNam.set(e.detail);
				dispatch('nam', e.detail);
			}}
		/>
	{/if}
{/if}
