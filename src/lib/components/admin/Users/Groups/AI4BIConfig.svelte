<script lang="ts">
	import { getContext } from 'svelte';
	const i18n = getContext('i18n');

	export let data = {};

	const ensureAi4bi = () => {
		if (!data) data = {};
		if (!data.ai4bi) data.ai4bi = {};
		if (!Array.isArray(data.ai4bi.allowed_tables)) data.ai4bi.allowed_tables = [];
	};

	$: ensureAi4bi();

	const updateAllowedTables = (value: string) => {
		ensureAi4bi();
		data.ai4bi.allowed_tables = value
			.split(',')
			.map((item) => item.trim())
			.filter(Boolean);
	};
</script>

<div class="space-y-4">
	<div>
		<div class="mb-1 text-xs text-gray-500">{$i18n.t('MCP URL')}</div>
		<input
			class="w-full text-sm bg-transparent placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-hidden"
			type="text"
			bind:value={data.ai4bi.mcp_url}
			placeholder="postgresql://sales_user:***@host:5432/aibi_demo"
			autocomplete="off"
		/>
		<div class="mt-1 text-[11px] text-gray-500">
			{$i18n.t('Có thể để trống ở bản đầu tiên nếu toàn hệ thống vẫn dùng chung 1 MCP, nhưng nên cấu hình riêng cho từng group khi rollout production.')}
		</div>
	</div>

	<div>
		<div class="mb-1 text-xs text-gray-500">{$i18n.t('Allowed Tables')}</div>
		<textarea
			class="w-full text-sm bg-transparent placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-hidden resize-none"
			rows="4"
			placeholder="orders, customers, products"
			value={(data?.ai4bi?.allowed_tables || []).join(', ')}
			on:input={(e) => updateAllowedTables(e.currentTarget.value)}
		/>
		<div class="mt-1 text-[11px] text-gray-500">
			{$i18n.t('Nhập danh sách bảng được phép truy cập, phân tách bằng dấu phẩy.')}
		</div>
	</div>

	<div>
		<div class="mb-1 text-xs text-gray-500">{$i18n.t('Denied Message')}</div>
		<input
			class="w-full text-sm bg-transparent placeholder:text-gray-300 dark:placeholder:text-gray-700 outline-hidden"
			type="text"
			bind:value={data.ai4bi.denied_message}
			placeholder="Bạn không có quyền truy cập dữ liệu được yêu cầu. Vui lòng liên hệ admin."
			autocomplete="off"
		/>
	</div>
</div>
