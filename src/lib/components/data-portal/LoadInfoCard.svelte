<script lang="ts">
	// Thẻ "Thông tin lần nạp" (đặc tả 15.4, 16.2).
	import ReadonlyCard from './ReadonlyCard.svelte';
	import { dpDomains } from '$lib/stores/dataPortal';
	import { so, thoiGian } from './fmt';
	import type { LanNap } from '$lib/apis/data-portal/types';
	export let L: LanNap;
	export let day = false; // Chi tiết lần nạp: thêm Tháng / Lấy từ sheet và Tổng số dòng

	$: dom = $dpDomains.find((d) => d.code === L.nhom);
	$: gc = (dom?.loai_tep?.length ?? 0) > 1;
	$: fields = [
		{ l: 'Nhóm thông tin', v: `${L.nhom} · ${dom?.name ?? ''}` },
		{ l: 'Năm dữ liệu', v: L.nam },
		...(gc ? [{ l: 'Loại tệp', v: L.loai?.ten ?? '' }] : []),
		{ l: 'Người nạp', v: L.nguoi },
		{ l: 'Thời gian nạp', v: thoiGian(L.luc) },
		...(day
			? [
					gc
						? { l: 'Lấy từ sheet', v: L.status === 'rejected' ? '—' : (L.sheet ?? '—') }
						: { l: 'Tháng', v: L.status === 'success' ? (L.thang ?? '—') : '—' },
					{ l: 'Tổng số dòng', v: so(L.tong_so_dong) }
				]
			: [])
	];
</script>

<ReadonlyCard title="Thông tin lần nạp" {fields} />
