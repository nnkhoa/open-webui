<script lang="ts">
	// Thẻ "Các bước xử lý" dựng từ dữ liệu lần nạp (đặc tả mục 17).
	import StepTimeline from './StepTimeline.svelte';
	import { mauKetLuan } from './fmt';
	export let buoc: { ma: string; ten: string; ket_qua: string; ket_luan: string; trang_thai: 'ok' | 'err' | 'skip' }[] = [];
	export let nut: Record<string, { t: string; onClick: () => void }> = {};

	const doi = (b: (typeof buoc)[number]) => ({
		ma: b.ma,
		ten: b.ten,
		ket_qua: b.ket_qua,
		trang_thai: b.trang_thai,
		ket_luan: [b.ket_luan, mauKetLuan(b.ket_luan, b.trang_thai === 'skip')] as [string, string],
		nut: nut[b.ma] ?? null
	});
	$: nhom = [
		{ h: 'A. Kiểm tra trước khi ghi', buoc: buoc.filter((b) => b.ma.startsWith('A')).map(doi) },
		{ h: 'B. Ghi vào database và đối chiếu lại', buoc: buoc.filter((b) => b.ma.startsWith('B')).map(doi) }
	];
</script>

<StepTimeline {nhom} />
