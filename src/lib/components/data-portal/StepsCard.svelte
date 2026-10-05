<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import type { Step } from '$lib/apis/data-portal/types';

	import Badge from './Badge.svelte';
	import { verdictTone } from './format';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let steps: Step[] = [];

	$: groups = [
		{
			title: $i18n.t('A. Checks before writing'),
			steps: steps.filter((step) => step.code.startsWith('A'))
		},
		{
			title: $i18n.t('B. Write to the database and reconcile'),
			steps: steps.filter((step) => step.code.startsWith('B'))
		}
	];

	const statusMarker = (step: Step) =>
		step.status === 'ok' ? '✓' : step.status === 'err' ? '!' : '–';
</script>

<section class="card">
	<div class="card-h"><div><h2>{$i18n.t('Processing steps')}</h2></div></div>
	{#each groups as group}
		<div class="tl-g"><h3>{group.title}</h3></div>
		<div class="tl">
			{#each group.steps as step}
				<div class="tl-i {step.status}">
					<span class="n">{statusMarker(step)}</span>
					<div style="min-width:0">
						<h4>{step.code}. {step.name}</h4>
						<p class="step-result">{step.result}</p>
					</div>
					<div class="tl-r">
						<Badge label={step.verdict} tone={verdictTone(step.verdict, step.status === 'skip')} />
					</div>
				</div>
			{/each}
		</div>
	{/each}
</section>
