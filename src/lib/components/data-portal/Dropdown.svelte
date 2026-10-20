<script context="module" lang="ts">
	export type DropdownOption = {
		value: string;
		label: string;
		subtitle?: string | null;
		code?: string;
	};
</script>

<script lang="ts">
	import { createEventDispatcher, onDestroy } from 'svelte';

	import Icon from './Icon.svelte';

	export let value = '';
	export let options: DropdownOption[] = [];
	export let placeholder = '';
	export let title = '';
	export let chipLabel = '';
	export let defaultValue = '';
	export let dropUp = false;
	export let disabled = false;
	export let id = '';

	const dispatch = createEventDispatcher<{ change: string }>();

	let open = false;
	let container: HTMLDivElement;

	$: current = options.find((option) => option.value === value);
	$: changed = !!chipLabel && value !== defaultValue;

	const select = (optionValue: string) => {
		open = false;
		if (optionValue !== value) {
			value = optionValue;
			dispatch('change', optionValue);
		}
	};

	const onDocumentMousedown = (event: MouseEvent) => {
		if (open && container && !container.contains(event.target as Node)) open = false;
	};

	const onDocumentKeydown = (event: KeyboardEvent) => {
		if (open && event.key === 'Escape') open = false;
	};

	if (typeof document !== 'undefined') {
		document.addEventListener('mousedown', onDocumentMousedown);
		document.addEventListener('keydown', onDocumentKeydown);
	}

	onDestroy(() => {
		if (typeof document !== 'undefined') {
			document.removeEventListener('mousedown', onDocumentMousedown);
			document.removeEventListener('keydown', onDocumentKeydown);
		}
	});
</script>

<div class="dropdown" class:f={!chipLabel && !dropUp} bind:this={container}>
	<button
		type="button"
		{id}
		class="dropdown-pill"
		class:chip={!!chipLabel}
		class:set={changed}
		aria-haspopup="listbox"
		aria-expanded={open}
		{disabled}
		on:click={() => (open = !open)}
	>
		{#if chipLabel}<span class="k">{chipLabel}:</span>{/if}
		{#if current?.code}<b>{current.code}</b><span class="sep">·</span>{/if}
		<span class="nm" style={current ? '' : 'color:var(--faint)'}
			>{current ? current.label : placeholder}</span
		>
		<Icon name="chev" size={14} stroke={2.5} />
	</button>
	{#if open}
		<div class="panel" role="listbox" style={dropUp ? 'top:auto;bottom:calc(100% + 6px)' : ''}>
			{#if title}<div class="panel-h">{title}</div>{/if}
			{#each options as option (option.value)}
				<button
					type="button"
					class="dd-item"
					class:on={option.value === value}
					role="option"
					aria-selected={option.value === value}
					on:click={() => select(option.value)}
				>
					<span class="dropdown-option" style="flex:1">
						{#if option.subtitle}<small>{option.subtitle}</small>{/if}
						<b>{option.label}</b>
					</span>
					{#if option.value === value}<Icon name="check" size={18} className="i-ok" />{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
