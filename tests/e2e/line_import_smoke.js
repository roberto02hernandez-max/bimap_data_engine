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
	const session = benchExecute("bimap_core.api.testing.create_playwright_session", { user: "Administrator" });
	const browser = await chromium.launch({
		headless: true,
		args: [`--host-resolver-rules=MAP ${SITE} 127.0.0.1`],
	});
	try {
		const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
		await context.addCookies([
			{ name: "sid", value: session.sid, domain: SITE, path: "/", httpOnly: true },
			{ name: "full_name", value: session.full_name, domain: SITE, path: "/" },
			{ name: "user_id", value: session.user, domain: SITE, path: "/" },
			{ name: "system_user", value: "yes", domain: SITE, path: "/" },
		]);
		const page = await context.newPage();
		const pageErrors = [];
		page.on("pageerror", (error) => pageErrors.push(String(error)));
		const response = await page.goto(`${BASE}/app/document-sales-order-lab`, {
			waitUntil: "networkidle",
			timeout: 60000,
		});
		const importButton = page.locator('[data-grid-action="import-spreadsheet"]');
		await importButton.waitFor({ state: "visible", timeout: 30000 });
		// The screen keeps the action disabled until capture mode has a confirmed
		// customer. Exercise the same public contract without manufacturing master data.
		await page.evaluate(() => window.BimapDataEngineLineImport.open({
			documentType: "Sales Order",
			ensureLineImportEditable: () => true,
			getLineImportPayload: () => ({ items: [] }),
			applyPreparedLines: () => true,
		}));
		await page.getByText("Importar partidas desde Excel", { exact: true }).waitFor({ timeout: 30000 });
		const checks = {
			httpOk: response?.status() === 200,
			integrationLoaded: await page.evaluate(() => Boolean(
				window.BimapDataEngineLineImport?.open
				&& window.BimapDataEngineIntegration?.prepareDocumentLines
			)),
			buttonVisible: await importButton.isVisible(),
			modalVisible: await page.locator(".bde-line-import").isVisible(),
			fileActionVisible: await page.locator(".bde-line-file").isVisible(),
			noPageErrors: pageErrors.length === 0,
		};
		const report = {
			status: Object.values(checks).every(Boolean) ? "passed" : "failed",
			checks,
			pageErrors,
		};
		console.log(JSON.stringify(report, null, 2));
		if (report.status !== "passed") process.exitCode = 1;
	} finally {
		await browser.close();
	}
})().catch((error) => {
	console.error(error.stack || String(error));
	process.exitCode = 1;
});
