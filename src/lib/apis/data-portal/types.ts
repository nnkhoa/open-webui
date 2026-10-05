export type FileType = {
	code: string;
	name: string;
	subtitle?: string | null;
};

export type Domain = {
	code: string;
	name: string;
	subtitle: string;
	file_types: FileType[];
};

export type LoadStatus = 'success' | 'rejected' | 'mismatch' | 'rolled_back';

export type UploadForm = {
	domain: string;
	year: string;
	fileType?: string;
	file: File;
};

export type UploadResult = {
	pending_id?: string;
	load_id?: number;
	status?: LoadStatus;
};

export type ConfirmedUpload = {
	load_id: number;
	status: LoadStatus;
};

export type LoadSummary = {
	load_id: number;
	created_at: string;
	user: string;
};

export type ExistingData = LoadSummary & {
	row_count: number;
};

export type TableCheck = {
	table: string;
	table_name: string;
	sheet: string;
	read: number;
	missing_required: number;
	duplicates: number;
	empty_cells: number;
	empty_cell_details: { column: string; cell_count: number }[];
	to_write: number;
	total: number | null;
	verdict: string;
};

export type UploadGroupRow = {
	group: string;
	subtitle?: string;
	data?: string;
	row_count: number;
	column_count?: number;
	total_column_count?: number;
	quantity?: number | null;
	existing: ExistingData | null;
	write_mode: string;
};

export type UploadGroups = {
	title: string;
	first_column: string;
	rows: UploadGroupRow[];
	total: {
		row_count: number;
		quantity?: number | null;
		existing?: number | null;
	};
};

export type PendingUpload = {
	pending_id: string;
	domain: string;
	year: number;
	file_type: FileType;
	file_name: string;
	size_bytes: number;
	sheet: string | null;
	checks: TableCheck[];
	identical: LoadSummary | null;
	overwrite: (string | number)[];
	new: (string | number)[];
	previous: ExistingData | null;
	by_group: UploadGroups;
};

export type LoadFilter = {
	domain: string;
	year: string;
	file_type: string;
	status: string;
	user: string;
	query: string;
	page: number;
	page_size: number;
};

export type LoadListItem = {
	id: number;
	file_name: string;
	year: number | null;
	file_type: { code: string; name: string };
	user: string;
	created_at: string;
	row_count: number;
	status: LoadStatus;
};

export type LoadList = {
	total: number;
	uploaders: string[];
	items: LoadListItem[];
};

export type StepStatus = 'ok' | 'err' | 'skip';

export type Step = {
	code: string;
	name: string;
	result: string;
	verdict: string;
	status: StepStatus;
};

export type LoadError = {
	sheet: string | null;
	location: string | null;
	issue: string | null;
	resolution: string | null;
};

export type Load = {
	id: number;
	status: LoadStatus;
	domain: string;
	year: number | null;
	file_type: FileType;
	file_name: string;
	size_bytes: number;
	user: string;
	created_at: string;
	months: string | null;
	sheet: string | null;
	total_rows: number;
	rows_written: number;
	sheet_count: number;
	steps: Step[];
	errors: LoadError[];
	can_rollback: boolean;
	is_active: boolean;
	primary_table: string | null;
};

export type TableLink = {
	table: string;
	layer: string;
	year?: number;
	period?: number;
	query?: string;
};

export type SheetLink = {
	sheet: number;
};

export type CardLink = TableLink | SheetLink;

export type CardValue = number | string | null;

export type CardCell = CardValue | { value: CardValue; link?: CardLink };

export type CardRow = {
	cells: CardCell[];
	verdict?: string;
	verdict_note?: string;
	note?: string;
	link?: TableLink;
};

export type CardOption = {
	name: string;
	label: string;
	value: string;
	default: string;
	choices: { value: string; label: string }[];
};

export type ReconcileCard = {
	key: string;
	title: string;
	count?: number;
	message?: string;
	columns: { label: string; align_right?: boolean }[];
	rows: CardRow[];
	totals?: CardCell[];
	options?: CardOption[];
	pagination?: { page: number; page_size: number; total: number };
};

export type ReconcileQuery = Record<string, string | number>;

export type SourceSheet = {
	index: number;
	name: string;
	row_count: number;
	hidden: boolean;
	hidden_row_count: number;
};

export type SourceSheetPage = {
	index: number;
	name: string;
	hidden: boolean;
	columns: string[];
	total: number;
	hidden_row_count: number;
	rows: { row_number: number; cells: (string | null)[]; hidden: boolean }[];
};

export type TableKind = 'fact' | 'dim';

export type TableSummary = {
	table: string;
	name: string;
	description: string;
	kind: TableKind;
	year: number | null;
	months: string | null;
	file_type: FileType;
	load_id: number | null;
	row_count: number;
	updated_at: string | null;
};

export type TableColumn = {
	name: string;
	source_name: string;
	type: string;
	type_label?: string;
	required: boolean;
	meaning: string;
	purpose: string;
	example: string | null;
	is_measure: boolean;
};

export type TableValue = string | number | null;

export type TableData = {
	table: string;
	name: string;
	description: string;
	grain: string;
	domain: string;
	kind: TableKind;
	file_type: FileType;
	layer: string;
	year: number | null;
	latest_month: string | null;
	updated_at: string | null;
	has_period: boolean;
	periods: string[];
	columns: TableColumn[];
	total: number;
	rows: TableValue[][];
	total_row: TableValue[] | null;
};

export type TableFilter = {
	layer: string;
	year: string;
	period: string;
	query: string;
};

export type DbConfig = {
	config: {
		host: string;
		port: number;
		database: string;
		username: string;
		note: string | null;
	} | null;
	connection: {
		ok: boolean;
		description: string;
		reason: string | null;
	} | null;
	last_tested_at: string | null;
	saved_at: string | null;
};

export type DbConfigForm = {
	host: string;
	port: number;
	database: string;
	username: string;
	password: string;
	note: string;
};

export type DbConfigResult = {
	ok: boolean;
	message: string;
};

export type DownloadedFile = {
	blob: Blob;
	fileName: string;
	rowCount: number | null;
};
