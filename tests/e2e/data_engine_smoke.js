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
	const fixture = benchExecute("bimap_data_engine.tests.e2e_fixture.create_item");
	const session = benchExecute("bimap_core.api.testing.create_playwright_session", { user: "Administrator" });
	let browser;
	try {
		browser = await chromium.launch({
			headless: true,
			args: [`--host-resolver-rules=MAP ${SITE} 127.0.0.1`],
		});
		const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
		await context.addCookies([
			{ name: "sid", value: session.sid, domain: SITE, path: "/", httpOnly: true },
			{ name: "full_name", value: session.full_name, domain: SITE, path: "/" },
			{ name: "user_id", value: session.user, domain: SITE, path: "/" },
			{ name: "system_user", value: "yes", domain: SITE, path: "/" },
		]);
		const page = await context.newPage();
		const errors = [];
		page.on("pageerror", (error) => errors.push(String(error)));
		page.on("response", (resource) => {
			if (resource.status() >= 400 && !resource.url().includes("socket.io")) {
				errors.push(`HTTP ${resource.status()}: ${resource.url()}`);
			}
		});
		page.on("console", (message) => {
			if (
				message.type() === "error"
				&& !message.text().includes("socket.io")
				&& !message.text().includes("Failed to load resource")
			) errors.push(`console: ${message.text()}`);
		});
		const response = await page.goto(`${BASE}/app/bimap-data-engine`, {
			waitUntil: "networkidle",
			timeout: 60000,
		});
		let priceListChoices = 0;
		let filteredPriceListPrepared = false;
		let priceListFixedChip = false;
		let priceListFilterFields = [];
		try {
			await page.locator('.bde-area option[value="catalogs"]').waitFor({ state: "attached", timeout: 30000 });
			await page.locator(".bde-area").selectOption("catalogs");
			priceListChoices = await page.locator('.bde-document option[value^="Item Price::"]').count();
			const firstPriceList = await page.locator('.bde-document option[value^="Item Price::"]').first().getAttribute("value");
			await page.locator(".bde-document").selectOption(firstPriceList);
			await page.locator(".bde-prepare").click();
			await page.locator('.bde-fields option[value="price_list"]').waitFor({ state: "attached", timeout: 30000 });
			filteredPriceListPrepared = await page.locator(".bde-filters").evaluate((input) => (
				input.readOnly && Boolean(JSON.parse(input.value).price_list)
			));
			priceListFixedChip = await page.locator(".bde-fixed-filter").count() === 1;
			await page.locator(".bde-add-filter").click();
			priceListFilterFields = await page.locator(".bde-filter-row .bde-filter-field").first().locator("option").evaluateAll(
				(options) => options.map((option) => option.value),
			);
			await page.locator(".bde-change-document").click();
			await page.locator(".bde-document").selectOption("Item");
			await page.locator(".bde-prepare").click();
			await page.locator('.bde-fields option[value="description"]').waitFor({ state: "attached", timeout: 30000 });
		} catch (error) {
			throw new Error(JSON.stringify({
				message: error.message,
				status: response?.status(),
				url: page.url(),
				title: await page.title(),
				shells: await page.locator(".bde-shell").count(),
				body: (await page.locator("body").innerText()).slice(0, 1000),
				errors,
			}, null, 2));
		}
		await page.locator(".bde-add-filter").click();
		const filterRow = page.locator(".bde-filter-row").first();
		await filterRow.locator(".bde-filter-field").selectOption("item_code");
		await filterRow.locator(".bde-filter-operator").selectOption("=");
		await filterRow.locator(".bde-filter-value input").fill(fixture.name);
		await page.locator(".bde-advanced summary").click();
		await page.locator(".bde-fields").evaluate((select) => {
			for (const option of select.options) option.selected = ["description", "image"].includes(option.value);
		});
		await page.locator(".bde-advanced summary").click();
		await page.locator(".bde-load").click();
		await page.waitForFunction(() => window.BimapDataEnginePage?.getState().adapterReady, null, { timeout: 60000 });
		await page.evaluate(() => window.BimapDataEnginePage.setValue(0, "description", "E2E updated"));
		await page.locator(".bde-preview").click();
		await page.waitForFunction(() => !document.querySelector(".bde-apply").disabled, null, { timeout: 30000 });
		await page.locator(".bde-apply").click();
		await page.locator(".modal .btn-primary:visible").click();
		await page.waitForTimeout(1000);
		const description = benchExecute("bimap_data_engine.tests.e2e_fixture.get_description", { name: fixture.name });
		await page.locator(".bde-advanced summary").click();
		await page.locator(".bde-clear-record").selectOption(fixture.name);
		await page.locator(".bde-clear-field").selectOption("image");
		await page.locator(".bde-mark-clear").click();
		await page.locator(".bde-preview").click();
		await page.waitForFunction(() => !document.querySelector(".bde-apply").disabled, null, { timeout: 30000 });
		await page.locator(".bde-apply").click();
		await page.locator(".modal .btn-primary:visible").click();
		await page.waitForTimeout(1000);
		const clearedImage = benchExecute("bimap_data_engine.tests.e2e_fixture.get_image", { name: fixture.name });
		await page.locator(".bde-table").selectOption("barcodes");
		await page.locator(".bde-parent-name").fill(fixture.name);
		await page.locator(".bde-load-child").click();
		await page.waitForFunction(
			() => document.querySelector(".bde-status")?.textContent.includes("filas hijas cargadas"),
			null,
			{ timeout: 30000 },
		);
		await page.evaluate(() => {
			window.BimapDataEnginePage.setValue(0, "barcode", "E2E-EDITED-BARCODE");
			window.BimapDataEnginePage.setValue(2, "barcode", "E2E-NEW-BARCODE");
		});
		await page.locator(".bde-preview").click();
		await page.waitForFunction(() => !document.querySelector(".bde-apply").disabled, null, { timeout: 30000 });
		await page.locator(".bde-apply").click();
		await page.locator(".modal .btn-primary:visible").click();
		await page.waitForTimeout(1000);
		const barcodes = benchExecute("bimap_data_engine.tests.e2e_fixture.get_barcodes", { name: fixture.name });
		const checks = {
			httpOk: response?.status() === 200,
			spanishCatalogSelectorsPresent: await page.locator(".bde-area").count() === 1
				&& await page.locator('.bde-document option:checked').textContent() === "Artículos",
			compactFieldPickerPresent: await page.locator(".bde-field-picker .bde-field-choice").count() > 5,
			existingPriceListsPresent: priceListChoices >= 1,
			priceListFilterProtected: filteredPriceListPrepared,
			priceListFixedFilterVisible: priceListFixedChip,
			priceListFieldsAreDynamic: priceListFilterFields.includes("item_code")
				&& priceListFilterFields.includes("price_list_rate") && !priceListFilterFields.includes("price_list"),
			dynamicFilterBuilderPresent: await page.locator(".bde-filter-row").count() === 1,
			pageMounted: await page.locator(".bde-grid canvas").count() > 0,
			changePersisted: description === "E2E updated",
			explicitClearPersisted: !clearedImage,
			jobResumeControlsPresent: await page.locator(".bde-resume-job").count() === 1,
			childUpdatePersisted: barcodes.includes("E2E-EDITED-BARCODE"),
			childAddPersisted: barcodes.includes("E2E-NEW-BARCODE"),
			unselectedChildPreserved: barcodes.includes(fixture.barcodes[1]),
			noPageErrors: errors.length === 0,
		};
		const report = { status: Object.values(checks).every(Boolean) ? "passed" : "failed", checks, errors };
		console.log(JSON.stringify(report, null, 2));
		if (report.status !== "passed") process.exitCode = 1;
	} finally {
		if (browser) await browser.close();
		benchExecute("bimap_data_engine.tests.e2e_fixture.delete_item", { name: fixture.name });
	}
})().catch((error) => {
	console.error(error.stack || String(error));
	process.exitCode = 1;
});
