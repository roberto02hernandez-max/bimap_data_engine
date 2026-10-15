frappe.pages["bimap-data-engine"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("BIMAP Data Engine"),
		single_column: true,
	});
	page.main.html(`
		<div class="bde-shell bde-editor-shell">
			<div class="bdi-step bde-step-select"><span>1</span><strong>${__("Elige qué quieres actualizar")}</strong></div>
			<div class="bde-toolbar bde-choice-toolbar">
				<div class="bde-field"><label>${__("Área o proceso")}</label><select class="form-control bde-area"><option value="">${__("Selecciona un área…")}</option></select></div>
				<div class="bde-field"><label>${__("Catálogo o documento")}</label><select class="form-control bde-document" disabled><option value="">${__("Selecciona qué quieres actualizar…")}</option></select></div>
				<button class="btn btn-primary bde-prepare" disabled>${__("Preparar actualización")}</button>
			</div>
			<div class="bde-editor-help">${__("BIMAP cargará los registros existentes en la hoja. Sólo se guardarán las celdas que cambies.")}</div>
			<div class="bde-status">${__("Elige los campos y carga los registros existentes.")}</div>
			<div class="bde-workspace hidden">
				<div class="bde-field-picker"></div>
				<div class="bde-filter-panel">
					<div class="bde-filter-header">
						<strong>${__("Filtrar registros")}</strong>
						<span class="text-muted bde-filter-hint">${__("Sin filtros adicionales: se cargarán todos los registros permitidos.")}</span>
						<button class="btn btn-default btn-xs bde-add-filter">${__("Agregar filtro")}</button>
						<button class="btn btn-default btn-xs bde-clear-filters">${__("Quitar filtros")}</button>
					</div>
					<div class="bde-fixed-filters hidden"></div>
					<div class="bde-filter-rows"></div>
				</div>
				<div class="bde-action-toolbar">
					<button class="btn btn-primary bde-load">${__("Cargar registros existentes")}</button>
					<button class="btn btn-default bde-export">${__("Exportar XLSX")}</button>
					<button class="btn btn-default bde-preview" disabled>${__("Vista previa")}</button>
					<button class="btn btn-primary bde-apply" disabled>${__("Guardar cambios en ERPNext")}</button>
					<button class="btn btn-danger bde-cancel-job hidden">${__("Cancelar trabajo")}</button>
					<button class="btn btn-default bde-download-job hidden">${__("Descargar resultados")}</button>
				</div>
				<details class="bde-advanced">
					<summary>${__("Filtros y herramientas avanzadas")}</summary>
					<input class="bde-doctype" type="hidden">
					<select class="bde-fields hidden" multiple></select>
					<div class="bde-toolbar bde-query-toolbar">
						<div class="bde-field"><label>${__("Filtros JSON generados")}</label><input class="form-control bde-filters" value='{}' readonly></div>
						<div class="bde-field"><label>${__("Máximo de registros")}</label><input class="form-control bde-limit" type="number" min="1" max="25000" value="25000"></div>
						<button class="btn btn-default bde-schema">${__("Volver a cargar campos")}</button>
					</div>
					<div class="bde-toolbar bde-child-toolbar">
						<div class="bde-field"><label>${__("Tabla hija")}</label><select class="form-control bde-table"><option value="">${__("Seleccionar…")}</option></select></div>
						<div class="bde-field"><label>${__("Documento padre")}</label><input class="form-control bde-parent-name"></div>
						<button class="btn btn-default bde-load-child">${__("Abrir tabla hija")}</button>
					</div>
					<div class="bde-toolbar bde-clear-toolbar">
						<div class="bde-field"><label>${__("Documento a limpiar")}</label><select class="form-control bde-clear-record"><option value="">${__("Seleccionar…")}</option></select></div>
						<div class="bde-field"><label>${__("Campo a limpiar")}</label><select class="form-control bde-clear-field"><option value="">${__("Seleccionar…")}</option></select></div>
						<button class="btn btn-default bde-mark-clear">${__("Marcar limpieza explícita")}</button>
						<button class="btn btn-default bde-reset-clears">${__("Quitar limpiezas")}</button>
					</div>
					<div class="bde-toolbar bde-session-toolbar">
						<div class="bde-field"><label>${__("Sesión guardada")}</label><select class="form-control bde-sessions"><option value="">${__("Seleccionar…")}</option></select></div>
						<button class="btn btn-default bde-refresh-sessions">${__("Actualizar sesiones")}</button>
						<button class="btn btn-default bde-save-session">${__("Guardar sesión")}</button>
						<button class="btn btn-default bde-open-session">${__("Continuar sesión")}</button>
					</div>
					<div class="bde-toolbar bde-job-toolbar">
						<div class="bde-field"><label>${__("Trabajos recientes")}</label><select class="form-control bde-jobs"><option value="">${__("Seleccionar…")}</option></select></div>
						<label class="bde-check"><input type="checkbox" class="bde-retry-failed"> ${__("Reintentar registros fallidos")}</label>
						<button class="btn btn-default bde-refresh-jobs">${__("Actualizar trabajos")}</button>
						<button class="btn btn-default bde-monitor-job">${__("Ver progreso")}</button>
						<button class="btn btn-primary bde-resume-job">${__("Reanudar")}</button>
					</div>
				</details>
				<div class="bde-grid hidden"></div>
			</div>
		</div>
	`);
	const root = page.main.find(".bde-shell")[0];
	const elements = {
		area: root.querySelector(".bde-area"),
		document: root.querySelector(".bde-document"),
		prepare: root.querySelector(".bde-prepare"),
		workspace: root.querySelector(".bde-workspace"),
		fieldPicker: root.querySelector(".bde-field-picker"),
		filterPanel: root.querySelector(".bde-filter-panel"),
		filterHint: root.querySelector(".bde-filter-hint"),
		fixedFilters: root.querySelector(".bde-fixed-filters"),
		filterRows: root.querySelector(".bde-filter-rows"),
		addFilter: root.querySelector(".bde-add-filter"),
		clearFilters: root.querySelector(".bde-clear-filters"),
		doctype: root.querySelector(".bde-doctype"),
		fields: root.querySelector(".bde-fields"),
		filters: root.querySelector(".bde-filters"),
		limit: root.querySelector(".bde-limit"),
		schema: root.querySelector(".bde-schema"),
		load: root.querySelector(".bde-load"),
		export: root.querySelector(".bde-export"),
		table: root.querySelector(".bde-table"),
		parentName: root.querySelector(".bde-parent-name"),
		loadChild: root.querySelector(".bde-load-child"),
		clearRecord: root.querySelector(".bde-clear-record"),
		clearField: root.querySelector(".bde-clear-field"),
		markClear: root.querySelector(".bde-mark-clear"),
		resetClears: root.querySelector(".bde-reset-clears"),
		sessions: root.querySelector(".bde-sessions"),
		refreshSessions: root.querySelector(".bde-refresh-sessions"),
		saveSession: root.querySelector(".bde-save-session"),
		openSession: root.querySelector(".bde-open-session"),
		jobs: root.querySelector(".bde-jobs"),
		retryFailed: root.querySelector(".bde-retry-failed"),
		refreshJobs: root.querySelector(".bde-refresh-jobs"),
		monitorJob: root.querySelector(".bde-monitor-job"),
		resumeJob: root.querySelector(".bde-resume-job"),
		preview: root.querySelector(".bde-preview"),
		apply: root.querySelector(".bde-apply"),
		cancelJob: root.querySelector(".bde-cancel-job"),
		downloadJob: root.querySelector(".bde-download-job"),
		grid: root.querySelector(".bde-grid"),
		status: root.querySelector(".bde-status"),
	};
	let adapter = null;
	let catalog = null;
	let selectedDocument = null;
	let selectedFields = new Set();
	let filterDraft = [];
	let schema = null;
	let pendingChanges = [];
	let explicitClears = [];
	let loadPromise = null;
	let currentJob = null;
	let lastJob = null;
	let invocationContext = null;
	let editorMode = "parent";
	let currentSession = null;
	const filterOptionCache = new Map();
	const contextId = new URLSearchParams(window.location.search).get("context");

	function option(value, label) {
		return Object.assign(document.createElement("option"), { value, textContent: label });
	}

	function escapeHtml(value) {
		return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
			"&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
		}[char]));
	}

	function setStatus(message, state = "") {
		elements.status.textContent = message;
		elements.status.dataset.state = state;
	}

	function call(method, args) {
		const type = method.includes(".api.metadata.") || method.includes(".api.records.")
			|| method.includes(".api.filter_options.")
			|| method.endsWith(".api.jobs.get_job") || method.endsWith(".api.jobs.list_jobs")
			|| method.endsWith(".api.integration.get_editor_context") ? "GET" : "POST";
		const isSessionRead = method.endsWith(".api.imports.get_work_session")
			|| method.endsWith(".api.imports.list_work_sessions");
		return frappe.call({ method, args, type: isSessionRead ? "GET" : type }).then((response) => response.message);
	}

	async function loadAssets() {
		if (!loadPromise) {
			loadPromise = frappe.require([
				"bimap_data_engine.bundle.js",
				"/assets/bimap_data_engine/css/data_engine.css",
			]);
		}
		await loadPromise;
	}

	function resetWorkspace() {
		root.classList.remove("bde-workspace-active");
		if (adapter) adapter.destroy();
		adapter = null;
		schema = null;
		selectedFields = new Set();
		filterDraft = [];
		pendingChanges = [];
		explicitClears = [];
		elements.filterRows.replaceChildren();
		elements.fixedFilters.replaceChildren();
		elements.fixedFilters.classList.add("hidden");
		elements.workspace.classList.add("hidden");
		elements.grid.classList.add("hidden");
	}

	async function loadCatalog() {
		catalog = await call("bimap_data_engine.api.metadata.get_edit_catalog", {});
		elements.area.replaceChildren(
			option("", __("Selecciona un área…")),
			...(catalog.areas || []).map((area) => option(area.id, area.label)),
		);
		if (!contextId) {
			setStatus(__("Selecciona primero un área y después el catálogo o documento que quieres actualizar."));
			return;
		}
		invocationContext = await call("bimap_data_engine.api.integration.get_editor_context", { context_id: contextId });
		if (!new Set(["Edit", "Export"]).has(invocationContext.mode)) frappe.throw(__("El contexto no autoriza esta pantalla."));
		for (const area of catalog.areas || []) {
			const document = area.documents.find((candidate) => candidate.doctype === invocationContext.doctype);
			if (!document) continue;
			elements.area.value = area.id;
			selectArea(false);
			elements.document.value = document.id || document.doctype;
			selectDocument();
			await prepareWorkspace();
			return;
		}
		frappe.throw(__("El documento solicitado no está disponible para actualización."));
	}

	function selectArea(clear = true) {
		if (clear) resetWorkspace();
		const area = catalog?.areas?.find((candidate) => candidate.id === elements.area.value);
		selectedDocument = null;
		elements.document.replaceChildren(
			option("", __("Selecciona qué quieres actualizar…")),
			...(area?.documents || []).map((document) => option(document.id || document.doctype, document.label)),
		);
		elements.document.disabled = !area;
		elements.prepare.disabled = true;
		setStatus(area
			? __("Ahora elige qué catálogo o documento de {0} quieres actualizar.", [area.label])
			: __("Selecciona primero un área y después el catálogo o documento que quieres actualizar."));
	}

	function selectDocument() {
		resetWorkspace();
		const area = catalog?.areas?.find((candidate) => candidate.id === elements.area.value);
		selectedDocument = area?.documents?.find((document) => (document.id || document.doctype) === elements.document.value) || null;
		elements.prepare.disabled = !selectedDocument;
		if (selectedDocument) {
			setStatus(__("Prepara la hoja para consultar y actualizar {0}.", [selectedDocument.label]), "success");
		}
	}

	async function prepareWorkspace() {
		if (!selectedDocument) return;
		elements.doctype.value = selectedDocument.doctype;
		filterDraft = [];
		elements.filters.value = JSON.stringify(fixedFiltersObject());
		elements.filters.readOnly = true;
		selectedFields = new Set(selectedDocument.fields.filter((field) => field.preferred).map((field) => field.fieldname));
		await loadSchema();
		elements.workspace.classList.remove("hidden");
		root.classList.add("bde-workspace-active");
		setStatus(__("Elige las columnas y presiona “Cargar registros existentes”. Se consultarán hasta {0} registros.", [elements.limit.value]), "success");
	}

	function identityFields() {
		const fieldname = {
			Customer: "bimap_customer_number",
			Supplier: "bimap_supplier_number",
			Item: "item_code",
			"Item Price": "item_code",
		}[schema?.doctype];
		return new Set(fieldname ? [fieldname] : []);
	}

	function lockedFields() {
		return new Set([
			...identityFields(),
			...Object.keys(fixedFiltersObject()),
		]);
	}

	function fixedFiltersObject() {
		return {
			...(selectedDocument?.filters || {}),
			...(invocationContext?.filters || {}),
		};
	}

	const NO_VALUE_OPERATORS = new Set(["is_set", "is_not_set"]);
	const NUMERIC_FIELD_TYPES = new Set(["Int", "Float", "Currency", "Percent", "Rating"]);
	const DATE_FIELD_TYPES = new Set(["Date", "Datetime", "Time"]);
	const TREE_LINK_DOCTYPES = new Set(["Item Group", "Customer Group", "Supplier Group", "Territory", "Warehouse"]);
	const SELECTOR_LINK_DOCTYPES = new Set([
		"Brand", "Company", "Currency", "Customer Group", "Item Group",
		"Price List", "Supplier Group", "Territory", "UOM", "Warehouse",
	]);

	function loadFilterOptions(doctype) {
		if (!filterOptionCache.has(doctype)) {
			filterOptionCache.set(doctype, call(
				"bimap_data_engine.api.filter_options.get_filter_options",
				{ link_doctype: doctype },
			).catch((error) => {
				filterOptionCache.delete(doctype);
				throw error;
			}));
		}
		return filterOptionCache.get(doctype);
	}

	function operatorsForField(field) {
		if (field.fieldtype === "Check") {
			return [["=", __("Es")], ["!=", __("No es")]];
		}
		if (field.fieldtype === "Select") {
			return [
				["in", __("Cualquiera de estos valores")],
				["not in", __("Ninguno de estos valores")],
				["is_set", __("Tiene valor")], ["is_not_set", __("Está vacío")],
			];
		}
		if (NUMERIC_FIELD_TYPES.has(field.fieldtype) || DATE_FIELD_TYPES.has(field.fieldtype)) {
			return [
				["=", __("Igual a")], ["!=", __("Distinto de")],
				[">", __("Mayor que")], [">=", __("Mayor o igual")],
				["<", __("Menor que")], ["<=", __("Menor o igual")],
				["between", __("Entre")], ["is_set", __("Tiene valor")],
				["is_not_set", __("Está vacío")],
			];
		}
		if (field.fieldtype === "Link" && SELECTOR_LINK_DOCTYPES.has(field.options)
			&& TREE_LINK_DOCTYPES.has(field.options)) {
			return [
				["in", __("Cualquiera de estas opciones")],
				["not in", __("Ninguna de estas opciones")],
				["descendants of (inclusive)", __("Incluye este grupo y sus subgrupos")],
				["descendants of", __("Sólo sus subgrupos")],
				["not descendants of", __("No está en sus subgrupos")],
				["is_set", __("Tiene valor")], ["is_not_set", __("Está vacío")],
			];
		}
		if (field.fieldtype === "Link" && SELECTOR_LINK_DOCTYPES.has(field.options)) {
			return [
				["in", __("Cualquiera de estas opciones")],
				["not in", __("Ninguna de estas opciones")],
				["is_set", __("Tiene valor")], ["is_not_set", __("Está vacío")],
			];
		}
		if (field.fieldtype === "Link") {
			return [
				["in", __("Cualquiera de estas opciones")],
				["not in", __("Ninguna de estas opciones")],
				["=", __("Exactamente")], ["!=", __("Distinto de")],
				["is_set", __("Tiene valor")], ["is_not_set", __("Está vacío")],
			];
		}
		return [
			["=", __("Igual a")], ["!=", __("Distinto de")],
			["between", __("Entre (incluyente)")],
			["like", __("Contiene")], ["not like", __("No contiene")],
			["in", __("Está en la lista")], ["not in", __("No está en la lista")],
			["is_set", __("Tiene valor")], ["is_not_set", __("Está vacío")],
		];
	}

	function fieldByName(fieldname) {
		return [...(schema?.fields || []), ...(schema?.filter_fields || [])]
			.find((field) => field.fieldname === fieldname) || null;
	}

	function filterableFields() {
		const fixed = new Set(Object.keys(fixedFiltersObject()));
		return [...(schema?.fields || []), ...(schema?.filter_fields || [])]
			.filter((field) => !fixed.has(field.fieldname));
	}

	function filterValueControl(field, operatorName, initialValue) {
		const wrapper = document.createElement("div");
		wrapper.className = "bde-filter-value";
		if (NO_VALUE_OPERATORS.has(operatorName)) return wrapper;
		const makeInput = (value = "") => {
			const enableClickToggle = (select) => {
				if (!select.multiple) return;
				select.title = __("Haz clic en cada opción para marcarla o desmarcarla.");
				select.addEventListener("mousedown", (event) => {
					if (!(event.target instanceof HTMLOptionElement)) return;
					event.preventDefault();
					event.target.selected = !event.target.selected;
					select.focus();
					select.dispatchEvent(new Event("change", { bubbles: true }));
				});
			};
			if (field.fieldtype === "Check") {
				const select = document.createElement("select");
				select.className = "form-control input-xs";
				select.append(option("1", __("Sí")), option("0", __("No")));
				select.value = String(value === true ? 1 : value === false ? 0 : value ?? "1");
				return select;
			}
			if (field.fieldtype === "Select") {
				const select = document.createElement("select");
				const multiple = new Set(["in", "not in"]).has(operatorName);
				select.className = `form-control input-xs${multiple ? " bde-filter-catalog-select" : ""}`;
				select.multiple = multiple;
				const values = String(field.options || "").split("\n").map((entry) => entry.trim()).filter(Boolean);
				const selected = new Set(Array.isArray(value) ? value.map(String) : [String(value || "")]);
				const entries = values.map((entry) => {
					const item = option(entry, __(entry));
					item.selected = selected.has(entry);
					return item;
				});
				select.append(...(multiple ? [] : [option("", __("Seleccionar…"))]), ...entries);
				enableClickToggle(select);
				return select;
			}
			if (field.fieldtype === "Link" && SELECTOR_LINK_DOCTYPES.has(field.options)) {
				const select = document.createElement("select");
				const multiple = new Set(["in", "not in"]).has(operatorName);
				select.className = "form-control input-xs bde-filter-catalog-select";
				select.multiple = multiple;
				enableClickToggle(select);
				select.disabled = true;
				select.append(option("", __("Cargando opciones…")));
				const selected = new Set(
					Array.isArray(value)
						? value.map(String)
						: multiple
							? String(value || "").split(",").map((entry) => entry.trim()).filter(Boolean)
							: [String(value || "")],
				);
				loadFilterOptions(field.options).then((response) => {
					const values = response?.options || [];
					const entries = values.map((entry) => {
						const indentation = response.tree ? "　".repeat(entry.depth || 0) : "";
						const marker = response.tree ? (entry.is_group ? "▸ " : "• ") : "";
						const suffix = entry.label !== entry.value ? ` — ${entry.value}` : "";
						const item = option(entry.value, `${indentation}${marker}${entry.label}${suffix}`);
						item.selected = selected.has(String(entry.value));
						return item;
					});
					select.replaceChildren(
						...(multiple ? [] : [option("", __("Selecciona un valor…"))]),
						...entries,
					);
					select.disabled = false;
				}).catch(() => {
					select.replaceChildren(option("", __("No fue posible cargar las opciones")));
					setStatus(__("No fue posible consultar las opciones del filtro."), "error");
				});
				return select;
			}
			if (field.fieldtype === "Link" && new Set(["in", "not in"]).has(operatorName)) {
				const host = document.createElement("div");
				host.className = "bde-filter-link-control bde-filter-link-multi";
				const control = frappe.ui.form.make_control({
					parent: $(host),
					df: {
						fieldtype: "MultiSelectList",
						label: field.label,
						placeholder: __("Busca y selecciona uno o varios valores…"),
						get_data: (text) => frappe.xcall("frappe.desk.search.search_link", {
							doctype: field.options,
							txt: text || "",
							page_length: 25,
						}).then((rows) => (rows || []).map((entry) => ({
							value: entry.value,
							label: entry.label || entry.value,
							description: entry.description,
						}))),
					},
					render_input: true,
				});
				host._bdeMultiSelectControl = control;
				control.set_value(Array.isArray(value)
					? value
					: String(value || "").split(",").map((entry) => entry.trim()).filter(Boolean));
				return host;
			}
			if (field.fieldtype === "Link" && !new Set(["in", "not in"]).has(operatorName)) {
				const host = document.createElement("div");
				host.className = "bde-filter-link-control";
				const control = frappe.ui.form.make_control({
					parent: $(host),
					df: { fieldtype: "Link", options: field.options, label: field.label, only_select: 1 },
					render_input: true,
				});
				control.set_value(value ?? "");
				return host;
			}
			const input = document.createElement("input");
			input.className = "form-control input-xs";
			input.type = field.fieldtype === "Date" ? "date"
				: field.fieldtype === "Datetime" ? "datetime-local"
					: field.fieldtype === "Time" ? "time"
						: NUMERIC_FIELD_TYPES.has(field.fieldtype) ? "number" : "text";
			if (input.type === "number") input.step = "any";
			input.value = value ?? "";
			input.placeholder = new Set(["in", "not in"]).has(operatorName)
				? __("Separa los valores con comas")
				: field.options && new Set(["Link", "Dynamic Link"]).has(field.fieldtype)
					? `${__("Valor de")} ${field.options}` : __("Valor");
			return input;
		};
		if (operatorName === "between") {
			const values = Array.isArray(initialValue) ? initialValue : ["", ""];
			wrapper.append(makeInput(values[0]), Object.assign(document.createElement("span"), { textContent: __("y") }), makeInput(values[1]));
		} else {
			wrapper.append(makeInput(initialValue));
		}
		return wrapper;
	}

	function updateFilterHint() {
		const additional = elements.filterRows.children.length;
		const fixed = Object.keys(fixedFiltersObject()).length;
		elements.filterHint.textContent = additional
			? __(
				"{0} filtro(s) adicional(es). Todos deben cumplirse.", [additional],
			)
			: fixed
				? __("Puedes agregar más condiciones; todas se combinarán con el filtro bloqueado.")
				: __("Sin filtros: se cargarán todos los registros permitidos.");
	}

	function addFilterRow(initial = {}) {
		if (!schema) return;
		const fields = filterableFields();
		if (!fields.length) return;
		const row = document.createElement("div");
		row.className = "bde-filter-row";
		const fieldSelect = document.createElement("select");
		fieldSelect.className = "form-control input-xs bde-filter-field";
		fieldSelect.append(...fields.map((field) => option(field.fieldname, field.label || field.fieldname)));
		fieldSelect.value = fields.some((field) => field.fieldname === initial.fieldname) ? initial.fieldname : fields[0].fieldname;
		const operatorSelect = document.createElement("select");
		operatorSelect.className = "form-control input-xs bde-filter-operator";
		const valueSlot = document.createElement("div");
		valueSlot.className = "bde-filter-value-slot";
		const remove = document.createElement("button");
		remove.type = "button";
		remove.className = "btn btn-default btn-xs bde-remove-filter";
		remove.textContent = __("Quitar");
		const renderOperator = (preferredOperator, preferredValue) => {
			const field = fieldByName(fieldSelect.value);
			const operators = operatorsForField(field);
			operatorSelect.replaceChildren(...operators.map(([value, label]) => option(value, label)));
			operatorSelect.value = operators.some(([value]) => value === preferredOperator) ? preferredOperator : operators[0][0];
			valueSlot.replaceChildren(filterValueControl(field, operatorSelect.value, preferredValue));
		};
		fieldSelect.addEventListener("change", () => { renderOperator(); invalidateGrid(); });
		operatorSelect.addEventListener("change", () => { renderOperator(operatorSelect.value); invalidateGrid(); });
		valueSlot.addEventListener("change", invalidateGrid);
		valueSlot.addEventListener("input", () => {
			if (adapter) invalidateGrid();
		});
		remove.addEventListener("click", () => {
			row.remove();
			updateFilterHint();
			invalidateGrid();
		});
		row.append(fieldSelect, operatorSelect, valueSlot, remove);
		elements.filterRows.append(row);
		renderOperator(initial.operator, initial.value);
		updateFilterHint();
	}

	function clearUserFilters({ invalidate = true } = {}) {
		elements.filterRows.replaceChildren();
		filterDraft = [];
		updateFilterHint();
		if (invalidate) invalidateGrid();
	}

	function filtersToDraft(filters) {
		const fixed = fixedFiltersObject();
		const displayValue = (operatorName, value) => {
			if (new Set(["in", "not in"]).has(operatorName) && Array.isArray(value)) return [...value];
			if (new Set(["like", "not like"]).has(operatorName) && typeof value === "string"
				&& value.startsWith("%") && value.endsWith("%")) return value.slice(1, -1);
			return value;
		};
		if (!filters) return [];
		if (Array.isArray(filters) && filters.every((entry) => !Array.isArray(entry))) {
			return filters.map((entry) => ({ ...entry, value: displayValue(entry.operator, entry.value) }));
		}
		if (!Array.isArray(filters)) {
			return Object.entries(filters)
				.filter(([fieldname, value]) => fixed[fieldname] !== value)
				.map(([fieldname, value]) => ({ fieldname, operator: "=", value }));
		}
		return filters.map((entry) => {
			const offset = entry.length === 4 ? 1 : 0;
			const fieldname = entry[offset];
			const rawOperator = entry[offset + 1];
			const value = entry[offset + 2];
			if (Object.prototype.hasOwnProperty.call(fixed, fieldname) && rawOperator === "=" && fixed[fieldname] === value) return null;
			const operatorName = rawOperator === "is" && value === "set" ? "is_set"
				: rawOperator === "is" && value === "not set" ? "is_not_set" : rawOperator;
			return { fieldname, operator: operatorName, value: displayValue(operatorName, value) };
		}).filter(Boolean);
	}

	function renderFilterBuilder(filters = filterDraft) {
		const fixed = fixedFiltersObject();
		const chips = Object.entries(fixed).map(([fieldname, value]) => {
			const chip = document.createElement("span");
			chip.className = "bde-fixed-filter";
			chip.textContent = `${fieldByName(fieldname)?.label || fieldname}: ${value}`;
			return chip;
		});
		elements.fixedFilters.replaceChildren(...chips);
		elements.fixedFilters.classList.toggle("hidden", !chips.length);
		elements.filterRows.replaceChildren();
		for (const filter of filtersToDraft(filters)) addFilterRow(filter);
		updateFilterHint();
	}

	function collectFilters() {
		const result = Object.entries(fixedFiltersObject()).map(([fieldname, value]) => [fieldname, "=", value]);
		filterDraft = [];
		for (const row of elements.filterRows.children) {
			const fieldname = row.querySelector(".bde-filter-field").value;
			const operatorName = row.querySelector(".bde-filter-operator").value;
			const controls = [...row.querySelectorAll(".bde-filter-value input, .bde-filter-value select")];
			let value;
			let operator = operatorName;
			if (operatorName === "is_set" || operatorName === "is_not_set") {
				operator = "is";
				value = operatorName === "is_set" ? "set" : "not set";
				filterDraft.push({ fieldname, operator: operatorName, value: null });
			} else if (operatorName === "between") {
				value = controls.map((control) => control.value);
				if (value.some((entry) => entry === "")) frappe.throw(__("Completa ambos valores del filtro “Entre”."));
				filterDraft.push({ fieldname, operator: operatorName, value });
				result.push([fieldname, ">=", value[0]], [fieldname, "<=", value[1]]);
				continue;
			} else {
				if (new Set(["in", "not in"]).has(operatorName)) {
					const control = controls[0];
					const multiControl = row.querySelector(".bde-filter-link-multi")?._bdeMultiSelectControl;
					value = multiControl
						? [...(multiControl.values || [])]
						: control instanceof HTMLSelectElement && control.multiple
							? [...control.selectedOptions].map((entry) => entry.value).filter(Boolean)
							: String(control?.value || "").split(",").map((entry) => entry.trim()).filter(Boolean);
					if (!value.length) frappe.throw(__("Selecciona al menos un valor para el filtro de lista."));
				} else {
					value = controls[0]?.value ?? "";
					if (value === "") frappe.throw(__("Completa el valor de todos los filtros o elimina la condición incompleta."));
				}
				filterDraft.push({ fieldname, operator: operatorName, value });
				if (new Set(["like", "not like"]).has(operatorName)) value = `%${value}%`;
			}
			result.push([fieldname, operator, value]);
		}
		const filters = result.length ? result : {};
		elements.filters.value = JSON.stringify(filters);
		return filters;
	}

	function invalidateGrid() {
		if (adapter) adapter.destroy();
		adapter = null;
		pendingChanges = [];
		explicitClears = [];
		elements.grid.classList.add("hidden");
		elements.preview.disabled = true;
		elements.apply.disabled = true;
		setStatus(__("Cambió la selección de columnas. Presiona “Cargar registros existentes” para actualizar la hoja."));
	}

	function renderFieldPicker() {
		if (!schema) return;
		const fields = schema.fields.filter((field) => !field.read_only || field.fixed_filter);
		const locked = lockedFields();
		for (const fieldname of locked) selectedFields.add(fieldname);
		const title = document.createElement("strong");
		title.textContent = selectedDocument?.label || schema.doctype;
		const hint = document.createElement("span");
		hint.className = "text-muted";
		hint.textContent = __("Activa únicamente las columnas que quieras consultar o modificar.");
		const search = document.createElement("input");
		search.type = "search";
		search.className = "form-control input-xs bde-field-search";
		search.placeholder = __("Buscar campo…");
		const choices = document.createElement("div");
		choices.className = "bde-field-choices";
		for (const field of fields) {
			const choice = document.createElement("label");
			choice.className = `bde-field-choice${locked.has(field.fieldname) ? " is-required" : ""}`;
			const checkbox = document.createElement("input");
			checkbox.type = "checkbox";
			checkbox.checked = selectedFields.has(field.fieldname);
			checkbox.disabled = locked.has(field.fieldname);
			checkbox.addEventListener("change", () => {
				if (checkbox.checked) selectedFields.add(field.fieldname);
				else selectedFields.delete(field.fieldname);
				const hiddenOption = [...elements.fields.options].find((candidate) => candidate.value === field.fieldname);
				if (hiddenOption) hiddenOption.selected = checkbox.checked;
				invalidateGrid();
			});
			const text = document.createElement("span");
			text.textContent = `${field.label || field.fieldname}${locked.has(field.fieldname) ? " *" : ""}`;
			choice.append(checkbox, text);
			choices.append(choice);
		}
		search.addEventListener("input", () => {
			const needle = search.value.trim().toLocaleLowerCase();
			for (const choice of choices.children) {
				choice.classList.toggle("hidden", Boolean(needle) && !choice.textContent.toLocaleLowerCase().includes(needle));
			}
		});
		const changeDocument = document.createElement("button");
		changeDocument.type = "button";
		changeDocument.className = "btn btn-default btn-xs bde-change-document";
		changeDocument.textContent = __("Cambiar catálogo");
		changeDocument.addEventListener("click", () => {
			root.classList.remove("bde-workspace-active");
			root.querySelector(".bde-step-select").scrollIntoView({ behavior: "smooth", block: "start" });
		});
		elements.fieldPicker.replaceChildren(title, hint, search, choices, changeDocument);
	}

	async function loadSchema() {
		if (contextId && !invocationContext) {
			invocationContext = await call("bimap_data_engine.api.integration.get_editor_context", {
				context_id: contextId,
			});
			elements.doctype.value = invocationContext.doctype;
			elements.doctype.readOnly = true;
			elements.filters.value = JSON.stringify(invocationContext.filters || {});
			elements.filters.readOnly = Object.keys(invocationContext.filters || {}).length > 0;
			if (!new Set(["Edit", "Export"]).has(invocationContext.mode)) {
				frappe.throw(__("El contexto no autoriza esta pantalla."));
			}
			if (invocationContext.mode === "Export") {
				root.querySelector(".bde-child-toolbar").classList.add("hidden");
				root.querySelector(".bde-clear-toolbar").classList.add("hidden");
				elements.preview.classList.add("hidden");
				elements.apply.classList.add("hidden");
			}
		}
		const doctype = elements.doctype.value.trim();
		if (!doctype) return;
		setStatus(__("Consultando metadatos…"));
		schema = await call("bimap_data_engine.api.metadata.get_schema", { doctype, context_id: contextId });
		const fixedFields = new Set(Object.keys(fixedFiltersObject()));
		for (const field of schema.fields) {
			if (!fixedFields.has(field.fieldname)) continue;
			field.read_only = true;
			field.fixed_filter = true;
		}
		const selectable = invocationContext?.mode === "Export"
			? schema.fields
			: schema.fields.filter((field) => !field.read_only || field.fixed_filter);
		const configuredLabels = new Map((selectedDocument?.fields || []).map((field) => [field.fieldname, field.label]));
		for (const field of schema.fields) {
			field.label = __(configuredLabels.get(field.fieldname) || field.label || field.fieldname);
		}
		if (!selectedFields.size) {
			for (const field of selectedDocument?.fields || []) {
				if (field.preferred) selectedFields.add(field.fieldname);
			}
		}
		elements.fields.replaceChildren(...selectable.map((field) => {
			const option = document.createElement("option");
			option.value = field.fieldname;
			option.textContent = `${field.label} (${field.fieldname})`;
			option.selected = invocationContext?.mode === "Export" || selectedFields.has(field.fieldname);
			return option;
		}));
		selectedFields = new Set([...elements.fields.selectedOptions].map((candidate) => candidate.value));
		elements.table.replaceChildren(
			Object.assign(document.createElement("option"), { value: "", textContent: __("Seleccionar…") }),
			...schema.tables.filter((table) => !table.read_only).map((table) => {
				const option = document.createElement("option");
				option.value = table.fieldname;
				option.textContent = `${table.label} (${table.fieldname})`;
				return option;
			}),
		);
		renderFieldPicker();
		renderFilterBuilder(filterDraft);
		setStatus(__("Metadatos cargados: {0} campos disponibles.", [selectable.length]), "success");
	}

	function selectedColumns() {
		const names = [...elements.fields.selectedOptions].map((option) => option.value);
		return names.map((name) => schema.fields.find((field) => field.fieldname === name)).filter(Boolean);
	}

	async function loadRows() {
		if (!schema || schema.doctype !== elements.doctype.value.trim()) await loadSchema();
		const columns = selectedColumns();
		if (!columns.length) {
			frappe.msgprint(__("Selecciona al menos un campo editable."));
			return;
		}
		const filters = collectFilters();
		setStatus(__("Consultando registros…"));
		const maximum = Math.min(Math.max(Number.parseInt(elements.limit.value, 10) || 500, 1), 25000);
		const rows = [];
		let nextStart = 0;
		do {
			const result = await call("bimap_data_engine.api.records.list_records", {
				doctype: schema.doctype,
				fields: columns.map((column) => column.fieldname),
				filters,
				start: nextStart,
				page_length: Math.min(500, maximum - rows.length),
				context_id: contextId,
			});
			rows.push(...result.rows);
			nextStart = result.next_start;
			setStatus(__("Consultando registros… {0}/{1}", [rows.length, maximum]));
		} while (nextStart !== null && rows.length < maximum);
		await loadAssets();
		if (!adapter) adapter = window.BimapDataEngineSpreadsheet.create(elements.grid);
		elements.grid.classList.remove("hidden");
		await adapter.mount(rows, columns);
		root.classList.add("bde-workspace-active");
		editorMode = "parent";
		pendingChanges = [];
		explicitClears = [];
		elements.clearRecord.replaceChildren(
			Object.assign(document.createElement("option"), { value: "", textContent: __("Seleccionar…") }),
			...rows.map((row) => Object.assign(document.createElement("option"), { value: row.name, textContent: row.name })),
		);
		elements.clearField.replaceChildren(
			Object.assign(document.createElement("option"), { value: "", textContent: __("Seleccionar…") }),
			...columns.map((column) => Object.assign(document.createElement("option"), {
				value: column.fieldname, textContent: column.label || column.fieldname,
			})),
		);
		elements.preview.disabled = !rows.length || invocationContext?.mode === "Export";
		elements.apply.disabled = true;
		elements.load.textContent = __("Recargar desde ERPNext");
		setStatus(__("{0} registros cargados. Edita la hoja, revisa con “Vista previa” y después usa “Guardar cambios en ERPNext”.", [rows.length]), "success");
	}

	async function loadChildRows() {
		if (!schema || schema.doctype !== elements.doctype.value.trim()) await loadSchema();
		const tableField = elements.table.value;
		const parentName = elements.parentName.value.trim();
		const table = schema.tables.find((entry) => entry.fieldname === tableField);
		if (!table || !parentName) {
			frappe.msgprint(__("Selecciona una tabla hija e indica el documento padre."));
			return;
		}
		const columns = table.fields.filter((field) => !field.read_only);
		if (!columns.length) {
			frappe.msgprint(__("La tabla hija no contiene campos editables."));
			return;
		}
		setStatus(__("Consultando tabla hija…"));
		const result = await call("bimap_data_engine.api.records.list_child_rows", {
			doctype: schema.doctype,
			name: parentName,
			table_field: tableField,
			fields: columns.map((column) => column.fieldname),
			context_id: contextId,
		});
		await loadAssets();
		if (!adapter) adapter = window.BimapDataEngineSpreadsheet.create(elements.grid);
		elements.grid.classList.remove("hidden");
		const rows = result.rows.map((row) => ({ ...row, modified: result.snapshot_modified }));
		await adapter.mount(rows, columns, {
			mode: "child",
			parentContext: {
				doctype: schema.doctype,
				name: parentName,
				tableField,
				snapshotModified: result.snapshot_modified,
			},
		});
		root.classList.add("bde-workspace-active");
		editorMode = "child";
		pendingChanges = [];
		explicitClears = [];
		elements.clearRecord.replaceChildren(Object.assign(document.createElement("option"), { value: "", textContent: __("Sólo disponible para campos del padre") }));
		elements.clearField.replaceChildren(Object.assign(document.createElement("option"), { value: "", textContent: __("Sólo disponible para campos del padre") }));
		elements.preview.disabled = false;
		elements.apply.disabled = true;
		setStatus(__("{0} filas hijas cargadas. Usa filas vacías para agregar y la columna Eliminar para bajas explícitas.", [rows.length]), "success");
	}

	async function reloadCurrentEditor() {
		if (editorMode === "child") return loadChildRows();
		return loadRows();
	}

	async function commitActiveCell() {
		const active = document.activeElement;
		if (active && typeof active.blur === "function") active.blur();
		await sleep(80);
	}

	async function requestLoadRows() {
		await commitActiveCell();
		if (adapter) {
			const candidate = collectCandidate();
			if (candidate.changes.length || explicitClears.length) {
				const confirmed = await new Promise((resolve) => {
					frappe.confirm(
						__("Hay cambios sin aplicar. Volver a cargar descartará lo escrito en la hoja. ¿Continuar?"),
						() => resolve(true),
						() => resolve(false),
					);
				});
				if (!confirmed) return;
			}
		}
		const label = elements.load.textContent;
		elements.load.disabled = true;
		elements.load.textContent = __("Cargando…");
		try {
			await loadRows();
		} finally {
			elements.load.disabled = false;
			elements.load.textContent = adapter ? __("Recargar desde ERPNext") : label;
		}
	}

	function collectCandidate() {
		const candidate = adapter.getChanges(schema.doctype);
		const clearKeys = new Set(explicitClears.map((change) => `${change.name}\u0000${change.fieldname}`));
		candidate.changes = candidate.changes
			.filter((change) => !clearKeys.has(`${change.name}\u0000${change.fieldname}`))
			.concat(explicitClears);
		return candidate;
	}

	function markExplicitClear() {
		if (editorMode !== "parent" || !adapter) return;
		const name = elements.clearRecord.value;
		const fieldname = elements.clearField.value;
		const row = adapter.rows.find((candidate) => candidate.name === name);
		if (!row || !fieldname) {
			frappe.msgprint(__("Selecciona un documento y un campo."));
			return;
		}
		explicitClears = explicitClears.filter((change) => change.name !== name || change.fieldname !== fieldname);
		explicitClears.push({
			operation: "clear",
			doctype: schema.doctype,
			name,
			fieldname,
			original: row[fieldname] ?? null,
			snapshot_modified: String(row.modified ?? ""),
		});
		adapter.setValue(adapter.rows.indexOf(row), fieldname, "");
		setStatus(__("Limpieza explícita marcada para {0}.{1}. Total: {2}.", [name, fieldname, explicitClears.length]), "success");
	}

	function resetExplicitClears() {
		for (const change of explicitClears) {
			const rowIndex = adapter?.rows.findIndex((row) => row.name === change.name) ?? -1;
			if (rowIndex >= 0) adapter.setValue(rowIndex, change.fieldname, change.original);
		}
		explicitClears = [];
		setStatus(__("Se quitaron las instrucciones explícitas de limpieza."), "success");
	}

	async function preview() {
		await commitActiveCell();
		const candidate = collectCandidate();
		pendingChanges = candidate.changes;
		if (!pendingChanges.length) {
			elements.apply.disabled = true;
			const message = candidate.ignoredEmpty.length
				? __("No hay cambios aplicables. Se ignoraron {0} celdas vacías; usa una operación explícita para limpiar.", [candidate.ignoredEmpty.length])
				: __("No se detectaron cambios en la hoja.");
			setStatus(message);
			frappe.msgprint({
				title: __("Sin cambios para revisar"),
				indicator: "blue",
				message: `${escapeHtml(message)}<br><span class="text-muted">${escapeHtml(__("Confirma la edición con Enter o sal de la celda antes de intentar nuevamente."))}</span>`,
			});
			return;
		}
		const documents = [];
		for (let index = 0; index < pendingChanges.length; index += 500) {
			setStatus(__("Validando cambios… {0}/{1}", [Math.min(index + 500, pendingChanges.length), pendingChanges.length]));
			const result = await call("bimap_data_engine.api.changes.preview_changes", {
				changes: pendingChanges.slice(index, index + 500),
				context_id: contextId,
			});
			documents.push(...result.documents);
		}
		const errors = documents.flatMap((document) => document.errors || []);
		const valid = documents.every((document) => document.valid);
		elements.apply.disabled = !valid;
		setStatus(valid
			? __("Vista previa válida: {0} cambios en {1} documentos.", [pendingChanges.length, documents.length])
			: `${__("Vista previa bloqueada:")}\n${errors.join("\n")}`,
		valid ? "success" : "error");
		const rows = pendingChanges.slice(0, 20).map((change) => `<tr>
			<td>${escapeHtml(change.name || change.child_name || "")}</td>
			<td>${escapeHtml(change.fieldname || change.child_fieldname || change.operation)}</td>
			<td>${escapeHtml(change.original ?? "")}</td>
			<td>${escapeHtml(change.value ?? "")}</td>
		</tr>`).join("");
		const more = pendingChanges.length > 20
			? `<p class="text-muted">${escapeHtml(__("Se muestran 20 de {0} cambios.", [pendingChanges.length]))}</p>` : "";
		const errorList = errors.length
			? `<ul>${errors.slice(0, 20).map((error) => `<li>${escapeHtml(error)}</li>`).join("")}</ul>` : "";
		frappe.msgprint({
			title: valid ? __("Vista previa lista") : __("La vista previa encontró errores"),
			indicator: valid ? "green" : "red",
			message: valid
				? `<p><strong>${escapeHtml(__("{0} cambio(s) en {1} documento(s).", [pendingChanges.length, documents.length]))}</strong></p>
					<p>${escapeHtml(__("Todavía no se ha guardado nada. Cierra esta ventana y presiona “Aplicar cambios” para confirmar."))}</p>
					<div class="table-responsive"><table class="table table-bordered table-sm"><thead><tr><th>${__("Documento")}</th><th>${__("Campo")}</th><th>${__("Valor anterior")}</th><th>${__("Valor nuevo")}</th></tr></thead><tbody>${rows}</tbody></table></div>${more}`
				: `<p>${escapeHtml(__("Corrige los siguientes errores antes de aplicar:"))}</p>${errorList}`,
		});
	}

	function sleep(milliseconds) {
		return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
	}

	async function monitorJob(jobName) {
		currentJob = jobName;
		lastJob = jobName;
		elements.cancelJob.classList.remove("hidden");
		const terminal = new Set(["Completed", "Completed with errors", "Cancelled", "Failed"]);
		while (currentJob === jobName) {
			const result = await call("bimap_data_engine.api.jobs.get_job", { job_name: jobName, page_length: 1 });
			const job = result.job;
			setStatus(__("Trabajo {0}: {1}. Procesados {2}/{3}; correctos {4}; fallidos {5}.", [
				job.name, job.status, job.processed_documents, job.total_documents,
				job.succeeded_documents, job.failed_documents,
			]), job.status === "Failed" || job.status === "Completed with errors" ? "error" : "success");
			if (terminal.has(job.status)) break;
			await sleep(2000);
		}
		currentJob = null;
		elements.cancelJob.classList.add("hidden");
		elements.downloadJob.classList.remove("hidden");
		elements.apply.disabled = true;
		await refreshJobs();
	}

	async function refreshJobs() {
		const result = await call("bimap_data_engine.api.jobs.list_jobs", { page_length: 100 });
		const selected = elements.jobs.value || lastJob;
		elements.jobs.replaceChildren(
			Object.assign(document.createElement("option"), { value: "", textContent: __("Seleccionar…") }),
			...result.jobs.map((job) => Object.assign(document.createElement("option"), {
				value: job.name,
				textContent: `${job.name} · ${job.job_type} · ${job.status} · ${job.processed_documents}/${job.total_documents}`,
			})),
		);
		if ([...elements.jobs.options].some((option) => option.value === selected)) elements.jobs.value = selected;
	}

	async function monitorSelectedJob() {
		const jobName = elements.jobs.value;
		if (!jobName) return;
		await monitorJob(jobName);
	}

	async function resumeSelectedJob() {
		const jobName = elements.jobs.value;
		if (!jobName) {
			frappe.msgprint(__("Selecciona un trabajo para reanudar."));
			return;
		}
		const result = await call("bimap_data_engine.api.jobs.resume_job", {
			job_name: jobName,
			retry_failed: elements.retryFailed.checked ? 1 : 0,
		});
		await monitorJob(result.job.name);
	}

	async function apply() {
		if (!pendingChanges.length) return;
		frappe.confirm(
			__("Se guardarán {0} cambios en ERPNext. ¿Continuar?", [pendingChanges.length]),
			async () => {
				if (pendingChanges.length > 500) {
					const result = await call("bimap_data_engine.api.jobs.create_job", {
						changes: pendingChanges,
						batch_size: 50,
						enqueue_now: 1,
						context_id: contextId,
					});
					await monitorJob(result.job.name);
				} else {
					const result = await call("bimap_data_engine.api.changes.apply_changes", {
						changes: pendingChanges,
						context_id: contextId,
					});
					setStatus(__("Cambios aplicados. Operación: {0}", [result.operation_id]), "success");
					elements.apply.disabled = true;
					await reloadCurrentEditor();
				}
			},
		);
	}

	async function cancelCurrentJob() {
		if (!currentJob) return;
		await call("bimap_data_engine.api.jobs.cancel_job", { job_name: currentJob });
		setStatus(__("Cancelación solicitada para {0}.", [currentJob]));
	}

	async function exportRows() {
		if (!schema || schema.doctype !== elements.doctype.value.trim()) await loadSchema();
		const fields = selectedColumns().map((column) => column.fieldname);
		if (!fields.length) {
			frappe.msgprint(__("Selecciona al menos un campo para exportar."));
			return;
		}
		const filters = collectFilters();
		const params = new URLSearchParams({
			doctype: schema.doctype,
			fields: JSON.stringify(fields),
			filters: JSON.stringify(filters),
			max_rows: elements.limit.value || "500",
		});
		if (contextId) params.set("context_id", contextId);
		window.open(`/api/method/bimap_data_engine.api.exports.download_records?${params}`, "_blank");
	}

	async function refreshSessions() {
		const sessions = await call("bimap_data_engine.api.imports.list_work_sessions", { limit: 100 });
		elements.sessions.replaceChildren(
			Object.assign(document.createElement("option"), { value: "", textContent: __("Seleccionar…") }),
			...sessions.map((session) => Object.assign(document.createElement("option"), {
				value: session.name,
				textContent: `${session.session_title} · ${session.target_doctype} · ${session.modified}`,
			})),
		);
	}

	function sessionState() {
		const candidate = adapter ? collectCandidate() : null;
		const filters = collectFilters();
		return {
			context_id: contextId || null,
			doctype: schema?.doctype,
			fields: [...elements.fields.selectedOptions].map((option) => option.value),
			filters,
			limit: Number.parseInt(elements.limit.value, 10) || 500,
			editor_mode: editorMode,
			table_field: elements.table.value || null,
			parent_name: elements.parentName.value.trim() || null,
			pending_changes: candidate?.changes || [],
		};
	}

	async function saveCurrentSession() {
		if (!schema) await loadSchema();
		const values = await new Promise((resolve) => {
			frappe.prompt(
				[{ fieldname: "title", fieldtype: "Data", label: __("Nombre de la sesión"), reqd: 1 }],
				resolve,
				__("Guardar sesión"),
				__("Guardar"),
			);
		});
		const state = sessionState();
		const result = await call("bimap_data_engine.api.imports.save_work_session", {
			session_title: values.title,
			mode: "Edit",
			target_doctype: schema.doctype,
			state,
			session_name: currentSession,
			row_count: adapter?.rows?.length || 0,
		});
		currentSession = result.name;
		await refreshSessions();
		elements.sessions.value = result.name;
		setStatus(__("Sesión guardada: {0}", [result.name]), "success");
	}

	async function restorePendingChanges(changes) {
		let newChildRowIndex = adapter.rows.length;
		for (const change of changes || []) {
			if (editorMode === "parent") {
				const rowIndex = adapter.rows.findIndex((row) => row.name === change.name);
				if (rowIndex >= 0 && change.operation === "set") adapter.setValue(rowIndex, change.fieldname, change.value);
				if (rowIndex >= 0 && change.operation === "clear") {
					explicitClears.push(change);
					adapter.setValue(rowIndex, change.fieldname, "");
				}
				continue;
			}
			if (change.operation === "add_child") {
				const rowIndex = newChildRowIndex;
				Object.entries(change.value || {}).forEach(([fieldname, value]) => adapter.setValue(rowIndex, fieldname, value));
				newChildRowIndex += 1;
			} else {
				const rowIndex = adapter.rows.findIndex((row) => row.name === change.child_name);
				if (rowIndex < 0) continue;
				if (change.operation === "delete_child") adapter.setDelete(rowIndex, true);
				if (change.operation === "update_child") adapter.setValue(rowIndex, change.child_fieldname, change.value);
			}
		}
	}

	async function openSelectedSession() {
		const sessionName = elements.sessions.value;
		if (!sessionName) return;
		const session = await call("bimap_data_engine.api.imports.get_work_session", { session_name: sessionName });
		const state = session.state;
		if ((state.context_id || null) !== (contextId || null)) {
			frappe.throw(__("La sesión pertenece a un contexto de integración diferente."));
		}
		currentSession = session.name;
		const savedFilterTuples = Array.isArray(state.filters) ? state.filters : Object.entries(state.filters || {}).map(
			([fieldname, value]) => [fieldname, "=", value],
		);
		const matchesFixedFilters = (candidate) => Object.entries(candidate.filters || {}).every(([fieldname, value]) => (
			savedFilterTuples.some((entry) => {
				const offset = entry.length === 4 ? 1 : 0;
				return entry[offset] === fieldname && entry[offset + 1] === "=" && entry[offset + 2] === value;
			})
		));
		for (const area of catalog?.areas || []) {
			const document = area.documents.find((candidate) => candidate.doctype === state.doctype && matchesFixedFilters(candidate))
				|| area.documents.find((candidate) => candidate.doctype === state.doctype);
			if (!document) continue;
			elements.area.value = area.id;
			selectArea(false);
			elements.document.value = document.id || document.doctype;
			selectedDocument = document;
			break;
		}
		elements.doctype.value = state.doctype;
		elements.filters.value = JSON.stringify(state.filters || {});
		filterDraft = filtersToDraft(state.filters);
		elements.limit.value = state.limit || 500;
		await loadSchema();
		[...elements.fields.options].forEach((option) => { option.selected = state.fields?.includes(option.value); });
		if (state.editor_mode === "child") {
			elements.table.value = state.table_field || "";
			elements.parentName.value = state.parent_name || "";
			await loadChildRows();
		} else {
			await loadRows();
		}
		await restorePendingChanges(state.pending_changes);
		setStatus(__("Sesión restaurada con {0} cambios pendientes.", [state.pending_changes?.length || 0]), "success");
	}

	window.BimapDataEnginePage = {
		loadSchema,
		loadRows,
		loadChildRows,
		preview,
		getState: () => ({
			doctype: schema?.doctype || null,
			pendingChanges: [...pendingChanges],
			adapterReady: Boolean(adapter),
		}),
		setValue: (rowIndex, fieldname, value) => adapter.setValue(rowIndex, fieldname, value),
		setDelete: (rowIndex, remove = true) => adapter.setDelete(rowIndex, remove),
	};

	elements.area.addEventListener("change", selectArea);
	elements.document.addEventListener("change", selectDocument);
	elements.prepare.addEventListener("click", () => prepareWorkspace().catch((error) => setStatus(error.message, "error")));
	elements.addFilter.addEventListener("click", () => addFilterRow());
	elements.clearFilters.addEventListener("click", () => clearUserFilters());
	elements.schema.addEventListener("click", () => loadSchema().catch((error) => setStatus(error.message, "error")));
	elements.load.addEventListener("click", () => requestLoadRows().catch((error) => setStatus(error.message, "error")));
	elements.export.addEventListener("click", () => exportRows().catch((error) => setStatus(error.message, "error")));
	elements.loadChild.addEventListener("click", () => loadChildRows().catch((error) => setStatus(error.message, "error")));
	elements.markClear.addEventListener("click", markExplicitClear);
	elements.resetClears.addEventListener("click", resetExplicitClears);
	elements.refreshSessions.addEventListener("click", () => refreshSessions().catch((error) => setStatus(error.message, "error")));
	elements.saveSession.addEventListener("click", () => saveCurrentSession().catch((error) => setStatus(error.message, "error")));
	elements.openSession.addEventListener("click", () => openSelectedSession().catch((error) => setStatus(error.message, "error")));
	elements.refreshJobs.addEventListener("click", () => refreshJobs().catch((error) => setStatus(error.message, "error")));
	elements.monitorJob.addEventListener("click", () => monitorSelectedJob().catch((error) => setStatus(error.message, "error")));
	elements.resumeJob.addEventListener("click", () => resumeSelectedJob().catch((error) => setStatus(error.message, "error")));
	elements.preview.addEventListener("click", () => preview().catch((error) => setStatus(error.message, "error")));
	elements.apply.addEventListener("click", () => apply().catch((error) => setStatus(error.message, "error")));
	elements.cancelJob.addEventListener("click", () => cancelCurrentJob().catch((error) => setStatus(error.message, "error")));
	elements.downloadJob.addEventListener("click", () => {
		if (lastJob) window.open(`/api/method/bimap_data_engine.api.exports.download_job_results?job_name=${encodeURIComponent(lastJob)}`, "_blank");
	});

	$(wrapper).on("hide.bimapDataEngine", () => {
		if (adapter) adapter.destroy();
		adapter = null;
		window.BimapDataEnginePage = null;
	});
	Promise.all([loadCatalog(), refreshSessions(), refreshJobs()]).catch((error) => setStatus(error.message, "error"));
};
