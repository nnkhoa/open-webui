<script lang="ts">
	// Lịch sử nạp — danh sách (đặc tả 16.1).
	import { goto } from '$app/navigation';
	import { dpNhom, dpNam, dpDomains, dpNap, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet } from '$lib/apis/data-portal';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import GroupYearChips from '$lib/components/data-portal/GroupYearChips.svelte';
	import Dropdown from '$lib/components/data-portal/Dropdown.svelte';
	import SearchBox from '$lib/components/data-portal/SearchBox.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import DataTable, { type Row } from '$lib/components/data-portal/DataTable.svelte';
	import Pager from '$lib/components/data-portal/Pager.svelte';
	import EmptyState from '$lib/components/data-portal/EmptyState.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import { so, thoiGian, TRANG_THAI } from '$lib/components/data-portal/fmt';

	type Dong = {
		id: number;
		ten_tep: string;
		nam: string;
		loai: { ma: string; ten: string } | null;
		nguoi: string;
		luc: string;
		so_dong: number;
		status: keyof typeof TRANG_THAI;
	};

	let loai = '';
	let tt = '';
	let nguoi = '';
	let tim = '';
	let trang = 1;
	let moi = 25;
	let du: { tong: number; nguoi_nap: string[]; dong: Dong[] } | null = null;
	let loi = '';

	$: dom = $dpDomains.find((d) => d.code === $dpNhom);
	$: gc = (dom?.loai_tep?.length ?? 0) > 1;
	$: loc = !!(tim || tt || nguoi || (gc && loai));

	const tai = async () => {
		try {
			loi = '';
			du = await dpGet('loads', {
				nhom: $dpNhom,
				nam: $dpNam,
				loai: gc ? loai : '',
				trang_thai: tt,
				nguoi,
				tim,
				trang,
				moi
			});
		} catch (e) {
			loi = (e as Error).message;
		}
	};
	$: $dpNhom, $dpNam, loai, tt, nguoi, tim, trang, moi, tai();

	const xoaLoc = () => {
		tim = '';
		tt = '';
		nguoi = '';
		loai = '';
		trang = 1;
	};
	const napMoi = () => {
		dpNap.set({ ...NAP_TRONG });
		goto('/data-portal/upload');
	};

	$: rows = (du?.dong ?? []).map(
		(L): Row => ({
			cells: [
				{ v: `#${L.id}`, bold: true, cls: 's' },
				{ v: L.ten_tep, tep: true, link: () => goto(`/data-portal/history/${L.id}/file`), linkTitle: 'Xem tệp gốc' },
				{ v: L.nam, cls: 's' },
				...(gc ? [{ v: L.loai?.ten ?? '', cls: 's' }] : []),
				L.nguoi,
				{ v: thoiGian(L.luc), cls: 'nowrap' },
				{ v: so(L.so_dong), cls: 's' },
				{ badge: TRANG_THAI[L.status] }
			],
			onClick: () =>
				goto(
					`/data-portal/history/${L.id}?tab=${L.status === 'rejected' ? 'errors' : L.status === 'mismatch' ? 'reconcile' : 'steps'}`
				),
			title: `Xem chi tiết lần nạp #${L.id}`
		})
	);
</script>

<HeaderCard title="Lịch sử nạp">
	<button slot="actions" type="button" class="btn primary" on:click={napMoi}>Nạp tệp mới</button>
</HeaderCard>

<div class="chiprow" aria-label="Bộ lọc">
	<GroupYearChips on:nhom={() => { loai = ''; trang = 1; }} on:nam={() => (trang = 1)} />
	{#if gc}
		<Dropdown
			chip="Loại tệp"
			value={loai}
			mac=""
			options={[{ v: '', t: 'Tất cả' }, ...(dom?.loai_tep ?? []).map((l) => ({ v: l.ma, t: l.ten }))]}
			on:change={(e) => { loai = e.detail; trang = 1; }}
		/>
	{/if}
	<Dropdown
		chip="Trạng thái"
		value={tt}
		mac=""
		options={[
			{ v: '', t: 'Tất cả' },
			{ v: 'success', t: 'Thành công' },
			{ v: 'rejected', t: 'Bị từ chối' },
			{ v: 'mismatch', t: 'Lỗi đối chiếu' },
			{ v: 'rolled_back', t: 'Đã gỡ' }
		]}
		on:change={(e) => { tt = e.detail; trang = 1; }}
	/>
	<Dropdown
		chip="Người nạp"
		value={nguoi}
		mac=""
		options={[{ v: '', t: 'Tất cả' }, ...(du?.nguoi_nap ?? []).map((x) => ({ v: x, t: x }))]}
		on:change={(e) => { nguoi = e.detail; trang = 1; }}
	/>
	<SearchBox value={tim} placeholder="Tìm mã hoặc tên tệp, Enter để tìm" on:search={(e) => { tim = e.detail; trang = 1; }} />
	{#if loc}<button type="button" class="xoa" on:click={xoaLoc}>Xoá bộ lọc</button>{/if}
</div>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !du}
	<p class="desc">Đang tải dữ liệu…</p>
{:else if !du.dong.length}
	<section class="card">
		{#if loc}
			<EmptyState icon="list" title="Không tìm thấy kết quả phù hợp" p="Hãy thay đổi từ khoá hoặc xoá bớt điều kiện lọc.">
				<button type="button" class="btn" on:click={xoaLoc}>Xoá bộ lọc</button>
			</EmptyState>
		{:else if $dpNam}
			<EmptyState icon="list" title="Năm {$dpNam} chưa có lần nạp nào" p="Chọn năm khác ở ô Năm dữ liệu, hoặc nạp tệp với Năm dữ liệu {$dpNam}.">
				<button type="button" class="btn primary" on:click={napMoi}>Nạp tệp mới</button>
			</EmptyState>
		{:else}
			<EmptyState icon="list" title="Chưa có lần nạp nào" p="Nhóm thông tin {dom?.name ?? ''} chưa có lần nạp nào. Hãy nạp tệp đầu tiên để bắt đầu.">
				<button type="button" class="btn primary" on:click={napMoi}>Nạp tệp đầu tiên</button>
			</EmptyState>
		{/if}
	</section>
{:else}
	<Card title="Danh sách lần nạp" count={du.tong} pad={false}>
		<DataTable
			heads={[
				{ t: 'Mã' },
				{ t: 'Tệp' },
				{ t: 'Năm dữ liệu' },
				...(gc ? [{ t: 'Loại tệp' }] : []),
				{ t: 'Người nạp' },
				{ t: 'Thời gian nạp' },
				{ t: 'Số dòng', r: true },
				{ t: 'Trạng thái' }
			]}
			{rows}
		/>
		<Pager tong={du.tong} {trang} {moi} on:change={(e) => { trang = e.detail.trang; moi = e.detail.moi; }} />
	</Card>
{/if}
