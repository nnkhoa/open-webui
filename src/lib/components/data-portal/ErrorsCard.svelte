<script lang="ts">
	// Thẻ "Lỗi cần sửa" (đặc tả 15.5, 16.2).
	import Card from './Card.svelte';
	import DataTable from './DataTable.svelte';
	import Icon from './Icon.svelte';
	import { dpDownload, luuTep } from '$lib/apis/data-portal';
	export let loadId: number;
	export let loi: { sheet: string; vi_tri: string; van_de: string; cach_xu_ly: string }[] = [];

	const tai = async () => {
		const { blob, ten } = await dpDownload(`loads/${loadId}/errors.csv`, undefined, `loi-lan-nap-${loadId}.csv`);
		luuTep(blob, ten);
	};
</script>

<Card title="Lỗi cần sửa" count={loi.length} pad={false}>
	<button slot="right" type="button" class="btn sm" on:click={tai}><Icon name="down" size={14} />Tải danh sách lỗi</button>
	<DataTable
		heads={[{ t: 'Sheet' }, { t: 'Vị trí' }, { t: 'Vấn đề' }, { t: 'Cách xử lý' }]}
		rows={loi.map((e) => ({
			cells: [
				{ v: e.sheet, cls: 's' },
				{ v: e.vi_tri, cls: 's' },
				{ v: e.van_de, cls: 's' },
				e.cach_xu_ly
			]
		}))}
	/>
</Card>
