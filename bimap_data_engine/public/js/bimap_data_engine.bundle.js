import { UniverSheetsCorePreset } from "@univerjs/preset-sheets-core";
import UniverPresetSheetsCoreEsES from "@univerjs/preset-sheets-core/locales/es-ES";
import { createUniver, LocaleType, mergeLocales } from "@univerjs/presets";

import "@univerjs/preset-sheets-core/lib/index.css";


function sameValue(left, right) {
	return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}


function workbookData(rows, columns, options = {}) {
	const sheetId = "bimap-data";
	const childMode = options.mode === "child";
	const values = [
		["name", "modified", ...(childMode ? ["Eliminar"] : []), ...columns.map((column) => `${column.label || column.fieldname}${column.required ? " *" : ""}`)],
		...rows.map((row) => [row.name, row.modified, ...(childMode ? [false] : []), ...columns.map((column) => row[column.fieldname] ?? null)]),
	];
	const cellData = {};
	values.forEach((row, rowIndex) => {
		cellData[rowIndex] = {};
		row.forEach((value, columnIndex) => {
			cellData[rowIndex][columnIndex] = { v: value };
		});
	});
	return {
		id: `bimap-data-engine-${Date.now()}`,
		name: "BIMAP Data Engine",
		appVersion: "1.0.4",
		locale: LocaleType.ES_ES,
		styles: {},
		sheetOrder: [sheetId],
		sheets: {
			[sheetId]: {
				id: sheetId,
				name: "Datos",
				rowCount: Math.max(values.length + (childMode ? 50 : 20), (options.entryRows || 0) + 1, 100),
				columnCount: Math.max(columns.length + (childMode ? 3 : 2), 10),
				cellData,
			},
		},
	};
}


class SpreadsheetAdapter {
	constructor(container) {
		this.container = container;
		this.univer = null;
		this.univerAPI = null;
		this.workbook = null;
		this.sheet = null;
		this.rows = [];
		this.columns = [];
		this.mode = "parent";
		this.parentContext = null;
		this.entryRows = 50;
		this.changeDisposable = null;
	}

	async mount(rows, columns, options = {}) {
		this.destroy();
		this.rows = rows.map((row) => ({ ...row }));
		this.columns = columns.map((column) => ({ ...column }));
		this.mode = options.mode || "parent";
		this.parentContext = options.parentContext || null;
		this.entryRows = Math.max(Number(options.entryRows) || 0, this.rows.length, 50);
		const runtime = createUniver({
			locale: LocaleType.ES_ES,
			locales: {
				[LocaleType.ES_ES]: mergeLocales(UniverPresetSheetsCoreEsES),
			},
			presets: [
				UniverSheetsCorePreset({
					container: this.container,
					header: true,
					toolbar: true,
					footer: { sheetBar: false, statisticBar: true, menus: true, zoomSlider: true },
				}),
			],
		});
		this.univer = runtime.univer;
		this.univerAPI = runtime.univerAPI;
		this.workbook = this.univerAPI.createWorkbook(workbookData(this.rows, this.columns, options));
		this.sheet = this.workbook.getActiveSheet();
		this.sheet.setFrozenRows(1);
		this.sheet.hideColumns(0, 2);
		const visibleOffset = this.mode === "child" ? 3 : 2;
		for (const [index, column] of this.columns.entries()) {
			const label = String(column.label || column.fieldname || "");
			this.sheet.setColumnWidth(index + visibleOffset, Math.min(240, Math.max(130, label.length * 9 + 36)));
			if (column.read_only) {
				const displayRange = this.sheet.getRange(1, index + visibleOffset, this.entryRows, 1);
				displayRange.setBackgroundColor("#f3f5f7");
				await displayRange.getRangePermission().protect({
					name: `BIMAP read only ${column.fieldname}`,
					allowEdit: false,
				});
			}
		}
		const width = this.columns.length + (this.mode === "child" ? 3 : 2);
		const header = this.sheet.getRange(0, 0, 1, width);
		header.setFontWeight("bold");
		header.setBackgroundColor("#e8eef9");
		await header.getRangePermission().protect({ name: "BIMAP headers", allowEdit: false });
		const identity = this.sheet.getRange(1, 0, Math.max(this.rows.length, 1), 2);
		await identity.getRangePermission().protect({ name: "BIMAP identity", allowEdit: false });
		if (typeof options.onValueChange === "function") {
			this.changeDisposable = this.univerAPI.addEvent(
				this.univerAPI.Event.SheetValueChanged,
				(event) => {
					const sourceRows = new Set();
					for (const range of event.effectedRanges || []) {
						const firstRow = Math.max(range.getRow(), 1);
						const lastRow = Math.min(range.getLastRow(), this.mode === "import" ? this.entryRows : this.rows.length);
						for (let gridRow = firstRow; gridRow <= lastRow; gridRow += 1) {
							sourceRows.add(gridRow + 1);
						}
					}
					if (sourceRows.size) options.onValueChange([...sourceRows]);
				},
			);
		}
	}

	getChanges(doctype) {
		if (this.mode === "child") return this.getChildChanges();
		if (!this.sheet || !this.rows.length) return { changes: [], ignoredEmpty: [] };
		const width = this.columns.length + 2;
		const values = this.sheet.getRange(1, 0, this.rows.length, width).getValues();
		const originalByName = new Map(this.rows.map((row) => [String(row.name), row]));
		const changes = [];
		const ignoredEmpty = [];
		for (const valuesRow of values) {
			const name = String(valuesRow[0] ?? "");
			const snapshot = String(valuesRow[1] ?? "");
			const original = originalByName.get(name);
			if (!original || snapshot !== String(original.modified ?? "")) continue;
			this.columns.forEach((column, index) => {
				const nextValue = valuesRow[index + 2];
				const previousValue = original[column.fieldname] ?? null;
				if (sameValue(nextValue, previousValue)) return;
				if (nextValue === null || nextValue === "") {
					ignoredEmpty.push({ name, fieldname: column.fieldname });
					return;
				}
				changes.push({
					operation: "set",
					doctype,
					name,
					fieldname: column.fieldname,
					original: previousValue,
					value: nextValue,
					snapshot_modified: snapshot,
				});
			});
		}
		return { changes, ignoredEmpty };
	}

	getChildChanges() {
		if (!this.sheet || !this.parentContext) return { changes: [], ignoredEmpty: [] };
		const width = this.columns.length + 3;
		const height = this.mode === "import" ? this.entryRows : Math.max(this.rows.length + 50, 50);
		const values = this.sheet.getRange(1, 0, height, width).getValues();
		const originalByName = new Map(this.rows.map((row) => [String(row.name), row]));
		const changes = [];
		const ignoredEmpty = [];
		for (const valuesRow of values) {
			const name = String(valuesRow[0] ?? "");
			const original = originalByName.get(name);
			const remove = valuesRow[2] === true || String(valuesRow[2] ?? "").toLowerCase() === "true";
			if (original && remove) {
				changes.push({
					operation: "delete_child",
					doctype: this.parentContext.doctype,
					name: this.parentContext.name,
					fieldname: this.parentContext.tableField,
					child_name: name,
					snapshot_modified: this.parentContext.snapshotModified,
					confirmed: true,
				});
				continue;
			}
			if (original) {
				this.columns.forEach((column, index) => {
					const nextValue = valuesRow[index + 3];
					const previousValue = original[column.fieldname] ?? null;
					if (sameValue(nextValue, previousValue)) return;
					if (nextValue === null || nextValue === "") {
						ignoredEmpty.push({ name, fieldname: column.fieldname });
						return;
					}
					changes.push({
						operation: "update_child",
						doctype: this.parentContext.doctype,
						name: this.parentContext.name,
						fieldname: this.parentContext.tableField,
						child_name: name,
						child_fieldname: column.fieldname,
						original: previousValue,
						value: nextValue,
						snapshot_modified: this.parentContext.snapshotModified,
					});
				});
				continue;
			}
			const childValues = {};
			this.columns.forEach((column, index) => {
				const value = valuesRow[index + 3];
				if (value !== null && value !== "") childValues[column.fieldname] = value;
			});
			if (Object.keys(childValues).length) {
				changes.push({
					operation: "add_child",
					doctype: this.parentContext.doctype,
					name: this.parentContext.name,
					fieldname: this.parentContext.tableField,
					value: childValues,
					snapshot_modified: this.parentContext.snapshotModified,
				});
			}
		}
		return { changes, ignoredEmpty };
	}

	getRows(includeEmpty = false) {
		if (!this.sheet) return [];
		const offset = this.mode === "child" ? 3 : 2;
		const height = this.mode === "import" ? this.entryRows : Math.max(this.rows.length + 50, 50);
		const values = this.sheet.getRange(1, 0, height, this.columns.length + offset).getValues();
		const rows = values.map((valuesRow) => {
			const row = {};
			this.columns.forEach((column, index) => {
				row[column.fieldname] = valuesRow[index + offset] ?? null;
			});
			return row;
		});
		return includeEmpty ? rows : rows.filter((row) => Object.values(row).some((value) => value !== null && value !== ""));
	}

	setValue(rowIndex, fieldname, value) {
		const columnIndex = this.columns.findIndex((column) => column.fieldname === fieldname);
		const maximumRow = this.mode === "child"
			? this.rows.length + 49
			: this.mode === "import" ? this.entryRows - 1 : this.rows.length - 1;
		if (!this.sheet || columnIndex < 0 || rowIndex < 0 || rowIndex > maximumRow) {
			throw new Error("Celda BIMAP inexistente");
		}
		const offset = this.mode === "child" ? 3 : 2;
		this.sheet.getRange(rowIndex + 1, columnIndex + offset, 1, 1).setValue(value);
	}

	setDelete(rowIndex, remove = true) {
		if (this.mode !== "child" || !this.sheet || rowIndex < 0 || rowIndex >= this.rows.length) {
			throw new Error("Fila hija BIMAP inexistente");
		}
		this.sheet.getRange(rowIndex + 1, 2, 1, 1).setValue(Boolean(remove));
	}

	showIssues(issues = [], options = {}) {
		if (!this.sheet) return { issueRows: 0, issueCells: 0 };
		const sourceIssues = issues.filter((issue) => !issue.sheet || issue.sheet === options.sheetName);
		const offset = this.mode === "child" ? 3 : 2;
		const rowCount = Math.max(this.mode === "import" ? this.entryRows : this.rows.length, 1);
		this.sheet.showRows(1, rowCount);
		this.sheet.getRange(1, offset, rowCount, Math.max(this.columns.length, 1)).setBackgroundColor("#ffffff");
		const issueRows = new Set();
		let issueCells = 0;
		for (const issue of sourceIssues) {
			const sourceRow = Number(issue.row) - 2;
			if (!Number.isInteger(sourceRow) || sourceRow < 0 || sourceRow >= rowCount) continue;
			issueRows.add(sourceRow);
			const columnIndex = this.columns.findIndex((column) => column.fieldname === issue.source_field);
			if (columnIndex >= 0) {
				this.sheet.getRange(sourceRow + 1, columnIndex + offset, 1, 1).setBackgroundColor("#ffd7d5");
				issueCells += 1;
			} else {
				this.sheet.getRange(sourceRow + 1, offset, 1, Math.max(this.columns.length, 1)).setBackgroundColor("#fff0ef");
			}
		}
		if (options.onlyIssues) {
			for (let rowIndex = 0; rowIndex < rowCount; rowIndex += 1) {
				if (!issueRows.has(rowIndex)) this.sheet.hideRows(rowIndex + 1, 1);
			}
		}
		return { issueRows: issueRows.size, issueCells };
	}

	focusIssue(issue) {
		if (!this.sheet) return false;
		const sourceRow = Number(issue.row) - 2;
		const columnIndex = this.columns.findIndex((column) => column.fieldname === issue.source_field);
		const rowCount = this.mode === "import" ? this.entryRows : this.rows.length;
		if (!Number.isInteger(sourceRow) || sourceRow < 0 || sourceRow >= rowCount) return false;
		const offset = this.mode === "child" ? 3 : 2;
		const targetColumn = columnIndex >= 0 ? columnIndex + offset : offset;
		this.sheet.showRows(sourceRow + 1, 1);
		this.sheet.setActiveRange(this.sheet.getRange(sourceRow + 1, targetColumn, 1, 1));
		return true;
	}

	destroy() {
		if (this.changeDisposable) this.changeDisposable.dispose();
		if (this.workbook && this.univerAPI) {
			this.univerAPI.disposeUnit(this.workbook.getId());
		}
		if (this.univer) this.univer.dispose();
		this.container.replaceChildren();
		this.univer = null;
		this.univerAPI = null;
		this.workbook = null;
		this.sheet = null;
		this.mode = "parent";
		this.parentContext = null;
		this.entryRows = 50;
		this.changeDisposable = null;
	}
}


window.BimapDataEngineSpreadsheet = {
	create(container) {
		return new SpreadsheetAdapter(container);
	},
	workbookData,
};
