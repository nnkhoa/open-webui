import { describe, expect, it } from 'vitest';

import {
	buildOutputDisplayItems,
	getOutputText,
	type OutputDetailToken,
	type OutputDisplayItem,
	type OutputItem
} from './structuredOutput';

const reasoning = (summary: string[], extra: Partial<OutputItem> = {}): OutputItem => ({
	type: 'reasoning',
	status: 'completed',
	summary: summary.map((text) => ({ type: 'summary_text', text })),
	...extra
});

const message = (text: string): OutputItem => ({
	type: 'message',
	id: `msg-${text}`,
	content: [{ type: 'output_text', text }]
});

const toolCall = (callId: string): OutputItem => ({
	type: 'function_call',
	call_id: callId,
	name: 'execute_sql',
	arguments: '{}',
	status: 'completed'
});

const toolOutput = (callId: string, text: string): OutputItem => ({
	type: 'function_call_output',
	call_id: callId,
	output: [{ type: 'input_text', text }]
});

const tokensOf = (items: OutputDisplayItem[]): OutputDetailToken[] =>
	items.flatMap((item) =>
		item.type === 'detail_group' ? item.tokens : item.type === 'detail_single' ? [item.token] : []
	);

const reasoningTokens = (output: OutputItem[]) =>
	tokensOf(buildOutputDisplayItems(output)).filter(
		(token) => token.attributes.type === 'reasoning'
	);

describe('buildOutputDisplayItems — reasoning', () => {
	it('merges consecutive reasoning items into one block and sums durations', () => {
		const output = [
			reasoning(['**Lập kế hoạch**\n\nTruy vấn doanh thu'], { duration: 2 }),
			reasoning([], { duration: '' }),
			reasoning(['**Kiểm tra số**'], { duration: 3 }),
			message('Xong')
		];
		const tokens = reasoningTokens(output);
		expect(tokens).toHaveLength(1);
		expect(tokens[0].text).toBe(
			'> **Lập kế hoạch**\n> \n> Truy vấn doanh thu\n> \n> **Kiểm tra số**'
		);
		expect(tokens[0].attributes.duration).toBe('5');
		expect(tokens[0].attributes.done).toBe('true');
	});

	it('does not merge reasoning separated by a tool call', () => {
		const output = [reasoning(['A']), toolCall('c1'), toolOutput('c1', '[]'), reasoning(['B'])];
		const items = buildOutputDisplayItems(output);
		expect(items).toHaveLength(1);
		expect(items[0].type).toBe('detail_group');
		expect(tokensOf(items).map((token) => token.attributes.type)).toEqual([
			'reasoning',
			'tool_calls',
			'reasoning'
		]);
	});

	it('drops finished reasoning without text', () => {
		const output = [reasoning([]), toolCall('c1'), toolOutput('c1', 'ok')];
		expect(reasoningTokens(output)).toHaveLength(0);
	});

	it('keeps an empty reasoning block while it is still streaming', () => {
		const tokens = reasoningTokens([reasoning([], { status: 'in_progress' })]);
		expect(tokens).toHaveLength(1);
		expect(tokens[0].attributes.done).toBe('false');
		expect(tokens[0].summary).toBe('Thinking...');
	});

	it('streams into the merged block after finished reasoning', () => {
		const tokens = reasoningTokens([
			reasoning(['**A**']),
			reasoning([], { status: 'in_progress' })
		]);
		expect(tokens).toHaveLength(1);
		expect(tokens[0].attributes.done).toBe('false');
		expect(tokens[0].text).toBe('> **A**');
	});

	it('separates summary parts so bold headings start a new paragraph', () => {
		const tokens = reasoningTokens([reasoning(['**Một**\n\nCâu đầu.', '  **Hai**\n\nCâu sau.  '])]);
		expect(tokens[0].text).toBe('> **Một**\n> \n> Câu đầu.\n> \n> **Hai**\n> \n> Câu sau.');
	});

	it('falls back to reasoning content when there is no summary', () => {
		const tokens = reasoningTokens([
			{ type: 'reasoning', status: 'completed', content: [{ type: 'reasoning_text', text: 'raw' }] }
		]);
		expect(tokens[0].text).toBe('> raw');
	});
});

describe('buildOutputDisplayItems — tools and messages', () => {
	it('shows a finished tool call with its output', () => {
		const tokens = tokensOf(
			buildOutputDisplayItems([toolCall('c1'), toolOutput('c1', '[{"a":1}]')])
		);
		expect(tokens).toHaveLength(1);
		expect(tokens[0].summary).toBe('Tool Executed');
		expect(tokens[0].text).toBe('[{"a":1}]');
	});

	it('keeps messages between detail blocks in order', () => {
		const items = buildOutputDisplayItems([reasoning(['A']), message('Kết quả'), reasoning(['B'])]);
		expect(items.map((item) => item.type)).toEqual(['detail_single', 'message', 'detail_single']);
	});
});

describe('getOutputText', () => {
	it('joins non-empty message text only', () => {
		expect(
			getOutputText([reasoning(['nghĩ']), message('Một'), message('  '), message('Hai')])
		).toBe('Một\nHai');
	});
});
