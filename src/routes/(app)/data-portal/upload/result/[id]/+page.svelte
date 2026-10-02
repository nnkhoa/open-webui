<script lang="ts">
	// Nạp dữ liệu — bước 4: Kết quả (đặc tả 15.4, 15.5).
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { dpNap, dpDomains, NAP_TRONG } from '$lib/stores/dataPortal';
	import { dpGet } from '$lib/apis/data-portal';
	import type { LanNap } from '$lib/apis/data-portal/types';
	import HeaderCard from '$lib/components/data-portal/HeaderCard.svelte';
	import StepBar from '$lib/components/data-portal/StepBar.svelte';
	import Badge from '$lib/components/data-portal/Badge.svelte';
	import Banner from '$lib/components/data-portal/Banner.svelte';
	import Collapsible from '$lib/components/data-portal/Collapsible.svelte';
	import StepsCard from '$lib/components/data-portal/StepsCard.svelte';
	import ReconcileCards from '$lib/components/data-portal/ReconcileCards.svelte';
	import ErrorsCard from '$lib/components/data-portal/ErrorsCard.svelte';
	import LoadInfoCard from '$lib/components/data-portal/LoadInfoCard.svelte';
	import { so, TRANG_THAI } from '$lib/components/data-portal/fmt';

	let L: LanNap | null = null;
	let loi = '';
	let moBuoc = false;
	let moDc = false;

	$: id = Number($page.params.id);
	onMount(async () => {
		try {
			if (!$dpDomains.length) dpDomains.set(await dpGet('domains'));
			L = await dpGet<LanNap>(`loads/${id}`);
		} catch (e) {
			loi = (e as Error).message;
		}
	});

	$: gc = ($dpDomains.find((d) => d.code === L?.nhom)?.loai_tep?.length ?? 0) > 1;
	const napKhac = () => {
		dpNap.set({ ...NAP_TRONG });
		goto('/data-portal/upload');
	};
	const xemDuLieu = () => L && goto(`/data-portal/data/${L.bang_chinh ?? 'fact_ket_qua_kd'}?lop=gold&nam=${L.nam}`);
</script>

{#if loi}
	<Banner k="err" icon="x" title={loi} />
{:else if !L}
	<p class="desc">Đang tải dữ liệu…</p>
{:else}
	<HeaderCard title="Kết quả nạp · lần nạp #{L.id}" desc={L.ten_tep}>
		<span slot="after"><Badge t={TRANG_THAI[L.status][0]} k={TRANG_THAI[L.status][1]} /></span>
		<svelte:fragment slot="actions">
			<button type="button" class="btn" on:click={() => goto('/data-portal/history')}>Về lịch sử nạp</button>
			{#if L.status === 'success'}
				<button type="button" class="btn" title="Quay lại bước 1 để nạp tệp tiếp theo" on:click={napKhac}>Nạp tệp khác</button>
				<button type="button" class="btn primary" on:click={xemDuLieu}>Xem dữ liệu vừa nạp</button>
			{:else if L.status === 'rejected'}
				<button type="button" class="btn primary" title="Quay lại bước 1 để chọn tệp đã sửa lỗi" on:click={napKhac}>Chọn tệp đã sửa</button>
			{:else}
				<button type="button" class="btn primary" on:click={() => goto(`/data-portal/history/${L?.id}?tab=reconcile`)}>Xem chi tiết lần nạp</button>
			{/if}
		</svelte:fragment>
	</HeaderCard>

	<StepBar i={4} loi={L.status === 'rejected' ? 1 : L.status === 'mismatch' ? 3 : -1} {gc} />

	<LoadInfoCard {L} />

	{#if L.status === 'success'}
		<Banner k="ok" icon="check" big title="Nạp dữ liệu thành công" p="{so(L.so_dong_ghi)} dòng đã vào database. Mọi bước đối chiếu khớp." />
	{:else if L.status === 'rejected'}
		<Banner k="err" icon="x" big title="Tệp chưa được xử lý" p="Tệp có {L.loi.length} lỗi, chưa ghi gì vào database." />
		<ErrorsCard loadId={L.id} loi={L.loi} />
	{:else}
		<Banner k="err" icon="alert" big title="Phát hiện chênh lệch khi đối chiếu" p="Đã huỷ toàn bộ, dữ liệu cũ giữ nguyên." />
	{/if}

	<Collapsible title="Các bước xử lý" bind:open={moBuoc}>
		<StepsCard buoc={L.buoc} />
	</Collapsible>
	{#if L.status !== 'rejected'}
		<Collapsible title="Đối chiếu tệp gốc ↔ database" bind:open={moDc}>
			<ReconcileCards loadId={L.id} nam={L.nam} />
		</Collapsible>
	{/if}
{/if}
