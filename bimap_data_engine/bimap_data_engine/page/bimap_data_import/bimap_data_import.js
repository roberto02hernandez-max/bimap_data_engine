frappe.pages["bimap-data-import"].on_page_load = function (wrapper) {
	const BACKGROUND_PREVIEW_THRESHOLD = 250;
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("BIMAP Data Import"),
		single_column: true,
	});
	page.main.html(`
		<div class="bde-shell bde-import-shell">
			<div class="bdi-step bdi-step-select"><span>1</span><strong>${__("Elige qué quieres importar")}</strong></div>
			<div class="bde-toolbar bdi-choice-toolbar">
				<div class="bde-field"><label>${__("Área o proceso")}</label><select class="form-control bdi-area"><option value="">${__("Selecciona un área…")}</option></select></div>
				<div class="bde-field"><label>${__("Documento")}</label><select class="form-control bdi-doctype" disabled><option value="">${__("Selecciona un documento…")}</option></select></div>
				<button class="btn btn-primary bdi-template" disabled>${__("Crear plantilla aquí")}</button>
				<button class="btn btn-default bdi-file" disabled>${__("Abrir un Excel existente")}</button>
				<button class="btn btn-default bdi-alphaerp">${__("Migrar desde AlphaERP")}</button>
			</div>
			<div class="bdi-template-help">${__("BIMAP preparará los encabezados necesarios. Podrás escribir, pegar desde Excel o abrir un archivo existente.")}</div>
			<div class="bdi-capture-controls hidden">
				<div class="bdi-step bdi-step-capture"><span>2</span><strong>${__("Captura o pega tus datos")}</strong></div>
				<div class="bde-toolbar">
					<div class="bde-field"><label>${__("Hoja de captura")}</label><select class="form-control bdi-sheet"></select></div>
					<div class="bde-field"><label>${__("Identificador de cada documento")}</label><select class="form-control bdi-key"></select></div>
					<button class="btn btn-default bdi-suggest">${__("Relacionar columnas automáticamente")}</button>
					<button class="btn btn-default bdi-save-profile">${__("Guardar configuración")}</button>
				</div>
				<div class="bdi-field-picker hidden"></div>
				<div class="bdi-sheet-tabs hidden"></div>
				<div class="bdi-sheet-explanation hidden"></div>
				<div class="bdi-column-help hidden"></div>
			</div>
			<div class="bdi-import-controls hidden">
				<div class="bdi-step bdi-step-import"><span>3</span><strong>${__("Valida y crea los documentos")}</strong></div>
			<div class="bde-toolbar">
				<div class="bde-field bdi-defaults-field"><label>${__("Valores predeterminados JSON")}</label><input class="form-control bdi-defaults" value="{}"></div>
				<div class="bde-field"><label>${__("Estado destino")}</label><select class="form-control bdi-lifecycle"><option value="draft">${__("Borrador")}</option><option value="submit">${__("Enviar con ERPNext")}</option></select></div>
				<button class="btn btn-default bdi-preview" disabled>${__("Vista previa")}</button>
				<button class="btn btn-primary bdi-start" disabled>${__("Iniciar importación")}</button>
				<button class="btn btn-default bdi-cfdi-preview hidden">${__("Preparar CFDI")}</button>
				<button class="btn btn-primary bdi-cfdi-create hidden" disabled>${__("Crear borrador")}</button>
				<button class="btn btn-default bdi-results hidden">${__("Descargar resultados")}</button>
			</div>
			</div>
			<details class="bdi-advanced hidden"><summary>${__("Configuración técnica avanzada")}</summary><textarea class="form-control bdi-spec" rows="8" placeholder='{"nodes": [...]}'></textarea></details>
			<div class="bde-mapping"></div>
			<div class="bdi-validation hidden">
				<div class="bdi-validation-toolbar">
					<button class="btn btn-danger btn-xs bdi-only-errors"></button>
					<button class="btn btn-default btn-xs bdi-show-all"></button>
					<span class="text-muted bdi-validation-hint">${__("Selecciona un problema para ir a su celda.")}</span>
				</div>
				<div class="bdi-issues"></div>
			</div>
			<div class="bde-grid hidden"></div>
			<div class="bde-status">${__("Selecciona primero un área y el documento que quieres importar.")}</div>
		</div>
	`);
	const root = page.main.find(".bde-import-shell")[0];
	const elements = Object.fromEntries([
		["area", ".bdi-area"], ["doctype", ".bdi-doctype"], ["template", ".bdi-template"], ["file", ".bdi-file"],
		["alphaerp", ".bdi-alphaerp"],
		["sheet", ".bdi-sheet"], ["key", ".bdi-key"], ["defaults", ".bdi-defaults"],
		["defaultsField", ".bdi-defaults-field"],
		["lifecycle", ".bdi-lifecycle"],
		["suggest", ".bdi-suggest"], ["saveProfile", ".bdi-save-profile"],
		["preview", ".bdi-preview"], ["start", ".bdi-start"], ["spec", ".bdi-spec"],
		["cfdiPreview", ".bdi-cfdi-preview"], ["cfdiCreate", ".bdi-cfdi-create"],
		["results", ".bdi-results"],
		["captureControls", ".bdi-capture-controls"], ["importControls", ".bdi-import-controls"],
		["advanced", ".bdi-advanced"],
		["sheetTabs", ".bdi-sheet-tabs"], ["sheetExplanation", ".bdi-sheet-explanation"],
		["fieldPicker", ".bdi-field-picker"],
		["columnHelp", ".bdi-column-help"],
		["validation", ".bdi-validation"], ["onlyErrors", ".bdi-only-errors"],
		["showAll", ".bdi-show-all"], ["issues", ".bdi-issues"],
		["mapping", ".bde-mapping"], ["grid", ".bde-grid"], ["status", ".bde-status"],
	].map(([name, selector]) => [name, root.querySelector(selector)]));
	elements.alphaerp.addEventListener("click", () => frappe.set_route("bimap-alphaerp-migration"));
	let schema = null;
	let catalog = null;
	let selectedDocument = null;
	let activeTemplate = null;
	let workbook = null;
	let sourceFile = null;
	let adapter = null;
	let currentPlan = null;
	let lastJob = null;
	let assetPromise = null;
	let invocationContext = null;
	let currentIssues = [];
	let cfdiMode = false;
	let currentCfdiPreview = null;
	let mountedSheetName = null;
	let revalidationTimer = null;
	let lookupTimer = null;
	let lookupSequence = 0;
	let applyingLookupValues = false;
	let previewSequence = 0;
	const pendingRows = new Set();
	const pendingLookupRows = new Set();
	const contextId = new URLSearchParams(window.location.search).get("context");

	function setStatus(message, state = "") {
		elements.status.textContent = message;
		elements.status.dataset.state = state;
	}

	function call(method, args, type = "POST") {
		return frappe.call({ method, args, type }).then((response) => response.message);
	}

	function option(value, label) {
		return Object.assign(document.createElement("option"), { value, textContent: label });
	}

	function resetWorkspace() {
		root.classList.remove("bdi-workspace-active");
		if (adapter) adapter.destroy();
		adapter = null;
		mountedSheetName = null;
		workbook = null;
		sourceFile = null;
		activeTemplate = null;
		currentPlan = null;
		currentIssues = [];
		schema = null;
		elements.captureControls.classList.add("hidden");
		elements.importControls.classList.add("hidden");
		elements.advanced.classList.add("hidden");
		elements.validation.classList.add("hidden");
		elements.mapping.classList.add("hidden");
		elements.grid.classList.add("hidden");
		elements.fieldPicker.classList.add("hidden");
		elements.defaultsField.classList.remove("hidden");
	}

	async function loadCatalog() {
		catalog = await call("bimap_data_engine.api.metadata.get_import_catalog", {}, "GET");
		elements.area.replaceChildren(
			option("", __("Selecciona un área…")),
			...(catalog.areas || []).map((area) => option(area.id, area.label)),
		);
		setStatus(__("Selecciona primero un área y después el documento que quieres importar."));
	}

	function selectArea() {
		resetWorkspace();
		const area = catalog?.areas?.find((candidate) => candidate.id === elements.area.value);
		selectedDocument = null;
		elements.doctype.replaceChildren(
			option("", __("Selecciona un documento…")),
			...(area?.documents || []).map((document) => option(document.doctype, document.label)),
		);
		elements.doctype.disabled = !area;
		elements.template.disabled = true;
		elements.file.disabled = true;
		setStatus(area
			? __("Ahora elige qué documento de {0} quieres importar.", [area.label])
			: __("Selecciona primero un área y después el documento que quieres importar."));
	}

	async function selectDocument() {
		resetWorkspace();
		const area = catalog?.areas?.find((candidate) => candidate.id === elements.area.value);
		selectedDocument = area?.documents?.find((document) => document.doctype === elements.doctype.value) || null;
		elements.template.disabled = !selectedDocument;
		elements.file.disabled = !selectedDocument;
		if (!selectedDocument) return;
		await loadSchema();
		setStatus(__("Puedes crear la plantilla aquí o abrir un Excel existente para {0}.", [selectedDocument.label]), "success");
	}

	async function loadAssets() {
		if (!assetPromise) {
			assetPromise = frappe.require(["bimap_data_engine.bundle.js", "/assets/bimap_data_engine/css/data_engine.css"]);
		}
		await assetPromise;
	}

	async function loadSchema() {
		if (contextId && !invocationContext) {
			invocationContext = await call("bimap_data_engine.api.integration.get_editor_context", { context_id: contextId }, "GET");
			if (invocationContext.mode !== "Import") frappe.throw(__("El contexto no autoriza importaciones."));
			elements.doctype.value = invocationContext.doctype;
			elements.doctype.readOnly = true;
		}
		const doctype = elements.doctype.value.trim();
		if (!doctype) return;
		schema = await call("bimap_data_engine.api.metadata.get_schema", { doctype, context_id: contextId }, "GET");
		setStatus(__("Metadatos cargados para {0}.", [doctype]), "success");
		if (workbook) await renderSheet();
	}

	function templateSheet(name, fields, includeKey = true) {
		const headers = [
			...(includeKey ? ["Folio externo"] : []),
			...fields.map((field) => field.capture_label || field.label),
		];
		return {
			name,
			display_name: name === "Captura" ? __("Captura completa") : name,
			headers,
			rows: [],
			row_count: 0,
		};
	}

	function addLookupDisplayFields(fields) {
		return fields.flatMap((field) => field.lookup ? [
			field,
			{
				fieldname: `__bimap_name_${field.fieldname}`,
				label: field.lookup.display_label,
				capture_label: field.lookup.display_label,
				display_only: true,
				read_only: true,
				lookup_for: field.fieldname,
			},
		] : [field]);
	}

	async function createTemplate() {
		if (!selectedDocument) return;
		const childLabels = new Set((selectedDocument.child?.fields || []).map((field) => field.label));
		const parentLabels = new Set(selectedDocument.fields.map((field) => field.label));
		const parentFields = selectedDocument.fields.map((field) => ({
			...field,
			capture_label: childLabels.has(field.label) ? `${__(field.label)} (${__("cabecera")})` : __(field.label),
		}));
		const childFields = (selectedDocument.child?.fields || []).map((field) => ({
			...field,
			capture_label: parentLabels.has(field.label) ? `${__(field.label)} (${__("partida")})` : __(field.label),
		}));
		const allFields = [...parentFields, ...childFields];
		activeTemplate = {
			...selectedDocument,
			fields: parentFields,
			child: selectedDocument.child ? { ...selectedDocument.child, fields: childFields } : null,
			all_capture_fields: allFields,
			selected_fields: new Set(allFields.filter((field) => field.required).map((field) => field.capture_label || field.label)),
		};
		activeTemplate.capture_fields = addLookupDisplayFields(allFields.filter((field) => (
			activeTemplate.selected_fields.has(field.capture_label || field.label)
		)));
		const sheets = [templateSheet("Captura", activeTemplate.capture_fields)];
		workbook = { format: "BIMAP", source: { generated: true }, sheets };
		sourceFile = null;
		elements.suggest.classList.add("hidden");
		elements.saveProfile.classList.add("hidden");
		elements.mapping.classList.add("hidden");
		elements.defaultsField.classList.add("hidden");
		elements.sheet.replaceChildren(...sheets.map((sheet) => option(sheet.name, sheet.display_name || sheet.name)));
		elements.sheet.value = "Captura";
		elements.captureControls.classList.remove("hidden");
		elements.importControls.classList.remove("hidden");
		elements.advanced.classList.add("hidden");
		await renderSheet();
		root.classList.add("bdi-workspace-active");
		setStatus(selectedDocument.child
			? __("Plantilla lista. Captura una fila por producto y repite los datos generales del mismo documento.")
			: __("Plantilla lista. Escribe directamente o pega filas copiadas desde Excel."), "success");
	}

	function renderFieldPicker() {
		if (!activeTemplate) {
			elements.fieldPicker.classList.add("hidden");
			return;
		}
		const fields = activeTemplate.all_capture_fields || [];
		const title = document.createElement("strong");
		title.textContent = activeTemplate.label;
		const hint = document.createElement("span");
		hint.className = "text-muted";
		hint.textContent = __("Obligatorias bloqueadas; activa sólo las opcionales que necesites.");
		const search = document.createElement("input");
		search.type = "search";
		search.className = "form-control input-xs bdi-field-search";
		search.placeholder = __("Buscar campo…");
		const changeDocument = document.createElement("button");
		changeDocument.type = "button";
		changeDocument.className = "btn btn-default btn-xs bdi-change-document";
		changeDocument.textContent = __("Cambiar documento");
		changeDocument.addEventListener("click", () => {
			root.classList.remove("bdi-workspace-active");
			root.scrollIntoView({ behavior: "smooth", block: "start" });
		});
		const choices = document.createElement("div");
		choices.className = "bdi-field-choices";
		const folioChoice = document.createElement("label");
		folioChoice.className = "bdi-field-choice is-required";
		folioChoice.innerHTML = '<input type="checkbox" checked disabled><span>Folio externo *</span>';
		choices.append(folioChoice);
		for (const field of fields) {
			const key = field.capture_label || field.label;
			const choice = document.createElement("label");
			choice.className = `bdi-field-choice${field.required ? " is-required" : ""}`;
			const checkbox = document.createElement("input");
			checkbox.type = "checkbox";
			checkbox.checked = activeTemplate.selected_fields.has(key);
			checkbox.disabled = Boolean(field.required);
			checkbox.addEventListener("change", async () => {
				if (checkbox.checked) activeTemplate.selected_fields.add(key);
				else activeTemplate.selected_fields.delete(key);
				activeTemplate.capture_fields = addLookupDisplayFields(fields.filter((candidate) => (
					activeTemplate.selected_fields.has(candidate.capture_label || candidate.label)
				)));
				const sheet = selectedSheet();
				if (sheet) {
					persistMountedSheet();
					sheet.headers = ["Folio externo", ...activeTemplate.capture_fields.map((candidate) => candidate.capture_label || candidate.label)];
					sheet.rows = sheet.rows.map((row) => Object.fromEntries(sheet.headers.map((header) => [header, row[header] ?? null])));
					await renderSheet();
				}
			});
			const text = document.createElement("span");
			text.textContent = `${key}${field.required ? " *" : ""}`;
			choice.append(checkbox, text);
			choices.append(choice);
		}
		search.addEventListener("input", () => {
			const needle = search.value.trim().toLocaleLowerCase();
			for (const choice of choices.children) {
				choice.classList.toggle("hidden", Boolean(needle) && !choice.textContent.toLocaleLowerCase().includes(needle));
			}
		});
		elements.fieldPicker.replaceChildren(title, hint, search, choices, changeDocument);
		elements.fieldPicker.classList.remove("hidden");
	}

	function selectedSheet() {
		return workbook?.sheets.find((sheet) => sheet.name === elements.sheet.value);
	}

	function persistMountedSheet() {
		if (!adapter || !mountedSheetName || !workbook) return;
		const mounted = workbook.sheets.find((sheet) => sheet.name === mountedSheetName);
		if (!mounted) return;
		mounted.rows = adapter.getRows();
		mounted.row_count = mounted.rows.length;
	}

	function templateFieldsForSheet(sheetName) {
		if (!activeTemplate) return null;
		return sheetName === "Captura" ? activeTemplate.capture_fields : activeTemplate.fields;
	}

	const COLUMN_HELP = {
		"Folio externo": __("Una clave tuya para identificar el documento, por ejemplo COT-001. Se repite en sus partidas."),
		"Clave de cliente": __("Clave BIMAP única del cliente. El nombre aparecerá automáticamente a la derecha."),
		"Nombre del cliente": __("Nombre confirmado por BIMAP a partir de la clave; es sólo informativo."),
		"Clave de proveedor": __("Clave BIMAP única del proveedor. El nombre aparecerá automáticamente a la derecha."),
		"Nombre del proveedor": __("Nombre confirmado por BIMAP a partir de la clave; es sólo informativo."),
		"Fecha": __("Fecha del documento, normalmente en formato AAAA-MM-DD."),
		"Fecha de entrega": __("Fecha comprometida de entrega en formato AAAA-MM-DD."),
		"Fecha requerida": __("Fecha en que se requieren los productos."),
		"Válida hasta": __("Último día de vigencia de la cotización."),
		"Moneda": __("Código de moneda, por ejemplo MXN o USD."),
		"Clave de producto": __("Código del producto en ERPNext, por ejemplo P20-001."),
		"Nombre del producto": __("Nombre confirmado por BIMAP a partir de la clave; es sólo informativo."),
		"Cantidad": __("Número de unidades solicitadas."),
		"Unidad": __("Unidad de medida del producto, por ejemplo PZA, Kg o Nos."),
		"Precio unitario": __("Precio de una unidad. Puede dejarse vacío para que ERPNext busque el precio configurado."),
		"Almacén": __("Almacén que utilizará esta partida cuando el documento afecte inventario."),
	};

	function renderCaptureGuide(sheet) {
		if (!activeTemplate) {
			elements.sheetTabs.classList.add("hidden");
			elements.sheetExplanation.classList.add("hidden");
			elements.columnHelp.classList.add("hidden");
			return;
		}
		elements.sheetTabs.classList.add("hidden");
		elements.sheetExplanation.textContent = activeTemplate.child
			? __("Todo se captura aquí: una fila por producto. Repite Folio externo, cliente, fecha y moneda en cada partida del mismo documento.")
			: __("Escribe una fila por registro que quieras crear.");
		elements.sheetExplanation.classList.remove("hidden");
		elements.columnHelp.classList.add("hidden");
		renderFieldPicker();
	}

	function renderMapping(headers) {
		const templateFields = templateFieldsForSheet(elements.sheet.value);
		const childTable = elements.sheet.value === "Partidas"
			? schema.tables.find((table) => table.fieldname === activeTemplate?.child?.table_field)
			: null;
		const editable = childTable
			? childTable.fields.filter((field) => !field.read_only)
			: schema.fields.filter((field) => !field.read_only);
		elements.mapping.replaceChildren(...headers.map((header) => {
			const row = document.createElement("div");
			row.className = "bde-map-row";
			const label = document.createElement("span");
			label.textContent = header;
			const select = document.createElement("select");
			select.className = "form-control bdi-map-target";
			select.dataset.source = header;
			select.append(Object.assign(document.createElement("option"), { value: "", textContent: __("No importar") }));
			for (const field of editable) {
				select.append(Object.assign(document.createElement("option"), {
					value: field.fieldname,
					textContent: `${field.label} (${field.fieldname})`,
				}));
			}
			const intended = templateFields?.find((field) => (field.capture_label || field.label) === header);
			if (intended) select.value = intended.fieldname;
			const transform = document.createElement("select");
			transform.className = "form-control bdi-map-transform";
			transform.innerHTML = '<option value="none">-</option><option value="trim">trim</option><option value="upper">UPPER</option><option value="lower">lower</option>';
			row.append(label, select, transform);
			return row;
		}));
	}

	async function renderSheet() {
		if (!schema) await loadSchema();
		persistMountedSheet();
		const sheet = selectedSheet();
		if (!sheet) return;
		renderCaptureGuide(sheet);
		elements.key.replaceChildren(...sheet.headers.map((header) => Object.assign(document.createElement("option"), {
			value: header, textContent: header,
		})));
		if (sheet.headers.includes("Folio externo")) elements.key.value = "Folio externo";
		renderMapping(sheet.headers);
		await loadAssets();
		elements.grid.classList.remove("hidden");
		if (!adapter) adapter = window.BimapDataEngineSpreadsheet.create(elements.grid);
		const rows = sheet.rows.map((row, index) => ({ name: `source-${index + 1}`, modified: "", ...row }));
		const currentTemplateFields = templateFieldsForSheet(sheet.name) || [];
		const columns = sheet.headers.map((header) => ({
			fieldname: header,
			label: header,
			required: header === "Folio externo" || Boolean(currentTemplateFields.find((field) => (field.capture_label || field.label) === header)?.required),
			read_only: Boolean(currentTemplateFields.find((field) => (field.capture_label || field.label) === header)?.read_only),
		}));
		await adapter.mount(rows, columns, {
			mode: "import",
			entryRows: activeTemplate ? 1000 : Math.max(rows.length, 50),
			onValueChange: (rows) => handleValueChange(rows),
		});
		mountedSheetName = sheet.name;
		elements.preview.disabled = false;
		elements.start.disabled = true;
		currentPlan = null;
		currentIssues = [];
		pendingRows.clear();
		elements.validation.classList.add("hidden");
		setStatus(activeTemplate
			? __("Hoja {0} lista: los encabezados con * son obligatorios; ERPNext completará sus valores configurados.", [sheet.name])
			: __("{0}: {1} filas cargadas para mapear.", [sheet.name, sheet.row_count]), "success");
	}

	async function loadFileUrl(fileUrl) {
		sourceFile = fileUrl;
		activeTemplate = null;
		elements.suggest.classList.remove("hidden");
		elements.saveProfile.classList.remove("hidden");
		elements.mapping.classList.remove("hidden");
		elements.defaultsField.classList.remove("hidden");
		setStatus(__("Analizando archivo…"));
		const isCfdi = String(sourceFile || "").toLowerCase().split("?")[0].endsWith(".xml");
		workbook = await call(
			isCfdi
				? "bimap_data_engine.api.cfdi.inspect_cfdi"
				: "bimap_data_engine.api.imports.inspect_file",
			{ file_url: sourceFile },
		);
		elements.sheet.replaceChildren(...workbook.sheets.map((sheet) => Object.assign(document.createElement("option"), {
			value: sheet.name, textContent: `${sheet.name} (${sheet.row_count})`,
		})));
		elements.captureControls.classList.remove("hidden");
		elements.importControls.classList.remove("hidden");
		elements.advanced.classList.remove("hidden");
		if (workbook.source?.document_type) {
			cfdiMode = true;
			elements.lifecycle.value = "draft";
			elements.lifecycle.disabled = true;
			currentCfdiPreview = null;
			elements.cfdiPreview.classList.remove("hidden");
			elements.cfdiCreate.classList.remove("hidden");
			elements.cfdiCreate.disabled = true;
			for (const control of [elements.suggest, elements.saveProfile, elements.preview, elements.start]) {
				control.classList.add("hidden");
			}
			elements.captureControls.classList.remove("hidden");
			elements.importControls.classList.remove("hidden");
			elements.doctype.value = workbook.source.document_type === "payment"
				? "Payment Entry"
				: "Purchase Invoice";
			await loadSchema();
			const conceptSheet = workbook.sheets.find((sheet) => sheet.name === "Conceptos" && sheet.row_count)
				|| workbook.sheets[0];
			if (conceptSheet) elements.sheet.value = conceptSheet.name;
			await renderSheet();
			elements.preview.disabled = true;
			elements.start.disabled = true;
			const warnings = workbook.source.warnings || [];
			setStatus(warnings.length
				? __("CFDI cargado con advertencias: {0}", [warnings.join(" · ")])
				: __("CFDI {0} cargado y normalizado.", [workbook.source.uuid || ""]),
			warnings.length ? "error" : "success");
			return;
		}
		cfdiMode = false;
		elements.lifecycle.disabled = false;
		currentCfdiPreview = null;
		elements.cfdiPreview.classList.add("hidden");
		elements.cfdiCreate.classList.add("hidden");
		for (const control of [elements.suggest, elements.saveProfile, elements.preview, elements.start]) {
			control.classList.remove("hidden");
		}
		await renderSheet();
	}

	async function previewCfdi() {
		if (!cfdiMode || !sourceFile) return;
		setStatus(__("ERPNext está preparando el documento CFDI…"));
		currentCfdiPreview = await call("bimap_data_engine.api.cfdi.preview_document", {
			file_url: sourceFile,
			options: JSON.parse(elements.defaults.value || "{}"),
		});
		currentPlan = {
			valid: currentCfdiPreview.valid,
			records: currentCfdiPreview.document ? [currentCfdiPreview.document] : [],
			errors: currentCfdiPreview.issues || [],
		};
		currentIssues = currentPlan.errors;
		renderIssues(true);
		elements.cfdiCreate.disabled = !currentCfdiPreview.valid;
		const document = currentCfdiPreview.document;
		const successMessage = currentCfdiPreview.document_type === "payment"
			? __("CFDI listo: {0} pagos conciliados contra {1} facturas. Se crearán como borrador.", [
				currentCfdiPreview.documents?.length || 0,
				(currentCfdiPreview.documents || []).reduce((total, entry) => total + (entry.references?.length || 0), 0),
			])
			: __("CFDI listo: ERPNext calculó {0} en {1} partidas. Se creará como borrador.", [
				document?.grand_total || 0, document?.items?.length || 0,
			]);
		setStatus(currentCfdiPreview.valid
			? successMessage
			: __("El CFDI tiene {0} incidencias; corrígelas en configuración o catálogos.", [currentIssues.length]),
		currentCfdiPreview.valid ? "success" : "error");
	}

	async function createCfdiDraft() {
		if (!currentCfdiPreview?.valid) return;
		frappe.confirm(__("Se creará un borrador nativo de {0}. No se contabilizará ni enviará hasta que lo confirmes en ERPNext. ¿Continuar?", [schema.doctype]), async () => {
			try {
				elements.cfdiCreate.disabled = true;
				const result = await call("bimap_data_engine.api.cfdi.create_draft", {
					file_url: sourceFile,
					options: JSON.parse(elements.defaults.value || "{}"),
				});
				frappe.set_route("Form", result.doctype, result.name);
			} catch (error) {
				setStatus(error.message, "error");
				elements.cfdiCreate.disabled = false;
			}
		});
	}

	function openFile() {
		new frappe.ui.FileUploader({
			folder: "Home/Attachments",
			allow_toggle_private: true,
			allow_take_photo: false,
			restrictions: { allowed_file_types: [".csv", ".xlsx", ".xml"] },
			on_success: async (fileDoc) => {
				await loadFileUrl(fileDoc.file_url);
			},
		});
	}

	function currentMapping() {
		return [...elements.mapping.querySelectorAll(".bde-map-row")].map((row) => {
			const target = row.querySelector(".bdi-map-target");
			return {
				source: target.dataset.source,
				target: target.value,
				transform: row.querySelector(".bdi-map-transform").value,
			};
		}).filter((entry) => entry.target);
	}

	function templateMapping(fields) {
		return (fields || []).filter((field) => (
			!field.display_only
			&& (!activeTemplate?.selected_fields || activeTemplate.selected_fields.has(field.capture_label || field.label))
		)).map((field) => ({
			source: field.capture_label || field.label,
			target: field.fieldname,
			transform: "none",
		}));
	}

	function normalizedTemplateWorkbook(sourceWorkbook = workbook, lookupIssues = []) {
		if (!activeTemplate?.child) return { workbook: sourceWorkbook, rowMap: null, consistencyIssues: lookupIssues };
		const capture = sourceWorkbook.sheets.find((sheet) => sheet.name === "Captura");
		const groups = new Map();
		const parentRows = [];
		const childRows = [];
		const parentRowMap = [];
		const childRowMap = [];
		const consistencyIssues = [...lookupIssues];
		for (const [index, row] of (capture?.rows || []).entries()) {
			const sourceRow = index + 2;
			const folio = String(row["Folio externo"] ?? "").trim();
			const groupKey = folio || `__fila_${sourceRow}`;
			if (!groups.has(groupKey)) {
				const parent = { "Folio externo": folio };
				for (const field of activeTemplate.fields) {
					const source = field.capture_label || field.label;
					parent[source] = row[source];
				}
				groups.set(groupKey, { parent, sourceRow });
				parentRows.push(parent);
				parentRowMap.push(sourceRow);
			} else {
				const first = groups.get(groupKey);
				for (const field of activeTemplate.fields) {
					const source = field.capture_label || field.label;
					const original = first.parent[source];
					const repeated = row[source];
					if ((original === null || original === "") && repeated !== null && repeated !== "") {
						first.parent[source] = repeated;
						continue;
					}
					if (repeated !== null && repeated !== "" && original !== null && original !== ""
						&& String(repeated) !== String(original)) {
						consistencyIssues.push({
							node: "documents", sheet: "Captura", row: sourceRow,
							source_field: source, target_field: field.fieldname,
							severity: "error", code: "inconsistent_header",
							message: __(`El valor de ${source} no coincide con la primera fila del folio ${folio}.`),
							error: __(`El valor de ${source} no coincide con la primera fila del folio ${folio}.`),
						});
					}
				}
			}
			const child = { "Folio externo": folio };
			for (const field of activeTemplate.child.fields) {
				const source = field.capture_label || field.label;
				child[source] = row[source];
			}
			childRows.push(child);
			childRowMap.push(sourceRow);
		}
		return {
			workbook: {
				format: "BIMAP",
				source: { generated: true, normalized_from: "Captura" },
				sheets: [
					{ name: "Documentos", headers: capture?.headers || [], rows: parentRows, row_count: parentRows.length },
					{ name: "Partidas", headers: capture?.headers || [], rows: childRows, row_count: childRows.length },
				],
			},
			rowMap: { Documentos: parentRowMap, Partidas: childRowMap },
			consistencyIssues,
		};
	}

	function remapTemplatePlan(plan, normalization) {
		if (!normalization.rowMap) {
			const errors = [...(plan.errors || []), ...(normalization.consistencyIssues || [])];
			return { ...plan, valid: errors.length === 0, errors };
		}
		const errors = (plan.errors || []).map((issue) => {
			const sourceRow = normalization.rowMap[issue.sheet]?.[Number(issue.row) - 2];
			return sourceRow ? { ...issue, sheet: "Captura", row: sourceRow } : issue;
		});
		errors.push(...normalization.consistencyIssues);
		return { ...plan, valid: errors.length === 0, errors };
	}

	async function suggest() {
		const sheet = selectedSheet();
		if (!sheet) return;
		const suggestions = await call("bimap_data_engine.api.imports.suggest", {
			doctype: schema.doctype, headers: sheet.headers,
		});
		for (const suggestion of suggestions) {
			const select = [...elements.mapping.querySelectorAll(".bdi-map-target")]
				.find((candidate) => candidate.dataset.source === suggestion.source);
			if (select) select.value = suggestion.target;
		}
		setStatus(__("Se aplicaron {0} sugerencias; revisa el mapeo antes del preview.", [suggestions.length]), "success");
	}

	function specification() {
		persistMountedSheet();
		if (elements.spec.value.trim()) return JSON.parse(elements.spec.value);
		if (activeTemplate) {
			const defaults = JSON.parse(elements.defaults.value || "{}");
			if (activeTemplate.doctype === "Quotation" && defaults.quotation_to === undefined) {
				defaults.quotation_to = "Customer";
			}
			const node = {
				id: "documents",
				doctype: activeTemplate.doctype,
				sheet: activeTemplate.child ? "Documentos" : "Captura",
				external_key: "Folio externo",
				mapping: templateMapping(activeTemplate.fields),
				defaults,
				submit: elements.lifecycle.value === "submit",
			};
			if (activeTemplate.child) {
				node.children = [{
					table_field: activeTemplate.child.table_field,
					sheet: "Partidas",
					parent_key: "Folio externo",
					mapping: templateMapping(activeTemplate.child.fields),
				}];
			}
			return { nodes: [node] };
		}
		return {
			nodes: [{
				id: "records",
				doctype: schema.doctype,
				sheet: elements.sheet.value,
				external_key: elements.key.value,
				mapping: currentMapping(),
				defaults: JSON.parse(elements.defaults.value || "{}"),
				submit: elements.lifecycle.value === "submit",
			}],
		};
	}

	function scheduleRevalidation(rows = []) {
		if (!currentPlan) return;
		rows.forEach((row) => pendingRows.add(row));
		window.clearTimeout(revalidationTimer);
		revalidationTimer = window.setTimeout(() => {
			previewImport(true).catch((error) => setStatus(error.message, "error"));
		}, 700);
	}

	function lookupSpecs() {
		if (activeTemplate) {
			return [...activeTemplate.fields, ...(activeTemplate.child?.fields || [])]
				.filter((field) => field.lookup && activeTemplate.selected_fields.has(field.capture_label || field.label))
				.map((field) => ({
					kind: field.lookup.kind,
					source: field.capture_label || field.label,
					display_source: field.lookup.display_label,
				}));
		}
		const kindByTarget = {
			customer: "customer", party_name: "customer",
			supplier: "supplier", item_code: "item",
		};
		const selfKind = { Customer: "customer", Supplier: "supplier", Item: "item" }[schema?.doctype];
		return currentMapping().filter((entry) => (
			kindByTarget[entry.target] && kindByTarget[entry.target] !== selfKind
		)).map((entry) => ({
			kind: kindByTarget[entry.target],
			source: entry.source,
			display_source: `__bimap_name_${entry.target}`,
		}));
	}

	async function resolveTemplateRows(rows) {
		const lookups = lookupSpecs();
		if (!lookups.length || !rows.length) return { rows, display_rows: [], issues: [] };
		return call("bimap_data_engine.api.lookups.resolve_import_keys", {
			target_doctype: activeTemplate?.doctype || schema.doctype,
			rows,
			lookups,
		});
	}

	function handleValueChange(rows = []) {
		if (applyingLookupValues) return;
		scheduleRevalidation(rows);
		if (!activeTemplate || !lookupSpecs().length) return;
		rows.forEach((row) => pendingLookupRows.add(row));
		window.clearTimeout(lookupTimer);
		lookupTimer = window.setTimeout(async () => {
			const sequence = ++lookupSequence;
			const gridRows = adapter?.getRows(true) || [];
			const requested = [...pendingLookupRows].sort((left, right) => left - right);
			pendingLookupRows.clear();
			const indexes = requested.map((row) => row - 2).filter((index) => index >= 0 && index < gridRows.length);
			if (!indexes.length) return;
			try {
				const result = await resolveTemplateRows(indexes.map((index) => gridRows[index]));
				if (sequence !== lookupSequence || !adapter) return;
				applyingLookupValues = true;
				indexes.forEach((gridIndex, resultIndex) => {
					for (const [fieldname, value] of Object.entries(result.display_rows[resultIndex] || {})) {
						adapter.setValue(gridIndex, fieldname, value);
					}
				});
				window.setTimeout(() => { applyingLookupValues = false; }, 0);
			} catch (error) {
				setStatus(error.message, "error");
			}
		}, 350);
	}

	function mergePartialPlan(previous, partial) {
		if (!partial.scope?.partial) return partial;
		const addresses = new Set(partial.scope.rows.map((entry) => `${entry.node}:${entry.row}`));
		const records = previous.records.filter((record) => (
			!addresses.has(`${record.node_id}:${record.source_row}`)
		));
		const errors = previous.errors.filter((issue) => !addresses.has(`${issue.node}:${issue.row}`));
		records.push(...partial.records);
		errors.push(...partial.errors);
		return {
			...previous,
			valid: errors.length === 0,
			records,
			errors,
			scope: { partial: false, rows: [] },
		};
	}

	function previewUnitCount(currentSpecification, sourceWorkbook = workbook) {
		return currentSpecification.nodes.reduce((total, node) => {
			const sourceSheet = sourceWorkbook.sheets.find((candidate) => candidate.name === node.sheet);
			return total + (sourceSheet?.row_count || sourceSheet?.rows?.length || 0);
		}, 0);
	}

	function technicalPreviewIssue(record, currentSpecification) {
		let address = {};
		try { address = JSON.parse(record.changes_json || "{}"); } catch (_error) { /* no-op */ }
		const node = currentSpecification.nodes.find((candidate) => candidate.id === record.node_id);
		const lines = String(record.error || __("Error técnico durante el preview.")).trim().split("\n");
		return {
			node: record.node_id,
			sheet: node?.sheet,
			row: address.row || 2,
			severity: "error",
			code: "preview_worker_error",
			message: lines[lines.length - 1],
			error: lines[lines.length - 1],
		};
	}

	async function backgroundPreview(currentSpecification, sourceWorkbook = workbook) {
		const started = await call("bimap_data_engine.api.imports.start_preview", {
			workbook: sourceWorkbook,
			specification: currentSpecification,
			batch_size: 50,
			enqueue_now: 1,
			context_id: contextId,
		});
		const jobName = started.job.name;
		const terminal = new Set(["Completed", "Completed with errors", "Cancelled", "Failed"]);
		let job;
		do {
			const snapshot = await call(
				"bimap_data_engine.api.jobs.get_job",
				{ job_name: jobName, page_length: 1 },
				"GET",
			);
			job = snapshot.job;
			setStatus(__("Preparando preview {0}: {1}/{2} unidades.", [
				job.name, job.processed_documents, job.total_documents,
			]));
			if (!terminal.has(job.status)) await new Promise((resolve) => window.setTimeout(resolve, 1200));
		} while (!terminal.has(job.status));
		if (["Cancelled", "Failed"].includes(job.status)) {
			throw new Error(job.last_error || __("El preview masivo no pudo terminar."));
		}
		const records = [];
		for (let start = 0; ; start += 500) {
			const pageResult = await call(
				"bimap_data_engine.api.jobs.get_job",
				{ job_name: jobName, start, page_length: 500 },
				"GET",
			);
			records.push(...pageResult.records);
			if (pageResult.records.length < 500) break;
		}
		const plan = { valid: true, records: [], errors: [], nodes: [], scope: { partial: false, rows: [] } };
		for (const record of records) {
			if (record.status === "Failed" || !record.result_json) {
				plan.errors.push(technicalPreviewIssue(record, currentSpecification));
				continue;
			}
			const partial = JSON.parse(record.result_json);
			plan.records.push(...(partial.records || []));
			plan.errors.push(...(partial.errors || []));
		}
		plan.valid = plan.errors.length === 0;
		return plan;
	}

	async function previewImport(automatic = false) {
		const sheet = selectedSheet();
		if (!sheet || !adapter) return;
		const sequence = ++previewSequence;
		sheet.rows = adapter.getRows();
		if (automatic) setStatus(__("Revalidando cambios…"));
		const currentSpecification = specification();
		let resolvedWorkbook = workbook;
		let lookupIssues = [];
		if (lookupSpecs().length) {
			const resolution = await resolveTemplateRows(sheet.rows);
			resolvedWorkbook = {
				...workbook,
				sheets: workbook.sheets.map((candidate) => candidate.name === sheet.name
					? { ...candidate, rows: resolution.rows, row_count: resolution.rows.length }
					: candidate),
			};
			lookupIssues = resolution.issues || [];
		}
		const normalization = normalizedTemplateWorkbook(resolvedWorkbook, lookupIssues);
		const requestWorkbook = normalization.workbook;
		const rowsToValidate = automatic ? [...pendingRows] : [];
		if (automatic && !rowsToValidate.length) return;
		if (automatic) rowsToValidate.forEach((row) => pendingRows.delete(row));
		const allowIncremental = automatic && !activeTemplate?.child;
		const validRowsToValidate = rowsToValidate.filter((row) => row >= 2 && row <= sheet.rows.length + 1);
		const selectedNodes = currentSpecification.nodes
			.filter((node) => node.sheet === sheet.name)
			.flatMap((node) => validRowsToValidate.map((row) => ({ node: node.id, row })));
		if (allowIncremental && !selectedNodes.length) return;
		let nextPlan;
		try {
			const incremental = allowIncremental && selectedNodes.length;
			const background = !automatic && previewUnitCount(currentSpecification, requestWorkbook) >= BACKGROUND_PREVIEW_THRESHOLD;
			const args = { workbook: requestWorkbook, specification: currentSpecification, context_id: contextId };
			if (incremental) args.selection = selectedNodes;
			nextPlan = background ? await backgroundPreview(currentSpecification, requestWorkbook) : await call(
				incremental
					? "bimap_data_engine.api.imports.revalidate_import_rows"
					: "bimap_data_engine.api.imports.preview_import",
				args,
			);
		} catch (error) {
			if (automatic) rowsToValidate.forEach((row) => pendingRows.add(row));
			throw error;
		}
		if (sequence !== previewSequence) return;
		nextPlan = remapTemplatePlan(nextPlan, normalization);
		currentPlan = allowIncremental ? mergePartialPlan(currentPlan, nextPlan) : nextPlan;
		currentIssues = currentPlan.errors || [];
		renderIssues(true);
		elements.start.disabled = !currentPlan.records.length
			|| currentPlan.errors.some((issue) => issue.code === "inconsistent_header");
		setStatus(currentPlan.valid
			? __("Preview válido: {0} documentos nuevos.", [currentPlan.records.length])
			: __("Preview: {0} documentos válidos y {1} errores. La ejecución parcial requerirá confirmación.", [currentPlan.records.length, currentPlan.errors.length]),
		currentPlan.valid ? "success" : "error");
	}

	function renderIssues(onlyErrors = true) {
		if (!adapter || !workbook) return;
		const sheetName = elements.sheet.value;
		const visibleIssues = currentIssues.filter((issue) => cfdiMode || issue.sheet === sheetName);
		elements.validation.classList.toggle("hidden", !currentPlan);
		elements.onlyErrors.textContent = __("Solo errores ({0})", [visibleIssues.length]);
		elements.showAll.textContent = __("Todos ({0})", [selectedSheet()?.row_count || 0]);
		elements.onlyErrors.classList.toggle("btn-danger", onlyErrors);
		elements.onlyErrors.classList.toggle("btn-default", !onlyErrors);
		elements.showAll.classList.toggle("btn-primary", !onlyErrors);
		elements.showAll.classList.toggle("btn-default", onlyErrors);
		adapter.showIssues(visibleIssues, { sheetName, onlyIssues: onlyErrors });
		elements.issues.replaceChildren(...visibleIssues.map((issue, index) => {
			const button = document.createElement("button");
			button.type = "button";
			button.className = "bdi-issue";
			button.textContent = `${__("Fila")} ${issue.row}${issue.source_field ? ` · ${issue.source_field}` : ""}: ${issue.message || issue.error}`;
			button.title = issue.message || issue.error;
			button.addEventListener("click", () => adapter.focusIssue(visibleIssues[index]));
			return button;
		}));
		if (!visibleIssues.length && currentPlan) {
			const empty = document.createElement("div");
			empty.className = "bdi-no-issues";
			empty.textContent = __("Todo está listo. No hay errores en esta hoja.");
			elements.issues.append(empty);
		}
	}

	async function monitor(jobName) {
		lastJob = jobName;
		const terminal = new Set(["Completed", "Completed with errors", "Cancelled", "Failed"]);
		while (true) {
			const result = await call("bimap_data_engine.api.jobs.get_job", { job_name: jobName, page_length: 1 }, "GET");
			const job = result.job;
			setStatus(__("Trabajo {0}: {1}; {2}/{3}; fallidos {4}.", [job.name, job.status, job.processed_documents, job.total_documents, job.failed_documents]), job.failed_documents ? "error" : "success");
			if (terminal.has(job.status)) break;
			await new Promise((resolve) => window.setTimeout(resolve, 2000));
		}
		elements.results.classList.remove("hidden");
	}

	async function startImport() {
		if (!currentPlan) return;
		if (currentPlan.errors?.some((issue) => issue.code === "inconsistent_header")) {
			frappe.throw(__("Corrige primero los datos generales que no coinciden dentro del mismo folio."));
		}
		const validOnly = !currentPlan.valid;
		frappe.confirm(
			elements.lifecycle.value === "submit"
				? __("Se enviarán {0} documentos mediante ERPNext. Esto puede generar inventario, CxC/CxP y pólizas contables. ¿Continuar?", [currentPlan.records.length])
				: validOnly
				? __("Se ejecutarán sólo {0} registros válidos. ¿Continuar?", [currentPlan.records.length])
				: __("Se crearán {0} documentos. ¿Continuar?", [currentPlan.records.length]),
			async () => {
				const result = await call("bimap_data_engine.api.imports.start_import", {
					plan: currentPlan, batch_size: 50, valid_only: validOnly ? 1 : 0, enqueue_now: 1,
					context_id: contextId,
				});
				await monitor(result.job.name);
			},
		);
	}

	async function saveProfile() {
		const values = await new Promise((resolve) => frappe.prompt(
			[{ fieldname: "title", fieldtype: "Data", label: __("Nombre del perfil"), reqd: 1 }],
			resolve, __("Guardar perfil"), __("Guardar"),
		));
		const result = await call("bimap_data_engine.api.imports.save_profile", {
			profile_title: values.title,
			target_doctype: schema.doctype,
			mapping: currentMapping(),
			defaults: JSON.parse(elements.defaults.value || "{}"),
			source_format: workbook?.format || "Any",
		});
		setStatus(__("Perfil guardado: {0}", [result.name]), "success");
	}

	elements.area.addEventListener("change", selectArea);
	elements.doctype.addEventListener("change", () => selectDocument().catch((error) => setStatus(error.message, "error")));
	elements.template.addEventListener("click", () => createTemplate().catch((error) => setStatus(error.message, "error")));
	elements.file.addEventListener("click", openFile);
	elements.sheet.addEventListener("change", () => renderSheet().catch((error) => setStatus(error.message, "error")));
	elements.suggest.addEventListener("click", () => suggest().catch((error) => setStatus(error.message, "error")));
	elements.preview.addEventListener("click", () => previewImport().catch((error) => setStatus(error.message, "error")));
	elements.start.addEventListener("click", () => startImport().catch((error) => setStatus(error.message, "error")));
	elements.cfdiPreview.addEventListener("click", () => previewCfdi().catch((error) => setStatus(error.message, "error")));
	elements.cfdiCreate.addEventListener("click", () => createCfdiDraft().catch((error) => setStatus(error.message, "error")));
	elements.saveProfile.addEventListener("click", () => saveProfile().catch((error) => setStatus(error.message, "error")));
	elements.results.addEventListener("click", () => {
		if (lastJob) window.open(`/api/method/bimap_data_engine.api.exports.download_job_results?job_name=${encodeURIComponent(lastJob)}`, "_blank");
	});
	elements.onlyErrors.addEventListener("click", () => renderIssues(true));
	elements.showAll.addEventListener("click", () => renderIssues(false));
	window.BimapDataImportPage = {
		loadFileUrl,
		loadSchema,
		suggest,
		previewImport,
		previewCfdi,
		createTemplate,
		setCell: (rowIndex, column, value) => adapter?.setValue(rowIndex, column, value),
		getRows: () => adapter?.getRows() || [],
		getState: () => ({
			schema: schema?.doctype, sourceFile, plan: currentPlan,
			adapterReady: Boolean(adapter), area: elements.area.value,
			template: activeTemplate?.doctype || null,
			columns: adapter?.columns?.map((column) => column.fieldname) || [],
		}),
	};

	$(wrapper).on("hide.bimapDataImport", () => {
		window.clearTimeout(revalidationTimer);
		window.clearTimeout(lookupTimer);
		persistMountedSheet();
		if (adapter) adapter.destroy();
		window.BimapDataImportPage = null;
	});
	loadCatalog().catch((error) => setStatus(error.message, "error"));
};
