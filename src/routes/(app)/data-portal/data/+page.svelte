<script lang="ts">
	// Dữ liệu — danh sách bảng (đặc tả 19.1).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { dpNhom, dpNam, dpDomains, dpNap, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import GroupYearChips from '$lib/components/data-portal/GroupYearChips.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import DataTable, { type Row } from '$lib/components/data-portal/DataTable.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import { so, thoiGian } from '$lib/components/data-portal/fmt';

	type Bang = {
		bang: string;
		ten: string;
		mo_ta: string;
		loai: 'fact' | 'dim';
		nam: string | null;
		thang: string | null;
		loai_tep: { ma: string; ten: string; phu?: string } | null;
		load_id: number | null;
		so_dong: number;
		cap_nhat: string | null;
	};

	let ds: Bang[] | null = null;
	let loi = '';

	onMount(() => {
		const nam = $page.url.searchParams.get('nam');
		if (nam !== null) dpNam.set(nam);
	});

	$: gc = ($dpDomains.find((d) => d.code === $dpNhom)?.loai_tep?.length ?? 0) > 1;
	const tai = async (nhom: string, nam: string) => {
		try {
			loi = '';
			ds = await dpGet<Bang[]>('tables', { nhom, nam });
		} catch (e) {
			loi = (e as Error).message;
		}
	};
	$: tai($dpNhom, $dpNam);

	$: chuaCoNam = !!$dpNam && !!ds && ds.filter((b) => b.loai === 'fact').every((b) => !b.so_dong);
	const mo = (b: Bang) => () => goto(`/data-portal/data/${b.bang}?lop=gold${$dpNam && b.loai === 'fact' ? `&nam=${$dpNam}` : ''}`);
	const napDuLieu = () => {
		dpNap.set({ ...NAP_TRONG });
		goto('/data-portal/upload');
	};

	$: rows = (ds ?? []).map(
		(b): Row => ({
			cells: gc
				? [
						{ v: b.ten, bold: true, sub: b.mo_ta, cls: 's' },
						b.nam ?? '—',
						{ v: b.loai_tep?.ten ?? '', sub: b.loai_tep?.phu, cls: 's' },
						b.load_id ? `#${b.load_id}` : '—',
						{ v: so(b.so_dong), cls: 's' },
						b.so_dong ? thoiGian(b.cap_nhat) : { badge: ['Chưa nạp', 'muted'] }
					]
				: [
						{ v: b.ten, bold: true, sub: b.mo_ta, cls: 's' },
						b.loai === 'dim' ? 'Dùng chung mọi năm' : (b.nam ?? '—'),
						b.loai === 'dim' ? '—' : (b.thang ?? '—'),
						{ v: so(b.so_dong), cls: 's' },
						b.so_dong ? thoiGian(b.cap_nhat) : { badge: ['Chưa nạp', 'muted'] }
					],
			onClick: b.so_dong ? mo(b) : undefined,
			title: `Mở bảng ${b.ten}`
		})
	);
</script>

<HeaderCard title="Dữ liệu" />

<div class="chiprow" aria-label="Bộ lọc">
	<GroupYearChips />
</div>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !ds}
	<p class="desc">Đang tải dữ liệu…</p>
{:else}
	<Card title="Các bảng dữ liệu" count={ds.length} pad={false}>
		{#if chuaCoNam}
			<p class="desc" style="padding:0 24px 12px">
				Năm {$dpNam} chưa có dữ liệu. <button type="button" class="link" on:click={napDuLieu}>Nạp dữ liệu</button>
			</p>
		{/if}
		<DataTable
			heads={gc
				? [{ t: 'Bảng' }, { t: 'Năm' }, { t: 'Loại tệp' }, { t: 'Lần nạp' }, { t: 'Số dòng', r: true }, { t: 'Cập nhật lúc' }]
				: [{ t: 'Bảng' }, { t: 'Năm' }, { t: 'Tháng' }, { t: 'Số dòng', r: true }, { t: 'Cập nhật lúc' }]}
			{rows}
		/>
	</Card>
{/if}
