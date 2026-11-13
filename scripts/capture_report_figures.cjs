const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = process.argv[2] || 'http://127.0.0.1:60976/';
const outDir = path.resolve(process.argv[3] || 'docs/report_figures');
fs.mkdirSync(outDir, { recursive: true });

const chromeCandidates = [
  process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe'),
  process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft/Edge/Application/msedge.exe'),
  process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe'),
].filter(Boolean);
const executablePath = chromeCandidates.find(fs.existsSync);
if (!executablePath) throw new Error('Chrome or Edge executable was not found');

const ids = [1, 25, 49, 65, 87];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function loadScenes(page, sceneIds) {
  await page.evaluate(async selectedIds => {
    window.compareScenes = await Promise.all(selectedIds.map(async id => {
      const response = await fetch(`/api/scenes/${id}`);
      if (!response.ok) throw new Error(`Scene ${id} is unavailable`);
      return response.json();
    }));
    showWorkspace('compare');
    window.scrollTo(0, 0);
  }, sceneIds);
}

async function capture(page, file) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await delay(700);
  await page.screenshot({ path: path.join(outDir, file), fullPage: true });
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.setDefaultTimeout(120000);
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => typeof showWorkspace === 'function' && document.getElementById('timelineBtn'));

  // Figure 7.7 — one location observed across five supplied periods.
  await loadScenes(page, ids);
  await page.click('#timelineBtn');
  await page.waitForFunction(() => document.querySelectorAll('#timelineView button').length >= 4);
  await capture(page, 'figure-7-7-multitemporal-timeline.png');

  // Figure 7.8 — real registered before/after analysis and candidate evidence.
  await loadScenes(page, [65, 87]);
  await page.click('#compareBtn');
  await page.waitForFunction(() => /pair reports complete/i.test(document.getElementById('compareStatus')?.textContent || ''));
  await page.waitForFunction(() => document.querySelector('.timeline-report .false-alarm-panel'));
  await capture(page, 'figure-7-8-before-after-change-evidence.png');

  // Create one auditable review only when this capture record is absent.
  await page.evaluate(async selectedIds => {
    const note = 'Report evidence capture: multi-temporal candidate retained for analyst review; source imagery and uncertainty require verification.';
    const existing = await fetch('/api/evidence-reviews').then(r => r.json());
    if (!existing.some(record => record.note === note)) {
      const response = await fetch('/api/evidence-reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_ids: selectedIds, decision: 'needs-review', note }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || 'Review could not be saved');
    }
  }, [65, 87]);

  // Figure 7.9 — review queue alternative plus the report/provenance view.
  await page.evaluate(() => showWorkspace('review'));
  await page.click('#rqRefresh');
  await page.waitForFunction(() => /images available/i.test(document.getElementById('rqStatus')?.textContent || ''));
  await capture(page, 'figure-7-9-review-queue.png');

  await page.evaluate(() => showWorkspace('reports'));
  await page.click('#rpRefresh');
  await page.waitForSelector('#rpList .rpRecord');
  await page.locator('#rpList .rpRecord details').first().evaluate(node => { node.open = true; });
  await capture(page, 'figure-7-9-reports-provenance.png');

  await browser.close();
  console.log(JSON.stringify({ outDir, files: fs.readdirSync(outDir).filter(name => name.startsWith('figure-7-')) }, null, 2));
})().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
