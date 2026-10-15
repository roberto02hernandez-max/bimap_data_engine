window.BimapDataEngineIntegration = {
	async call(method, args) {
		const response = await frappe.call({ method, type: "POST", args });
		return response.message;
	},

	async createContext(options) {
		return this.call(
			"bimap_data_engine.api.integration.create_editor_context",
			{
				doctype: options.doctype,
				mode: options.mode || "Edit",
				allowed_fields: options.allowedFields || null,
				filters: options.filters || null,
				source_app: options.sourceApp || null,
			},
		);
	},

	async open(options) {
		const context = await this.createContext(options);
		window.location.assign(context.route);
		return context;
	},

	async prepareDocumentLines(options = {}) {
		return this.call(
			"bimap_data_engine.api.integration.prepare_document_lines",
			{
				parent_doctype: options.parentDoctype,
				table_field: options.tableField || "items",
				parent_values: options.parentValues || {},
				existing_rows: options.existingRows || [],
				imported_rows: options.importedRows || [],
				merge_policy: options.mergePolicy || "append",
				match_fields: options.matchFields || null,
			},
		);
	},

	applyPreparedLinesToScreen(screen, result = {}) {
		if (!screen?.grid || !Array.isArray(result.rows)) return false;
		screen.grid.rows = result.rows.length
			? result.rows.map((row) => screen.grid.newRow({ ...row }))
			: [screen.grid.newRow()];
		screen.grid.render();
		screen.grid.notifyRowsChanged();
		screen.scheduleSellingPreview?.();
		return true;
	},
};
