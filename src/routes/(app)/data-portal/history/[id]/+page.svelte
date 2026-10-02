<script lang="ts">
	// Chi tiết lần nạp (đặc tả 16.2) và hộp thoại Gỡ dữ liệu / Xoá lịch sử (16.4, HT-01, HT-02).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { toast } from 'svelte-sonner';
	import { user } from '$lib/stores';
	import { dpDomains } from '$lib/stores/dataPortal';
	import { dpGet, dpSend, DpError } from '$lib/apis/data-portal';
	import type { LanNap } from '$lib/apis/data-portal/types';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Tabs from '$lib/components/data-portal/Tabs.svelte';
	import StepsCard from '$lib/components/data-portal/StepsCard.svelte';
	import ReconcileCards from '$lib/components/data-portal/ReconcileCards.svelte';
	import ErrorsCard from '$lib/components/data-portal/ErrorsCard.svelte';
	import LoadInfoCard from '$lib/components/data-portal/LoadInfoCard.svelte';
	import Dialog from '$lib/components/data-portal/Dialog.svelte';
	import Card from '$lib/components/data-portal/Card.svelte';
	import { so, TRANG_THAI } from '$lib/components/data-portal/fmt';

	let L: LanNap | null = null;
	let loi = '';
	let hoi: '' | 'go' | 'xoa' = '';
	let ban = false;

	$: id = Number($page.params.id);
	$: tab = $page.url.searchParams.get('tab') ?? 'steps';
	$: admin = $user?.role === 'admin';
	$: gc = ($dpDomains.find((d) => d.code === L?.nhom)?.loai_tep?.length ?? 0) > 1;

	onMount(async () => {
		try {
			if (!$dpDomains.length) dpDomains.set(await dpGet('domains'));
			L = await dpGet<LanNap>(`loads/${id}`);
		} catch (e) {
			loi = (e as Error).message;
		}
	});

	const doiTab = (t: string) => goto(`/data-portal/history/${id}?tab=${t}`, { replaceState: true, noScroll: true });
	const xemDuLieu = () => {
		if (!L) return;
		if (gc) goto(`/data-portal/data/${L.bang_chinh}?lop=gold&nam=${L.nam}`);
		else goto(`/data-portal/data?nam=${L.nam}`);
	};
	const xoa = async () => {
		ban = true;
		try {
			await dpSend('DELETE', `loads/${id}`);
			hoi = '';
			goto('/data-portal/history');
		} catch (e) {
			hoi = '';
			toast.error(e instanceof DpError ? e.message : String(e));
		} finally {
			ban = false;
		}
	};
</script>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !L}
	<p class="desc">Đang tải dữ liệu…</p>
{:else}
	<HeaderCard title="Lần nạp #{L.id}" desc={L.ten_tep} back={() => goto('/data-portal/history')}>
		<span slot="after"><Badge t={TRANG_THAI[L.status][0]} k={TRANG_THAI[L.status][1]} /></span>
		<svelte:fragment slot="actions">
			{#if admin}
				{#if L.status === 'success'}
					<button type="button" class="btn danger" title="Xoá hẳn dữ liệu của lần nạp này khỏi database" on:click={() => (hoi = 'go')}>Gỡ dữ liệu</button>
				{:else}
					<button type="button" class="btn danger" on:click={() => (hoi = 'xoa')}>Xoá lịch sử</button>
				{/if}
			{/if}
			<button type="button" class="btn" on:click={() => goto(`/data-portal/history/${id}/file`)}>Xem tệp gốc</button>
			{#if L.status === 'success'}
				<button type="button" class="btn primary" on:click={xemDuLieu}>Xem dữ liệu liên quan</button>
			{/if}
		</svelte:fragment>
	</HeaderCard>

	<LoadInfoCard {L} day />

	<Tabs
		active={tab}
		tabs={[
			{ id: 'steps', t: 'Các bước xử lý' },
			{ id: 'reconcile', t: 'Đối chiếu tệp gốc ↔ database' },
			{ id: 'errors', t: 'Lỗi', n: L.loi.length }
		]}
		on:change={(e) => doiTab(e.detail)}
	/>

	{#if tab === 'steps'}
		{#if L.status === 'rejected'}
			<Banner k="err" icon="x" title="Tệp chưa được xử lý" p="Tệp có {L.loi.length} lỗi, chưa ghi gì vào database." />
		{:else if L.status === 'mismatch'}
			<Banner k="err" icon="alert" title="Phát hiện chênh lệch khi đối chiếu" p="Đã huỷ toàn bộ, dữ liệu cũ giữ nguyên." />
		{/if}
		<StepsCard buoc={L.buoc} />
	{:else if tab === 'reconcile'}
		<ReconcileCards loadId={L.id} nam={L.nam} />
	{:else if L.loi.length}
		<ErrorsCard loadId={L.id} loi={L.loi} />
	{:else}
		<Card title="Lỗi cần sửa"><p class="desc">Lần nạp này không có lỗi nào.</p></Card>
	{/if}
{/if}

{#if hoi && L}
	<Dialog label={hoi === 'go' ? 'Gỡ dữ liệu' : 'Xoá lịch sử'} on:close={() => (hoi = '')}>
		{#if hoi === 'go'}
			<h2>Gỡ dữ liệu của lần nạp #{L.id}?</h2>
			<p>
				Tệp {L.ten_tep} có {so(L.tong_so_dong)} dòng dữ liệu gốc. Mọi thông tin của lần nạp này sẽ bị xoá hẳn: dữ liệu ở cả ba lớp
				gốc, chuẩn hoá, phân tích, kết quả đối chiếu, lịch sử và tệp đã tải lên. Nếu lần nạp này đã thay dữ liệu của lần nạp trước
				({gc ? 'cùng loại tệp' : 'cùng tháng'}), dữ liệu của lần trước được dùng lại.
			</p>
		{:else}
			<h2>Xoá lần nạp #{L.id} khỏi lịch sử?</h2>
			<p>Thao tác này xoá bản ghi lịch sử của tệp {L.ten_tep}. Tệp này không có dữ liệu đang được sử dụng.</p>
		{/if}
		<div class="row" style="justify-content:flex-end;margin-top:4px">
			<button type="button" class="btn" on:click={() => (hoi = '')}>Huỷ</button>
			<button type="button" class="btn danger-solid" disabled={ban} on:click={xoa}>{hoi === 'go' ? 'Gỡ dữ liệu' : 'Xoá lịch sử'}</button>
		</div>
	</Dialog>
{/if}
