const { execFileSync } = require("node:child_process");
const { chromium } = require("playwright");

const ROOT = "/home/afficent/frappe-bench";
const SITE = "mi-sitio.local";
const BASE = `http://${SITE}:${process.env.BDE_E2E_PORT || "8000"}`;

function benchExecute(method, kwargs = {}) {
	const output = execFileSync(
		"bench", ["--site", SITE, "execute", method, "--kwargs", JSON.stringify(kwargs)],
		{ cwd: ROOT, encoding: "utf8" },
	);
	const line = output.trim().split("\n").reverse().find((candidate) => candidate.trim());
	try { return JSON.parse(line); } catch (_error) { return line; }
}

(async () => {
	const fixture = benchExecute("bimap_data_engine.tests.e2e_fixture.create_cfdi_import_file");
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
		page.on("pageerror", (error) => errors.push(String(error)));
		page.on("response", (response) => {
			if (response.status() >= 400 && !response.url().includes("socket.io")) errors.push(`HTTP ${response.status()}: ${response.url()}`);
		});
		const response = await page.goto(`${BASE}/app/bimap-data-import`, { waitUntil: "networkidle", timeout: 60000 });
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().schema === "Item", null, { timeout: 30000 });
		await page.evaluate((fileUrl) => window.BimapDataImportPage.loadFileUrl(fileUrl), fixture.file_url);
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().schema === "Purchase Invoice"
			&& window.BimapDataImportPage?.getState().adapterReady, null, { timeout: 60000 });
		await page.locator(".bdi-defaults").fill(JSON.stringify({ company: fixture.company, supplier: fixture.supplier }));
		await page.locator(".bdi-cfdi-preview").click();
		await page.waitForFunction(() => window.BimapDataImportPage?.getState().plan?.valid === true, null, { timeout: 30000 });
		const plan = await page.evaluate(() => window.BimapDataImportPage.getState().plan);
		const checks = {
			httpOk: response?.status() === 200,
			cfdiActionVisible: await page.locator(".bdi-cfdi-preview").isVisible(),
			createEnabled: await page.locator(".bdi-cfdi-create").isEnabled(),
			lifecycleLockedToDraft: await page.locator(".bdi-lifecycle").isDisabled()
				&& await page.locator(".bdi-lifecycle").inputValue() === "draft",
			previewValid: plan.valid === true && plan.records[0]?.bimap_cfdi_uuid === fixture.uuid,
			noPageErrors: errors.length === 0,
		};
		const report = { status: Object.values(checks).every(Boolean) ? "passed" : "failed", checks, errors };
		console.log(JSON.stringify(report, null, 2));
		if (report.status !== "passed") process.exitCode = 1;
	} finally {
		if (browser) await browser.close();
		benchExecute("bimap_data_engine.tests.e2e_fixture.delete_cfdi_import_fixture", {
			item_code: fixture.item_code, supplier: fixture.supplier,
			file_name: fixture.file_name, cfdi_uuid: fixture.uuid,
		});
	}
})().catch((error) => {
	console.error(error.stack || String(error));
	process.exitCode = 1;
});
