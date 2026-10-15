window.BimapDataEngineLineImport = {
	async call(method, args, type = "POST") {
		const response = await frappe.call({ method, args, type });
		return response.message;
	},

	async open(screen, options = {}) {
		const editable = typeof screen?.ensureLineImportEditable === "function"
			? await screen.ensureLineImportEditable()
			: screen?.grid?.ensureEditable?.();
		if (!editable) return null;
		const parentDoctype = options.parentDoctype || screen.documentType;
		const tableField = options.tableField || "items";
		const schema = await this.call(
			"bimap_data_engine.api.metadata.get_schema",
			{ doctype: parentDoctype },
			"GET",
		);
		const table = schema.tables.find((candidate) => candidate.fieldname === tableField);
		if (!table || table.read_only) {
			frappe.throw(__("La tabla de partidas no está disponible para importación."));
		}
		const availableChildFields = new Set(table.fields.map((field) => field.fieldname));

		const dialog = new frappe.ui.Dialog({
			title: __("Importar partidas desde Excel"),
			size: "extra-large",
			fields: [{ fieldname: "content", fieldtype: "HTML" }],
		});
		const root = dialog.fields_dict.content.$wrapper[0];
		root.innerHTML = `
			<div class="bde-line-import">
				<div class="bde-line-toolbar">
					<button class="btn btn-primary btn-sm bde-line-file" type="button">${__("Abrir CSV/XLSX")}</button>
					<label>${__("Hoja")} <select class="form-control bde-line-sheet"></select></label>
					<label>${__("Combinar")}
						<select class="form-control bde-line-policy">
							<option value="append">${__("Agregar filas")}</option>
							<option value="consolidate">${__("Sumar cantidades coincidentes")}</option>
							<option value="update">${__("Actualizar coincidencias")}</option>
							<option value="reject_duplicates">${__("Rechazar duplicados")}</option>
						</select>
					</label>
					<button class="btn btn-primary btn-sm bde-line-apply" type="button" disabled>${__("Preparar y agregar")}</button>
				</div>
				<div class="bde-line-mapping"></div>
				<div class="bde-line-status">${__("Selecciona el archivo que contiene las partidas.")}</div>
				<div class="bde-line-grid"></div>
			</div>
		`;
		const elements = {
			file: root.querySelector(".bde-line-file"),
			sheet: root.querySelector(".bde-line-sheet"),
			policy: root.querySelector(".bde-line-policy"),
			apply: root.querySelector(".bde-line-apply"),
			mapping: root.querySelector(".bde-line-mapping"),
			status: root.querySelector(".bde-line-status"),
			grid: root.querySelector(".bde-line-grid"),
		};
		let workbook = null;
		let adapter = null;
		let suggestions = [];
		const setStatus = (message, state = "") => {
			elements.status.textContent = message;
			elements.status.dataset.state = state;
		};
		const selectedSheet = () => workbook?.sheets.find((sheet) => sheet.name === elements.sheet.value);
		const currentMapping = () => [...elements.mapping.querySelectorAll(".bde-line-map-row")]
			.map((row) => ({
				source: row.dataset.source,
				target: row.querySelector("select").value,
				transform: "trim",
			}))
			.filter((entry) => entry.target);

		const renderMapping = (headers) => {
			elements.mapping.replaceChildren(...headers.map((header) => {
				const row = document.createElement("label");
				row.className = "bde-line-map-row";
				row.dataset.source = header;
				const caption = document.createElement("span");
				caption.textContent = header;
				const select = document.createElement("select");
				select.className = "form-control";
				select.append(Object.assign(document.createElement("option"), {
					value: "", textContent: __("No importar"),
				}));
				for (const field of table.fields.filter((candidate) => !candidate.read_only)) {
					select.append(Object.assign(document.createElement("option"), {
						value: field.fieldname,
						textContent: `${field.label} (${field.fieldname})`,
					}));
				}
				const suggested = suggestions.find((candidate) => candidate.source === header);
				if (suggested) select.value = suggested.target;
				row.append(caption, select);
				return row;
			}));
		};

		const renderSheet = async () => {
			const sheet = selectedSheet();
			if (!sheet) return;
			suggestions = await this.call("bimap_data_engine.api.imports.suggest", {
				doctype: parentDoctype,
				headers: sheet.headers,
				table_field: tableField,
			});
			renderMapping(sheet.headers);
			await frappe.require([
				"bimap_data_engine.bundle.js",
				"/assets/bimap_data_engine/css/data_engine.css",
			]);
			if (!adapter) adapter = window.BimapDataEngineSpreadsheet.create(elements.grid);
			await adapter.mount(
				sheet.rows.map((row, index) => ({ name: `line-${index + 1}`, modified: "", ...row })),
				sheet.headers.map((header) => ({ fieldname: header, label: header })),
				{ mode: "import" },
			);
			elements.apply.disabled = false;
			setStatus(__("{0} filas listas para revisar y mapear.", [sheet.row_count]), "success");
		};

		const loadFile = (fileDoc) => {
			setStatus(__("Leyendo archivo…"));
			return this.call("bimap_data_engine.api.imports.inspect_file", { file_url: fileDoc.file_url })
				.then(async (result) => {
					workbook = result;
					elements.sheet.replaceChildren(...workbook.sheets.map((sheet) => Object.assign(
						document.createElement("option"),
						{ value: sheet.name, textContent: `${sheet.name} (${sheet.row_count})` },
					)));
					await renderSheet();
				});
		};

		elements.file.addEventListener("click", () => {
			new frappe.ui.FileUploader({
				folder: "Home/Attachments",
				allow_toggle_private: true,
				allow_take_photo: false,
				restrictions: { allowed_file_types: [".csv", ".xlsx"] },
				on_success: (fileDoc) => loadFile(fileDoc).catch((error) => setStatus(error.message, "error")),
			});
		});
		elements.sheet.addEventListener("change", () => renderSheet().catch((error) => setStatus(error.message, "error")));
		elements.apply.addEventListener("click", async () => {
			try {
				elements.apply.disabled = true;
				setStatus(__("Validando partidas…"));
				const sheet = selectedSheet();
				sheet.rows = adapter.getRows();
				const mapped = await this.call(
					"bimap_data_engine.api.integration.map_document_lines",
					{
						parent_doctype: parentDoctype,
						table_field: tableField,
						rows: sheet.rows,
						mapping: currentMapping(),
						defaults: options.defaults || {},
					},
				);
				if (!mapped.valid) {
					adapter.showIssues(mapped.errors, { sheetName: sheet.name, onlyIssues: true });
					setStatus(__("Corrige las {0} filas marcadas y vuelve a preparar.", [mapped.errors.length]), "error");
					return;
				}
				const savePayload = await (screen.getLineImportPayload?.()
					|| screen.buildSavePayload?.()
					|| {});
				const existingRows = Array.isArray(savePayload.items) ? savePayload.items : [];
				const parentValues = { ...savePayload };
				delete parentValues.items;
				const prepared = await window.BimapDataEngineIntegration.prepareDocumentLines({
					parentDoctype,
					tableField,
					parentValues,
					existingRows,
					importedRows: mapped.records.map((record) => record.values),
					mergePolicy: elements.policy.value,
					matchFields: options.matchFields || ["item_code", "uom", "warehouse"]
						.filter((field) => availableChildFields.has(field)),
				});
				if (typeof screen.applyPreparedLines === "function") {
					await screen.applyPreparedLines(prepared);
				} else {
					window.BimapDataEngineIntegration.applyPreparedLinesToScreen(screen, prepared);
				}
				dialog.hide();
				(screen.showLineImportNotice || screen.mostrarAviso)?.call(
					screen,
					__("Partidas preparadas: {0} agregadas, {1} actualizadas.", [prepared.merge.added, prepared.merge.updated]),
					"green",
				);
			} catch (error) {
				setStatus(error.message || __("No se pudieron preparar las partidas."), "error");
			} finally {
				elements.apply.disabled = !workbook;
			}
		});
		dialog.$wrapper.on("hidden.bs.modal", () => adapter?.destroy?.());
		dialog.show();
		return dialog;
	},
};
