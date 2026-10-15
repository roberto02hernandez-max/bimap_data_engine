frappe.pages["bimap-alphaerp-migration"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Migración AlphaERP"), single_column: true });
	page.main.html(`
		<style>
			.alphaerp-migration{max-width:1600px;margin:auto}.alpha-hero{background:linear-gradient(135deg,#f4f8ff,#fff);border:1px solid #dce7f7;border-radius:14px;padding:18px}.alpha-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.alpha-step{border:1px solid #d8dce3;border-radius:10px;padding:12px;background:#fff;text-align:left}.alpha-step.active{border-color:#2490ef;box-shadow:0 0 0 2px #2490ef22}.alpha-step-number{display:inline-grid;place-items:center;width:25px;height:25px;border-radius:50%;background:#edf1f5;margin-right:6px}.alpha-kpi{border:1px solid #e1e5ea;border-radius:12px;padding:14px;background:#fff;height:100%}.alpha-kpi strong{font-size:23px;display:block}.alpha-section{border:1px solid #e1e5ea;border-radius:12px;background:#fff;margin-top:14px;overflow:hidden}.alpha-section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 16px;background:#f8f9fb;border-bottom:1px solid #e1e5ea}.alpha-badge{border-radius:99px;padding:3px 9px;font-size:12px;background:#edf1f5}.alpha-badge.pending{background:#fff3cd;color:#7a5800}.alpha-badge.ready{background:#dff5e5;color:#176b31}.alpha-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:10px 16px;border-bottom:1px solid #eee}.alpha-toolbar .form-control{width:auto;min-width:170px}.alpha-bulk-box{display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#f4f8ff;border:1px solid #d9e8fb;border-radius:8px;padding:7px 9px}.alpha-selected-count{font-weight:600;min-width:105px}.alpha-map-table td{vertical-align:middle}.alpha-map-row.selected{box-shadow:inset 4px 0 #2490ef;background:#f4f8ff}.alpha-origin{min-width:260px}.alpha-impact{min-width:160px}.alpha-examples{font-size:12px;color:#6c7680;margin-top:4px}.alpha-map-row.resolved,.alpha-issue-row.resolved{background:#f7fff8}.alpha-map-row.pending,.alpha-issue-row.pending{background:#fffdf7}.alpha-empty{padding:28px;text-align:center;color:#6c7680}.alpha-panel{display:none}.alpha-panel.active{display:block}.alpha-progress{height:8px;background:#e8edf2;border-radius:10px;overflow:hidden}.alpha-progress>span{display:block;height:100%;background:#28a745}.alpha-preview-json{white-space:pre-wrap;max-width:560px;font-size:11px}.alpha-sticky-actions{position:sticky;bottom:10px;z-index:5;display:flex;justify-content:flex-end;gap:8px;padding:10px;background:#ffffffee;border:1px solid #e1e5ea;border-radius:10px;box-shadow:0 4px 18px #0001}.alpha-issue-message{max-width:520px}@media(max-width:900px){.alpha-steps{grid-template-columns:1fr 1fr}.alpha-section-head{align-items:flex-start;flex-direction:column}}
		</style>
		<div class="container-fluid py-4 alphaerp-migration">
			<div class="alpha-hero">
				<div class="d-flex justify-content-between align-items-start flex-wrap gap-3">
					<div><h3 class="mb-1">${__("Asistente de migración AlphaERP")}</h3><div class="text-muted">${__("Resuelve equivalencias y revisa problemas antes de modificar ERPNext.")}</div></div>
					<div><button class="btn btn-primary alpha-analyze">${__("Analizar base AlphaERP")}</button> <span class="text-muted alpha-status">${__("Listo para analizar.")}</span></div>
				</div>
				<div class="alpha-steps mt-3">
					<button class="alpha-step active" data-panel="summary"><span class="alpha-step-number">1</span><strong>${__("Analizar")}</strong><div class="small text-muted">${__("Qué encontró el conector")}</div></button>
					<button class="alpha-step" data-panel="resolve"><span class="alpha-step-number">2</span><strong>${__("Resolver")}</strong><div class="small text-muted">${__("Equivalencias pendientes")}</div></button>
					<button class="alpha-step" data-panel="issues"><span class="alpha-step-number">3</span><strong>${__("Incidencias")}</strong><div class="small text-muted">${__("Huérfanos y conflictos")}</div></button>
					<button class="alpha-step" data-panel="review"><span class="alpha-step-number">4</span><strong>${__("Revisar")}</strong><div class="small text-muted">${__("Vista previa final")}</div></button>
				</div>
			</div>
			<div class="alpha-panel active alpha-summary mt-3" data-panel="summary"><div class="alpha-empty">${__("Pulsa Analizar base AlphaERP para comenzar.")}</div></div>
			<div class="alpha-panel alpha-resolve mt-3" data-panel="resolve"></div>
			<div class="alpha-panel alpha-issues mt-3" data-panel="issues"></div>
			<div class="alpha-panel alpha-review mt-3" data-panel="review"></div>
		</div>`);

	const root = page.main.find(".alphaerp-migration")[0];
	const status = root.querySelector(".alpha-status");
	const button = root.querySelector(".alpha-analyze");
	let setup = null;
	let analysis = null;
	const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
	const mappingId = (type, key) => `AlphaERP|${type}|${key}`;
	const savedFor = (type, key) => setup?.saved?.[mappingId(type, key)] || null;
	const optionHtml = (values, selected, emptyLabel = __("Selecciona…")) => [
		`<option value="">${esc(emptyLabel)}</option>`,
		...(values || []).map((value) => `<option value="${esc(value)}" ${value === selected ? "selected" : ""}>${esc(value)}</option>`),
	].join("");
	const examplesHtml = (examples) => (examples || []).length
		? `<div class="alpha-examples">${__("Ejemplos")}: ${(examples || []).map((row) => `${esc(row.key)} — ${esc(row.name)}`).join(" · ")}</div>` : "";

	function setPanel(name) {
		root.querySelectorAll(".alpha-step").forEach((element) => element.classList.toggle("active", element.dataset.panel === name));
		root.querySelectorAll(".alpha-panel").forEach((element) => element.classList.toggle("active", element.dataset.panel === name));
	}
	root.querySelectorAll(".alpha-step").forEach((element) => element.addEventListener("click", () => setPanel(element.dataset.panel)));

	function currentResolution(type, key, suggested = "") {
		return savedFor(type, key)?.resolution || (suggested ? "Reuse" : "");
	}

	function groupState(row) {
		const profiles = row.source_profiles || [];
		const decisions = profiles.map((profile) => savedFor(row.mapping_type, profile.source_key));
		if (!profiles.length || decisions.some((decision) => !decision?.resolution)) return { resolution: "", target: "", settings: {} };
		const first = decisions[0];
		const templateKey = row.mapping_type === "Customer Tax" ? "sales_template" : row.mapping_type === "Supplier Tax" ? "purchase_template" : "";
		const same = decisions.every((decision) => decision.resolution === first.resolution
			&& (decision.target_name || "") === (first.target_name || "")
			&& (!templateKey || (decision.settings?.[templateKey] || "") === (first.settings?.[templateKey] || "")));
		return same ? { resolution: first.resolution, target: first.target_name || "", settings: first.settings || {} } : { resolution: "", target: "", settings: {} };
	}

	function rowResolved(row) {
		return row.source_profiles ? Boolean(groupState(row).resolution) : Boolean(currentResolution(row.mapping_type, row.source_key, row.suggested_target));
	}

	function unresolvedCounts() {
		if (!setup) return { total: 0, resolved: 0, pending: 0 };
		const rows = [...setup.tax_signatures, ...setup.commercial_classifications, ...setup.uoms.filter((row) => row.used), ...setup.item_groups];
		const resolved = rows.filter(rowResolved).length;
		const resolvedIssues = setup.source_issues.filter((row) => savedFor("Source Issue", row.source_key)?.resolution).length;
		return { total: rows.length + setup.source_issues.length, resolved: resolved + resolvedIssues, pending: rows.length - resolved + setup.source_issues.length - resolvedIssues };
	}

	function renderSummary() {
		const source = analysis.summary || {};
		const entities = analysis.entities || {};
		const readiness = unresolvedCounts();
		const percent = readiness.total ? Math.round(readiness.resolved * 100 / readiness.total) : 100;
		root.querySelector(".alpha-summary").innerHTML = `
			<div class="d-flex justify-content-between align-items-center mb-2"><div><strong>${__("Empresa destino")}:</strong> ${esc(analysis.company)}</div><span class="alpha-badge">${__("Sólo lectura")}</span></div>
			<div class="row g-3">
				${[["Clientes", "Customer"], ["Proveedores", "Supplier"], ["Productos", "Item"]].map(([label, entity]) => `<div class="col-md-4"><div class="alpha-kpi"><span class="text-muted">${__(label)}</span><strong>${source[label] || 0}</strong><small>${entities[entity]?.create || 0} ${__("por crear")} · ${entities[entity]?.update || 0} ${__("por actualizar")}</small></div></div>`).join("")}
				${[["Variantes", source.Variantes], ["Precios", source.Precios], ["Relaciones proveedor-producto", source["Relaciones proveedor-producto"]], ["Huérfanos de origen", analysis.issue_summary?.orphan || 0]].map(([label, value]) => `<div class="col-md-3"><div class="alpha-kpi"><span class="text-muted">${__(label)}</span><strong>${value || 0}</strong></div></div>`).join("")}
			</div>
			<div class="alpha-section"><div class="alpha-section-head"><div><strong>${__("Preparación de la migración")}</strong><div class="small text-muted">${readiness.resolved} ${__("decisiones resueltas")} · ${readiness.pending} ${__("pendientes")}</div></div><button class="btn btn-primary alpha-go-resolve">${__("Resolver pendientes")}</button></div><div class="p-3"><div class="alpha-progress"><span style="width:${percent}%"></span></div><div class="small text-muted mt-2">${percent}% ${__("preparado")}</div></div></div>
			<div class="alert alert-warning mt-3 mb-1">${esc(analysis.fiscal?.note || "")}</div>
			<div class="text-muted small mt-2">${__("Huella del origen")}: ${esc(analysis.fingerprint)}</div>`;
		root.querySelector(".alpha-go-resolve").addEventListener("click", () => setPanel("resolve"));
	}

	function resolutionOptions(kind, selected) {
		const values = kind === "UOM"
			? [["", __("Pendiente")], ["Reuse", __("Usar existente")], ["Create", __("Crear unidad")], ["Packaging", __("Tratar como empaque")], ["Variant", __("Tratar como presentación/variante")], ["Ignore", __("Excluir")]]
			: [["", __("Pendiente")], ["Reuse", __("Usar existente")], ["Create", __("Crear al ejecutar la migración")], ["Ignore", __("Excluir")]];
		return values.map(([value, label]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${esc(label)}</option>`).join("");
	}

	function categoryActionOptions(selected) {
		return [
			["", __("Pendiente")],
			["Create|tree", __("Crear jerarquía de categorías")],
			["Create|brand", __("Usar el tercer nivel como marca")],
			["Reuse|existing", __("Relacionar con grupo existente")],
			["Ignore|exclude", __("Excluir clasificación")],
		].map(([value, label]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${esc(label)}</option>`).join("");
	}

	function mapRow(row, kind, targets, extra = "") {
		const saved = savedFor(row.mapping_type, row.source_key);
		const resolution = currentResolution(row.mapping_type, row.source_key, row.suggested_target);
		const proposed = row.source_label || row.source_key;
		const choices = [...targets];
		if (proposed && !choices.includes(proposed)) choices.push(proposed);
		const target = saved?.target_name || row.suggested_target || proposed;
		return `<tr class="alpha-map-row ${resolution ? "resolved" : "pending"}" data-type="${esc(row.mapping_type)}" data-key="${esc(row.source_key)}" data-label="${esc(row.source_label)}" data-proposed="${esc(proposed)}" data-used="${row.used ? 1 : 0}" data-search="${esc(`${row.source_key} ${row.source_label} ${(row.examples || []).map((x) => `${x.key} ${x.name}`).join(" ")}`.toLowerCase())}">
			<td><input type="checkbox" class="alpha-select-row"></td>
			<td class="alpha-origin"><strong>${esc(row.source_key)}</strong><div class="text-muted small">${esc(row.source_label)}${row.sat ? ` · SAT ${esc(row.sat)}` : ""}</div>${examplesHtml(row.examples)}</td>
			<td class="alpha-impact"><strong>${row.impact || 0}</strong> ${__("registros afectados")}${extra}</td>
			<td><select class="form-control alpha-resolution">${resolutionOptions(kind, resolution)}</select></td>
			<td><select class="form-control alpha-target">${optionHtml(choices, target)}</select></td>
		</tr>`;
	}

	function categoryRow(row) {
		const saved = savedFor(row.mapping_type, row.source_key);
		const savedMode = saved?.settings?.classification_mode || "";
		const action = saved?.resolution === "Create" ? `Create|${savedMode || "tree"}` : saved?.resolution === "Reuse" ? "Reuse|existing" : saved?.resolution === "Ignore" ? "Ignore|exclude" : row.suggested_target ? "Reuse|existing" : "";
		const levels = [...(row.levels || []), "", ""].slice(0, 3);
		const targetValues = [...setup.options.item_groups];
		if (!targetValues.includes(row.source_key)) targetValues.push(row.source_key);
		const parentPath = (row.levels || []).slice(0, -1).join(" / ");
		if (parentPath && !targetValues.includes(parentPath)) targetValues.push(parentPath);
		const target = saved?.target_name || row.suggested_target || row.source_key;
		return `<tr class="alpha-map-row ${action ? "resolved" : "pending"}" data-type="Item Group" data-key="${esc(row.source_key)}" data-label="${esc(row.source_label)}" data-proposed="${esc(row.source_key)}" data-parent-path="${esc(parentPath)}" data-third="${esc(levels[2])}" data-search="${esc(`${row.source_key} ${(row.examples || []).map((x) => `${x.key} ${x.name}`).join(" ")}`.toLowerCase())}">
			<td><input type="checkbox" class="alpha-select-row"></td>
			<td class="alpha-origin"><div><span class="text-muted">${__("Categoría")}:</span> <strong>${esc(levels[0] || "—")}</strong></div><div><span class="text-muted">${__("Subcategoría")}:</span> ${esc(levels[1] || "—")}</div><div><span class="text-muted">${__("Tercer nivel")}:</span> ${esc(levels[2] || "—")} ${row.suggest_brand ? `<span class="alpha-badge pending">${__("Posible marca")}</span>` : ""}</div>${examplesHtml(row.examples)}</td>
			<td class="alpha-impact"><strong>${row.impact || 0}</strong> ${__("productos")}</td>
			<td><select class="form-control alpha-resolution">${categoryActionOptions(action)}</select></td>
			<td><select class="form-control alpha-target">${optionHtml(targetValues, target)}</select></td>
		</tr>`;
	}

	function groupedRow(row, targets, kind) {
		const state = groupState(row);
		const proposed = row.source_label || row.source_key;
		const choices = [...targets];
		if (proposed && !choices.includes(proposed)) choices.push(proposed);
		const target = state.target || row.suggested_target || proposed;
		const profiles = encodeURIComponent(JSON.stringify(row.source_profiles || []));
		const keys = (row.source_profiles || []).map((profile) => profile.source_key).join(", ");
		const isTax = kind === "tax";
		const rates = isTax
			? `<div class="small text-muted">IVA ${esc(row.iva)}% · Ret. IVA ${esc(row.retention_vat)}% · Ret. ISR ${esc(row.retention_income)}%${row.has_ieps ? " · IEPS" : ""}${row.exempt ? ` · ${__("Exento")}` : ""}</div>`
			: `<div class="small text-muted">${row.tiers?.length ? `${__("Niveles")}: ${row.tiers.map(esc).join(", ")}` : __("Sin nivel Oro/Azul/Platino")}</div>`;
		const templates = row.mapping_type === "Customer Tax" ? setup.options.sales_templates : setup.options.purchase_templates;
		const settingName = row.mapping_type === "Customer Tax" ? "sales_template" : "purchase_template";
		return `<tr class="alpha-map-row ${state.resolution ? "resolved" : "pending"}" data-type="${esc(row.mapping_type)}" data-key="${esc(row.signature_key || row.source_key)}" data-label="${esc(row.source_label || keys)}" data-proposed="${esc(proposed)}" data-profiles="${esc(profiles)}" data-search="${esc(`${row.party_type} ${proposed} ${keys} ${(row.examples || []).map((x) => `${x.key} ${x.name}`).join(" ")}`.toLowerCase())}">
			<td><input type="checkbox" class="alpha-select-row"></td>
			<td class="alpha-origin"><strong>${isTax ? esc(row.party_type) : esc(proposed)}</strong><div class="small text-muted">${row.profile_count} ${__("claves AlphaERP")}: ${esc(keys)}</div>${examplesHtml(row.examples)}</td>
			<td class="alpha-impact"><strong>${row.impact || 0}</strong> ${__("registros afectados")}${rates}</td>
			<td><select class="form-control alpha-resolution">${resolutionOptions("other", state.resolution)}</select></td>
			<td><select class="form-control alpha-target">${optionHtml(choices, target)}</select></td>
			${isTax ? `<td><select class="form-control alpha-template" data-setting="${settingName}">${optionHtml(templates, state.settings?.[settingName] || "", __("Sin plantilla explícita"))}</select></td>` : ""}
		</tr>`;
	}

	function taxAutoRow(row) {
		const state = groupState(row);
		const settingName = row.mapping_type === "Customer Tax" ? "sales_template" : "purchase_template";
		const profiles = encodeURIComponent(JSON.stringify(row.source_profiles || []));
		const keys = (row.source_profiles || []).map((profile) => profile.source_key).join(", ");
		const savedTemplate = state.settings?.[settingName] || state.settings?.existing_template || "";
		const existingTemplate = savedTemplate || row.matched_template || "";
		const existingCategory = state.target || row.matched_tax_category || "";
		const needsNewTemplate = !existingTemplate;
		const resolution = state.resolution || (existingTemplate && existingCategory ? "Reuse" : "Create");
		const newName = state.settings?.template_name || row.suggested_name;
		const categoryName = existingCategory || newName;
		const result = needsNewTemplate
			? `<strong>${__("Crear plantilla")}</strong><div class="small text-muted mb-1">${__("No existe otra con estos mismos impuestos.")}</div><input class="form-control alpha-template-name" value="${esc(newName)}" placeholder="${__("Nombre de la nueva plantilla")}">`
			: `<strong class="text-success">${__("Usar plantilla existente")}</strong><div>${esc(existingTemplate)}</div>${existingCategory ? `<div class="small text-muted">${__("Categoría fiscal")}: ${esc(existingCategory)}</div>` : `<div class="small text-muted">${__("BIMAP creará y vinculará internamente la categoría fiscal necesaria.")}</div>`}`;
		return `<tr class="alpha-map-row ${state.resolution ? "resolved" : "pending"}" data-type="${esc(row.mapping_type)}" data-key="${esc(row.signature_key)}" data-label="${esc(keys)}" data-profiles="${esc(profiles)}" data-existing-template="${esc(existingTemplate)}">
			<td class="alpha-origin"><strong>${esc(row.party_type)}</strong><div class="small text-muted">${row.profile_count} ${__("claves AlphaERP")}: ${esc(keys)}</div>${examplesHtml(row.examples)}</td>
			<td class="alpha-impact"><strong>${row.impact || 0}</strong> ${__("registros afectados")}<div class="small text-muted">IVA ${esc(row.iva)}% · Ret. IVA ${esc(row.retention_vat)}% · Ret. ISR ${esc(row.retention_income)}%${row.has_ieps ? " · IEPS" : ""}${row.exempt ? ` · ${__("Exento")}` : ""}</div></td>
			<td>${result}<input type="hidden" class="alpha-resolution" value="${esc(resolution)}"><input type="hidden" class="alpha-target" value="${esc(categoryName)}">${existingTemplate && existingCategory ? `<input type="hidden" class="alpha-template" data-setting="${settingName}" value="${esc(existingTemplate)}">` : ""}</td>
		</tr>`;
	}

	function section(id, title, help, rows, body, targetOptions = [], guide = "") {
		const pending = rows.filter((row) => !rowResolved(row)).length;
		return `<div class="alpha-section alpha-resolution-section" data-section="${id}">
			<div class="alpha-section-head"><div><strong>${esc(title)}</strong><div class="small text-muted">${esc(help)}</div></div><span class="alpha-badge ${pending ? "pending" : "ready"}">${pending ? `${pending} ${__("pendientes")}` : __("Completo")}</span></div>
			${guide ? `<div class="alert alert-info m-3 mb-0 small">${guide}</div>` : ""}
			<div class="alpha-toolbar"><label><input type="checkbox" class="alpha-only-pending" checked> ${__("Sólo pendientes")}</label>${id === "uoms" ? `<label><input type="checkbox" class="alpha-used-only" checked> ${__("Sólo unidades utilizadas")}</label>` : ""}<input class="form-control alpha-search" placeholder="${__("Buscar…")}"><div class="alpha-bulk-box"><span class="alpha-selected-count">0 ${__("seleccionadas")}</span><button class="btn btn-xs btn-default alpha-select-visible">${__("Seleccionar visibles")}</button><button class="btn btn-xs btn-default alpha-clear-selection">${__("Limpiar")}</button><select class="form-control alpha-bulk-resolution">${id === "groups" ? categoryActionOptions("") : resolutionOptions(id === "uoms" ? "UOM" : "other", "")}</select>${targetOptions.length ? `<select class="form-control alpha-bulk-target">${optionHtml(targetOptions, "", __("Destino para selección…"))}</select>` : ""}<button class="btn btn-primary alpha-apply-bulk" disabled>${__("Aplicar a seleccionadas")}</button></div></div>
			<div class="table-responsive" style="max-height:520px"><table class="table alpha-map-table mb-0"><thead class="position-sticky top-0 bg-white"><tr><th><input type="checkbox" class="alpha-select-all" title="${__("Seleccionar todas las filas visibles")}"></th><th>${id === "groups" ? __("Clasificación encontrada") : __("Origen")}</th><th>${__("Impacto")}</th><th>${__("Acción a realizar")}</th><th>${id === "groups" ? __("Resultado propuesto") : __("Destino ERPNext")}</th></tr></thead><tbody>${body}</tbody></table><div class="alpha-no-visible alpha-empty d-none">${__("No hay pendientes con este filtro.")}</div></div>
		</div>`;
	}

	function renderResolver() {
		const usedUoms = setup.uoms.filter((row) => row.used).length;
		const uomRows = setup.uoms.map((row) => {
			const savedFactor = savedFor(row.mapping_type, row.source_key)?.settings?.conversion_factor;
			const inferredFactor = row.source_key.match(/^C\/?(\d+)$/i)?.[1] || "";
			const factor = savedFactor || inferredFactor;
			const usage = Object.entries(row.impact_detail || {}).map(([label, count]) => `${count} ${label}`).join(" · ");
			const detail = `<div class="small text-muted">${esc(usage || __("No se usa en los catálogos"))}</div><div class="small mt-2">${__("Factor de empaque")}: <input type="number" min="0.000001" step="any" class="form-control form-control-sm alpha-conversion-factor" value="${esc(factor)}" placeholder="${__("Si aplica")}" style="width:110px;display:inline-block"></div>`;
			return mapRow(row, "UOM", setup.options.uoms, detail);
		}).join("");
		const groupRows = setup.item_groups.map(categoryRow).join("");
		const taxRows = setup.tax_signatures.map(taxAutoRow).join("");
		const commercialRows = setup.commercial_classifications.map((row) => groupedRow(
			row,
			row.mapping_type === "Customer Commercial" ? setup.options.customer_groups : setup.options.supplier_groups,
			"commercial",
		)).join("");
		const commercialFieldsReady = Object.values(setup.commercial_fields || {}).every(Boolean);
		root.querySelector(".alpha-resolve").innerHTML = `
			<div class="alert alert-info"><strong>${__("Primero impuestos; después clasificación comercial")}</strong><br>${__("Las claves con exactamente las mismas tasas se resuelven juntas. Después decides el grupo comercial sin mezclarlo con los impuestos.")}</div>
			<div class="alpha-section" data-section="tax"><div class="alpha-section-head"><div><strong>1. ${__("Configuraciones fiscales automáticas")}</strong><div class="small text-muted">${__("BIMAP reutiliza una plantilla cuando los impuestos coinciden. Si no existe, únicamente solicita el nombre de la nueva plantilla.")}</div></div><span class="alpha-badge">${setup.tax_signatures.length} ${__("configuraciones")}</span></div><div class="table-responsive" style="max-height:600px"><table class="table alpha-map-table mb-0"><thead class="position-sticky top-0 bg-white"><tr><th>${__("Tipo y claves AlphaERP")}</th><th>${__("Impacto e impuestos")}</th><th>${__("Resultado automático")}</th></tr></thead><tbody>${taxRows}</tbody></table></div></div>
			<div class="alpha-section alpha-resolution-section" data-section="commercial"><div class="alpha-section-head"><div><strong>2. ${__("Clasificación comercial")}</strong><div class="small text-muted">${__("Usa Grupo de clientes o Grupo de proveedores de ERPNext. Oro, Azul y Platino se conservan como nivel comercial independiente.")}</div></div><span class="alpha-badge">${setup.commercial_classifications.length}</span></div><div class="alert alert-info m-3 mb-0 small"><strong>${__("Recomendado")}</strong>: ${__("resuelve todas automáticamente usando los grupos nativos y conservando los datos AlphaERP en campos auxiliares.")} <button class="btn btn-sm btn-primary ml-2 alpha-prepare-all-commercial">${commercialFieldsReady ? __("Preparar todos automáticamente") : __("Usar grupos y crear campos para todos")}</button></div><div class="alpha-toolbar"><label><input type="checkbox" class="alpha-only-pending" checked> ${__("Sólo pendientes")}</label><input class="form-control alpha-search" placeholder="${__("Buscar clasificación…")}"><div class="alpha-bulk-box"><span class="alpha-selected-count">0 ${__("seleccionadas")}</span><button class="btn btn-xs btn-default alpha-select-visible">${__("Seleccionar visibles")}</button><button class="btn btn-xs btn-default alpha-clear-selection">${__("Limpiar")}</button><select class="form-control alpha-bulk-resolution">${resolutionOptions("other", "")}</select><select class="form-control alpha-bulk-target"><option value="">${__("Grupo destino…")}</option></select><button class="btn btn-primary alpha-apply-bulk" disabled>${__("Aplicar a seleccionadas")}</button></div></div><div class="table-responsive" style="max-height:600px"><table class="table alpha-map-table mb-0"><thead class="position-sticky top-0 bg-white"><tr><th><input type="checkbox" class="alpha-select-all"></th><th>${__("Clasificación AlphaERP")}</th><th>${__("Impacto y niveles")}</th><th>${__("Decisión")}</th><th>${__("Grupo ERPNext")}</th></tr></thead><tbody>${commercialRows}</tbody></table><div class="alpha-no-visible alpha-empty d-none">${__("No hay clasificaciones pendientes.")}</div></div></div>
			${section("uoms", __("Unidades y presentaciones"), __(`Sólo ${usedUoms} de ${setup.uoms.length} unidades se utilizan. Las demás están ocultas y no bloquean la migración.`), setup.uoms.filter((row) => row.used), uomRows, setup.options.uoms, `<strong>${__("Usar existente")}</strong>: equivale a una unidad actual. · <strong>${__("Crear unidad")}</strong>: se manejará directamente como C/12, LB, etc. · <strong>${__("Empaque")}</strong>: C/12 representa 12 piezas. · <strong>${__("Presentación/variante")}</strong>: tendrá identidad comercial propia.`)}
			${section("groups", __("Clasificación de productos"), __("Separamos los tres niveles para decidir si forman una jerarquía o si el tercero realmente es una marca."), setup.item_groups, groupRows, setup.options.item_groups, `<strong>${__("Crear jerarquía")}</strong>: ALAMBRES → REDONDO → TIRDEN. · <strong>${__("Usar como marca")}</strong>: grupo ALAMBRES → REDONDO y marca TIRDEN. · <strong>${__("Relacionar")}</strong>: envía los productos a un grupo que ya existe.`)}
			<div class="alpha-sticky-actions"><button class="btn btn-primary alpha-save-mappings">${__("Guardar decisiones")}</button><button class="btn btn-default alpha-go-issues">${__("Continuar a incidencias")}</button></div>`;
		wireResolutionSections();
		const commercialBulk = root.querySelector('[data-section="commercial"] .alpha-bulk-target');
		commercialBulk.innerHTML = `<option value="">${__("Grupo destino…")}</option>${optionHtml([...new Set([...setup.options.customer_groups, ...setup.options.supplier_groups])], "", __("Grupo destino…")).replace(/^<option[^>]*>.*?<\/option>/, "")}`;
		root.querySelector(".alpha-prepare-all-commercial")?.addEventListener("click", prepareAllCommercial);
		root.querySelector(".alpha-save-mappings").addEventListener("click", saveMappings);
		root.querySelector(".alpha-go-issues").addEventListener("click", () => setPanel("issues"));
	}

	function filterSection(sectionElement) {
		const onlyPending = sectionElement.querySelector(".alpha-only-pending")?.checked;
		const usedOnly = sectionElement.querySelector(".alpha-used-only")?.checked;
		const query = sectionElement.querySelector(".alpha-search")?.value.trim().toLowerCase() || "";
		let visible = 0;
		sectionElement.querySelectorAll(".alpha-map-row").forEach((row) => {
			const pending = !row.querySelector(".alpha-resolution").value;
			const show = (!onlyPending || pending) && (!usedOnly || row.dataset.used === "1") && (!query || row.dataset.search.includes(query));
			row.classList.toggle("d-none", !show); if (show) visible += 1;
		});
		sectionElement.querySelector(".alpha-no-visible")?.classList.toggle("d-none", visible > 0);
		updateSectionSelection(sectionElement);
	}

	function updateSectionSelection(sectionElement) {
		const rows = [...sectionElement.querySelectorAll(".alpha-map-row")];
		const selectedRows = rows.filter((row) => row.querySelector(".alpha-select-row").checked);
		const visibleRows = rows.filter((row) => !row.classList.contains("d-none"));
		rows.forEach((row) => row.classList.toggle("selected", row.querySelector(".alpha-select-row").checked));
		const count = sectionElement.querySelector(".alpha-selected-count");
		if (count) count.textContent = `${selectedRows.length} ${selectedRows.length === 1 ? __("seleccionada") : __("seleccionadas")}`;
		const apply = sectionElement.querySelector(".alpha-apply-bulk");
		if (apply) apply.disabled = selectedRows.length === 0;
		const selectAll = sectionElement.querySelector(".alpha-select-all");
		if (selectAll) {
			selectAll.checked = visibleRows.length > 0 && visibleRows.every((row) => row.querySelector(".alpha-select-row").checked);
			selectAll.indeterminate = visibleRows.some((row) => row.querySelector(".alpha-select-row").checked) && !selectAll.checked;
		}
	}

	function wireResolutionSections() {
		root.querySelectorAll(".alpha-resolution-section").forEach((sectionElement) => {
			sectionElement.querySelector(".alpha-only-pending")?.addEventListener("change", () => filterSection(sectionElement));
			sectionElement.querySelector(".alpha-used-only")?.addEventListener("change", () => filterSection(sectionElement));
			sectionElement.querySelector(".alpha-search")?.addEventListener("input", () => filterSection(sectionElement));
			sectionElement.querySelectorAll(".alpha-select-row").forEach((box) => box.addEventListener("change", () => updateSectionSelection(sectionElement)));
			sectionElement.querySelector(".alpha-select-all")?.addEventListener("change", (event) => {
				sectionElement.querySelectorAll(".alpha-map-row:not(.d-none) .alpha-select-row").forEach((box) => { box.checked = event.target.checked; });
				updateSectionSelection(sectionElement);
			});
			sectionElement.querySelector(".alpha-select-visible")?.addEventListener("click", () => {
				sectionElement.querySelectorAll(".alpha-map-row:not(.d-none) .alpha-select-row").forEach((box) => { box.checked = true; });
				updateSectionSelection(sectionElement);
			});
			sectionElement.querySelector(".alpha-clear-selection")?.addEventListener("click", () => {
				sectionElement.querySelectorAll(".alpha-select-row").forEach((box) => { box.checked = false; });
				updateSectionSelection(sectionElement);
			});
			sectionElement.querySelector(".alpha-apply-bulk")?.addEventListener("click", () => {
				const resolution = sectionElement.querySelector(".alpha-bulk-resolution").value;
				const target = sectionElement.querySelector(".alpha-bulk-target")?.value;
				if (!resolution) return frappe.msgprint(__("Elige primero una decisión masiva."));
				if (["Reuse", "Reuse|existing", "Packaging", "Variant"].includes(resolution) && !target) {
					return frappe.msgprint(__("Esta acción necesita que elijas también un destino ERPNext."));
				}
				let skipped = 0;
				sectionElement.querySelectorAll(".alpha-map-row").forEach((row) => {
					if (!row.querySelector(".alpha-select-row").checked) return;
					if (resolution === "Create|brand" && !row.dataset.third) { skipped += 1; return; }
					row.querySelector(".alpha-resolution").value = resolution;
					if (target) row.querySelector(".alpha-target").value = target;
					else if (resolution === "Create|tree") row.querySelector(".alpha-target").value = row.dataset.proposed;
					else if (resolution === "Create|brand") row.querySelector(".alpha-target").value = row.dataset.parentPath;
					row.classList.toggle("resolved", Boolean(resolution)); row.classList.toggle("pending", !resolution);
				});
				filterSection(sectionElement);
				sectionElement.querySelectorAll(".alpha-select-row").forEach((box) => { box.checked = false; });
				updateSectionSelection(sectionElement);
				if (skipped) frappe.show_alert({ message: __(`Se omitieron ${skipped} filas porque no tienen tercer nivel para usar como marca.`), indicator: "orange" });
			});
			sectionElement.querySelectorAll(".alpha-resolution").forEach((select) => select.addEventListener("change", () => {
				const row = select.closest(".alpha-map-row");
				if (select.value === "Create" || select.value === "Create|tree") row.querySelector(".alpha-target").value = row.dataset.proposed;
				if (select.value === "Create|brand") row.querySelector(".alpha-target").value = row.dataset.parentPath;
				row.classList.toggle("resolved", Boolean(select.value)); row.classList.toggle("pending", !select.value); filterSection(sectionElement);
			}));
			filterSection(sectionElement);
		});
	}

	function renderIssues() {
		const rows = setup.source_issues.map((issue) => {
			const saved = savedFor("Source Issue", issue.source_key);
			const resolved = Boolean(saved?.resolution);
			const treatment = saved?.resolution === "Reuse" ? `${__("Relacionar con")} ${saved.target_name}` : saved?.resolution === "Ignore" ? __("Excluir relación inválida") : __("Pendiente");
			return `<tr class="alpha-issue-row ${resolved ? "resolved" : "pending"}" data-key="${esc(issue.source_key)}" data-label="${esc(issue.message)}" data-target-doctype="${esc(issue.target_doctype)}" data-target="${esc(saved?.target_name || "")}" data-resolution="${esc(saved?.resolution || "")}" data-search="${esc(`${issue.entity} ${issue.source_key} ${issue.message}`.toLowerCase())}"><td><input type="checkbox" class="alpha-select-issue"></td><td><strong>${esc(issue.entity)}</strong><div class="small text-muted">${esc(issue.source_key.split("|")[1] || "")}</div></td><td class="alpha-issue-message">${esc(issue.message)}</td><td><span class="alpha-badge ${resolved ? "ready" : "pending"}">${esc(treatment)}</span><div class="mt-1">${issue.target_doctype ? `<button class="btn btn-xs btn-default alpha-link-issue">${__("Relacionar")}</button> ` : ""}<button class="btn btn-xs btn-default alpha-ignore-one">${__("Excluir")}</button></div></td></tr>`;
		}).join("");
		root.querySelector(".alpha-issues").innerHTML = `<div class="alpha-section"><div class="alpha-section-head"><div><strong>${__("Incidencias del origen")}</strong><div class="small text-muted">${__("Son referencias rotas que ya existen así en AlphaERP. Nunca se corregirán silenciosamente.")}</div></div><span class="alpha-badge pending">${setup.source_issues.filter((x) => !savedFor("Source Issue", x.source_key)).length} ${__("pendientes")}</span></div><div class="alpha-toolbar"><input class="form-control alpha-issue-search" placeholder="${__("Buscar incidencia…")}"><button class="btn btn-default alpha-select-all-issues">${__("Seleccionar visibles")}</button><button class="btn btn-warning alpha-ignore-issues">${__("Excluir relaciones seleccionadas")}</button></div><div class="table-responsive" style="max-height:620px"><table class="table mb-0"><thead class="position-sticky top-0 bg-white"><tr><th></th><th>${__("Origen")}</th><th>${__("Problema")}</th><th>${__("Tratamiento")}</th></tr></thead><tbody>${rows || `<tr><td colspan="4" class="alpha-empty">${__("No se encontraron incidencias.")}</td></tr>`}</tbody></table></div></div><div class="alpha-sticky-actions"><button class="btn btn-primary alpha-save-issues">${__("Guardar decisiones")}</button><button class="btn btn-default alpha-go-review">${__("Continuar a revisión")}</button></div>`;
		const issuePanel = root.querySelector(".alpha-issues");
		const filterIssues = () => { const q = issuePanel.querySelector(".alpha-issue-search").value.toLowerCase(); issuePanel.querySelectorAll(".alpha-issue-row").forEach((row) => row.classList.toggle("d-none", q && !row.dataset.search.includes(q))); };
		issuePanel.querySelector(".alpha-issue-search").addEventListener("input", filterIssues);
		issuePanel.querySelector(".alpha-select-all-issues").addEventListener("click", () => issuePanel.querySelectorAll(".alpha-issue-row:not(.d-none) .alpha-select-issue").forEach((box) => { box.checked = true; }));
		issuePanel.querySelector(".alpha-ignore-issues").addEventListener("click", () => issuePanel.querySelectorAll(".alpha-issue-row").forEach((row) => { if (row.querySelector(".alpha-select-issue").checked) { row.dataset.resolution = "Ignore"; row.querySelector(".alpha-badge").textContent = __("Excluir relación inválida"); row.classList.add("resolved"); row.classList.remove("pending"); } }));
		issuePanel.querySelectorAll(".alpha-ignore-one").forEach((element) => element.addEventListener("click", () => {
			const row = element.closest(".alpha-issue-row"); row.dataset.resolution = "Ignore"; row.dataset.target = ""; row.querySelector(".alpha-badge").textContent = __("Excluir relación inválida"); row.classList.add("resolved"); row.classList.remove("pending");
		}));
		issuePanel.querySelectorAll(".alpha-link-issue").forEach((element) => element.addEventListener("click", () => {
			const row = element.closest(".alpha-issue-row");
			frappe.prompt([{ fieldname: "target", fieldtype: "Link", options: row.dataset.targetDoctype, label: __("Registro existente"), reqd: 1, default: row.dataset.target }], (values) => {
				row.dataset.resolution = "Reuse"; row.dataset.target = values.target; row.querySelector(".alpha-badge").textContent = `${__("Relacionar con")} ${values.target}`; row.classList.add("resolved"); row.classList.remove("pending");
			}, __("Relacionar incidencia"), __("Aceptar"));
		}));
		issuePanel.querySelector(".alpha-save-issues").addEventListener("click", saveMappings);
		issuePanel.querySelector(".alpha-go-review").addEventListener("click", () => { renderReview(); setPanel("review"); });
	}

	function renderReview() {
		const readiness = unresolvedCounts();
		const ready = readiness.pending === 0;
		root.querySelector(".alpha-review").innerHTML = `<div class="alpha-section"><div class="alpha-section-head"><div><strong>${__("Revisión final por catálogo")}</strong><div class="small text-muted">${__("Muestra únicamente los registros con problemas. ERPNext todavía no se modifica.")}</div></div><span class="alpha-badge ${ready ? "ready" : "pending"}">${ready ? __("Configuración completa") : `${readiness.pending} ${__("decisiones pendientes")}`}</span></div><div class="p-3"><div class="btn-group"><button class="btn btn-default alpha-preview" data-catalog="Customer">${__("Clientes")}</button><button class="btn btn-default alpha-preview" data-catalog="Supplier">${__("Proveedores")}</button><button class="btn btn-default alpha-preview" data-catalog="Item">${__("Productos")}</button></div><label class="ml-3"><input type="checkbox" class="alpha-only-errors" checked> ${__("Ocultar filas correctas")}</label><div class="alpha-preview-result mt-3"><div class="alpha-empty">${__("Elige un catálogo para validarlo.")}</div></div></div></div><div class="alert ${ready ? "alert-success" : "alert-warning"} mt-3">${ready ? __("Las decisiones están completas. La importación real permanecerá deshabilitada hasta incorporar y probar el ejecutor transaccional.") : __("La importación está bloqueada mientras existan decisiones pendientes.")}</div>`;
		root.querySelectorAll(".alpha-preview").forEach((element) => element.addEventListener("click", () => loadCatalogPreview(element.dataset.catalog)));
		root.querySelector(".alpha-only-errors").addEventListener("change", filterPreviewRows);
	}

	function collectDecisionRows() {
		const rows = [...root.querySelectorAll(".alpha-map-row")].flatMap((element) => {
			const rawResolution = element.querySelector(".alpha-resolution").value;
			if (!rawResolution) return [];
			const [resolution, classificationMode] = rawResolution.split("|");
			const template = element.querySelector(".alpha-template");
			const settings = template?.value ? { [template.dataset.setting]: template.value } : {};
			const templateName = element.querySelector(".alpha-template-name")?.value.trim();
			if (templateName) settings.template_name = templateName;
			if (element.dataset.existingTemplate && !template?.value) settings.existing_template = element.dataset.existingTemplate;
			const conversionFactor = element.querySelector(".alpha-conversion-factor")?.value;
			if (conversionFactor) settings.conversion_factor = conversionFactor;
			if (element.dataset.type === "Item Group" && classificationMode) {
				settings.classification_mode = classificationMode;
				if (classificationMode === "brand" && element.dataset.third) settings.brand_name = element.dataset.third;
			}
			const profiles = element.dataset.profiles ? JSON.parse(decodeURIComponent(element.dataset.profiles)) : null;
			if (profiles) {
				return profiles.map((profile) => ({
					mapping_type: element.dataset.type,
					source_key: profile.source_key,
					source_label: profile.source_label,
					resolution,
					target_name: templateName || element.querySelector(".alpha-target")?.value || "",
					settings: {
						...settings,
						...(element.dataset.type.includes("Commercial") ? {
							commercial_tier: profile.tier || "",
							source_profile: profile.source_label || profile.source_key,
						} : {}),
					},
				}));
			}
			return [{ mapping_type: element.dataset.type, source_key: element.dataset.key, source_label: element.dataset.label, resolution, target_name: templateName || element.querySelector(".alpha-target")?.value || "", settings }];
		});
		root.querySelectorAll(".alpha-issue-row[data-resolution]").forEach((element) => {
			if (!element.dataset.resolution) return;
			rows.push({ mapping_type: "Source Issue", source_key: element.dataset.key, source_label: element.dataset.label, resolution: element.dataset.resolution, target_name: element.dataset.target || "", settings: element.dataset.targetDoctype ? { target_doctype: element.dataset.targetDoctype } : {} });
		});
		return rows;
	}

	function prepareAllCommercial() {
		frappe.confirm(
			__("BIMAP reutilizará los grupos que ya existan, preparará la creación de los faltantes y creará los campos auxiliares para conservar la clasificación y el nivel comercial. ¿Continuar?"),
			async () => {
				const response = await frappe.call({ method: "bimap_data_engine.api.alphaerp.prepare_all_commercial_classifications", type: "POST", freeze: true, freeze_message: __("Preparando todas las clasificaciones…") });
				setup = await frappe.call({ method: "bimap_data_engine.api.alphaerp.get_equivalence_setup", type: "GET" }).then((r) => r.message);
				renderAll();
				setPanel("resolve");
				frappe.msgprint({
					title: __("Clasificaciones preparadas"),
					indicator: "green",
					message: __("Se resolvieron {0} clasificaciones: {1} usarán grupos existentes y {2} crearán grupos al ejecutar la migración.", [response.message.classifications, response.message.reused, response.message.to_create]),
				});
			},
		);
	}

	async function saveMappings() {
		const rows = collectDecisionRows();
		const response = await frappe.call({ method: "bimap_data_engine.api.alphaerp.save_equivalence_setup", type: "POST", args: { rows }, freeze: true, freeze_message: __("Guardando decisiones…") });
		frappe.show_alert({ message: __("Se guardaron {0} decisiones.", [response.message.saved]), indicator: "green" });
		setup = await frappe.call({ method: "bimap_data_engine.api.alphaerp.get_equivalence_setup", type: "GET" }).then((r) => r.message);
		renderAll();
	}

	function filterPreviewRows() {
		const onlyErrors = root.querySelector(".alpha-only-errors")?.checked;
		root.querySelectorAll(".alpha-preview-row").forEach((row) => row.classList.toggle("d-none", onlyErrors && row.dataset.blocking !== "1"));
	}

	async function loadCatalogPreview(catalog, start = 0) {
		const container = root.querySelector(".alpha-preview-result");
		container.innerHTML = `<div class="alpha-empty">${__("Preparando vista previa…")}</div>`;
		const response = await frappe.call({ method: "bimap_data_engine.api.alphaerp.preview_catalog", type: "GET", args: { catalog, start, page_length: 50 } });
		const data = response.message;
		const rows = data.rows.map((row) => {
			const blocking = row.issues.some((issue) => (issue.severity || "error") === "error");
			const problems = row.issues.map((issue) => `<div class="${issue.severity === "warning" ? "text-warning" : "text-danger"}">${esc(issue.message)}</div>`).join("");
			return `<tr class="alpha-preview-row" data-blocking="${blocking ? 1 : 0}"><td>${esc(row.source_key)}</td><td>${esc(row.action === "create" ? __("Crear") : __("Actualizar"))}</td><td><pre class="alpha-preview-json mb-0">${esc(JSON.stringify(row.values, null, 2))}</pre></td><td>${problems || `<span class="text-success">${__("Sin bloqueos")}</span>`}</td></tr>`;
		}).join("");
		container.innerHTML = `<div class="mb-2"><strong>${data.total}</strong> ${__("registros")} · <strong>${data.blocking_rows}</strong> ${__("bloqueados en esta página")}</div><div class="table-responsive" style="max-height:620px"><table class="table table-bordered"><thead class="position-sticky top-0 bg-white"><tr><th>${__("Clave")}</th><th>${__("Acción")}</th><th>${__("Destino propuesto")}</th><th>${__("Validación")}</th></tr></thead><tbody>${rows}</tbody></table></div><div class="d-flex justify-content-between"><button class="btn btn-default alpha-prev-page" ${data.start <= 0 ? "disabled" : ""}>${__("Anterior")}</button><button class="btn btn-default alpha-next-page" ${data.next_start === null ? "disabled" : ""}>${__("Siguiente")}</button></div>`;
		container.querySelector(".alpha-prev-page").addEventListener("click", () => loadCatalogPreview(catalog, Math.max(0, data.start - data.page_length)));
		container.querySelector(".alpha-next-page").addEventListener("click", () => loadCatalogPreview(catalog, data.next_start));
		filterPreviewRows();
	}

	function renderAll() { renderSummary(); renderResolver(); renderIssues(); renderReview(); }
	button.addEventListener("click", async () => {
		button.disabled = true; status.textContent = __("Leyendo y reconciliando la base…");
		try {
			const [summaryResponse, setupResponse] = await Promise.all([
				frappe.call({ method: "bimap_data_engine.api.alphaerp.preview_summary", type: "GET" }),
				frappe.call({ method: "bimap_data_engine.api.alphaerp.get_equivalence_setup", type: "GET" }),
			]);
			analysis = summaryResponse.message || {}; setup = setupResponse.message || {}; renderAll();
			status.textContent = __("Análisis terminado. ERPNext no fue modificado.");
		} catch (error) { status.textContent = __("No se pudo completar el análisis."); throw error; }
		finally { button.disabled = false; }
	});
};
