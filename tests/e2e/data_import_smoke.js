const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

const ROOT = "/home/afficent/frappe-bench";
const SITE = "mi-sitio.local";
const BASE = `http://${SITE}:${process.env.BDE_E2E_PORT || "8000"}`;

function benchExecute(method, kwargs = {}) {
	const output = execFileSync(
		"bench",
		["--site", SITE, "execute", method, "--kwargs", JSON.stringify(kwargs)],
		{ cwd: ROOT, encoding: "utf8" },
	);
	const line = output.trim().split("\n").reverse().find((candidate) => candidate.trim());
	try { return JSON.parse(line); } catch (_error) { return line; }
}

(async () => {
	const fixture = benchExecute("bimap_data_engine.tests.e2e_fixture.create_import_file");
	const defaults = benchExecute("bimap_data_engine.tests.e2e_fixture.get_item_defaults");
	const salesContext = benchExecute("bimap_data_engine.tests.e2e_fixture.create_sales_template_context");
	const session = benchExecute("bimap_core.api.testing.create_playwright_session", { user: "Administrator" });
	let browser;
	try {
		browser = await chromium.launch({ headless: true, args: [`--host-resolver-rules=MAP ${SITE} 127.0.0.1`] });
		const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
		await context.addCookies([
			{ name: "sid", value: session.sid, domain: SITE, path: "/", httpOnly: true },
			{ name: "full_name", value: session.full_name, domain: SITE, path: "/" },
			{ name: "user_id", value: session.user, domain: SITE, path: "/" },
			{ name: "system_user", value: "yes", domain: SITE, path: "/" },
		]);
		const page = await context.newPage();
		const errors = [];
		page.on("pageerror", (error) => {
			errors.push(String(error));
			console.error(`PAGE ERROR: ${error}`);
		});
		page.on("console", (message) => {
			if (message.type() === "error") console.error(`BROWSER ERROR: ${message.text()}`);
		});
		page.on("response", (response) => {
			if (response.status() >= 400 && !response.url().includes("socket.io")) {
				const message = `HTTP ${response.status()}: ${response.url()}`;
				errors.push(message);
				console.error(message);
			}
		});
		const response = await page.goto(`${BASE}/app/bimap-data-import`, { waitUntil: "networkidle", timeout: 60000 });
		if (response && response.status() >= 400) {
			console.error((await response.text()).slice(0, 4000));
		}
		await page.waitForFunction(() => document.querySelector(".bdi-area option[value='catalogs']"), null, { timeout: 30000 });
		await page.locator(".bdi-area").selectOption("catalogs");
		await page.locator(".bdi-doctype").selectOption("Item");
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().schema === "Item", null, { timeout: 30000 });
		await page.locator(".bdi-template").click();
		await page.waitForFunction(
			() => window.BimapDataImportPage?.getState().template === "Item"
				&& window.BimapDataImportPage?.getState().adapterReady,
			null,
			{ timeout: 60000 },
		);
		await page.locator(".bdi-field-choice", { hasText: "Descripción" }).locator("input").check();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().columns.includes("Descripción"), null, { timeout: 30000 });
		const spreadsheetCssLoaded = await page.evaluate(() => fetch(
			"/assets/bimap_data_engine/node_modules/@univerjs/preset-sheets-core/lib/index.css",
		).then((result) => result.ok && Number(result.headers.get("content-length") || 0) > 100000));
		const spanishFlow = await page.locator(".bdi-area option:checked").textContent() === "Catálogos"
			&& await page.locator(".bdi-doctype option:checked").textContent() === "Artículos";
		await page.evaluate((values) => { document.querySelector(".bdi-defaults").value = JSON.stringify(values); }, defaults);
		await page.evaluate((itemCode) => {
			window.BimapDataImportPage.setCell(0, "Folio externo", "item-1");
			window.BimapDataImportPage.setCell(0, "Clave del artículo", itemCode);
			window.BimapDataImportPage.setCell(0, "Descripción", "Imported through spreadsheet");
		}, fixture.item_code);
		if (process.env.BDE_SCREENSHOT) {
			await page.locator(".bde-grid canvas").first().waitFor({ state: "visible", timeout: 30000 });
			await page.waitForTimeout(500);
			await page.screenshot({ path: process.env.BDE_SCREENSHOT, fullPage: true });
		}
		await page.locator(".bdi-preview").click();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().plan?.valid === true, null, { timeout: 30000 });
		const plan = await page.evaluate(() => window.BimapDataImportPage.getState().plan);
		const result = benchExecute("bimap_data_engine.tests.e2e_fixture.execute_import_plan", {
			plan: JSON.stringify(plan),
		});
		const created = benchExecute("frappe.client.get_value", {
			doctype: "Item", filters: { name: fixture.item_code }, fieldname: ["name", "description"],
		});
		await page.locator(".bdi-change-document").click();
		await page.locator(".bdi-area").selectOption("sales");
		await page.locator(".bdi-doctype").selectOption("Sales Order");
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().schema === "Sales Order", null, { timeout: 30000 });
		await page.locator(".bdi-template").click();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().template === "Sales Order", null, { timeout: 60000 });
		await page.getByRole("checkbox", { name: "Fecha de entrega (cabecera)", exact: true }).check();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().columns.includes("Fecha de entrega (cabecera)"), null, { timeout: 30000 });
		await page.locator(".bdi-field-choice", { hasText: "Precio unitario" }).locator("input").check();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().columns.includes("Precio unitario"), null, { timeout: 30000 });
		const detailGuideVisible = await page.locator(".bdi-sheet option:checked").textContent() === "Captura completa"
			&& await page.locator(".bdi-field-picker", { hasText: "Clave de producto" }).isVisible()
			&& await page.locator(".bde-import-shell.bdi-workspace-active").count() === 1;
		await page.evaluate((company) => { document.querySelector(".bdi-defaults").value = JSON.stringify({ company }); }, salesContext.company);
		await page.evaluate((context) => {
			for (const [row, qty] of [[0, 2], [1, 3]]) {
				window.BimapDataImportPage.setCell(row, "Folio externo", "order-1");
				window.BimapDataImportPage.setCell(row, "Clave de cliente", context.customer_key);
				window.BimapDataImportPage.setCell(row, "Fecha", context.date);
				window.BimapDataImportPage.setCell(row, "Fecha de entrega (cabecera)", context.delivery_date);
				window.BimapDataImportPage.setCell(row, "Clave de producto", context.itemCode.toLowerCase());
				window.BimapDataImportPage.setCell(row, "Cantidad", qty);
				window.BimapDataImportPage.setCell(row, "Unidad", context.stock_uom);
				window.BimapDataImportPage.setCell(row, "Precio unitario", 10);
			}
		}, { ...salesContext, itemCode: fixture.item_code });
		await page.waitForFunction(() => {
			const row = window.BimapDataImportPage?.getRows?.()[0] || {};
			return Boolean(row["Nombre del cliente"] && row["Nombre del producto"]);
		}, null, { timeout: 30000 });
		const resolvedNamesVisible = await page.evaluate(() => {
			const row = window.BimapDataImportPage.getRows()[0];
			return Boolean(row["Nombre del cliente"] && row["Nombre del producto"]);
		});
		await page.locator(".bdi-preview").click();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().plan !== null, null, { timeout: 30000 });
		const transactionPlan = await page.evaluate(() => window.BimapDataImportPage.getState().plan);
		const checks = {
			httpOk: response?.status() === 200,
			spanishFlow,
			spreadsheetCssLoaded,
			pageMounted: await page.locator(".bde-grid canvas").count() > 0,
			previewValid: plan.valid === true && plan.records.length === 1,
			jobSucceeded: result.status === "Success",
			documentCreated: created?.name === fixture.item_code && created?.description === "Imported through spreadsheet",
			transactionTemplateValid: transactionPlan.valid === true && transactionPlan.records.length === 1
				&& transactionPlan.records[0].children.items.length === 2,
			resolvedNamesVisible,
			detailGuideVisible,
			noPageErrors: errors.length === 0,
		};
		const report = { status: Object.values(checks).every(Boolean) ? "passed" : "failed", checks, errors };
		console.log(JSON.stringify(report, null, 2));
		if (report.status !== "passed") process.exitCode = 1;
	} finally {
		if (browser) await browser.close();
		benchExecute("bimap_data_engine.tests.e2e_fixture.delete_import_fixture", {
			item_code: fixture.item_code,
			file_name: fixture.file_name,
		});
		benchExecute("bimap_data_engine.tests.e2e_fixture.delete_sales_template_context", {
			customer: salesContext.customer,
		});
	}
})().catch((error) => {
	console.error(error.stack || String(error));
	process.exitCode = 1;
});
