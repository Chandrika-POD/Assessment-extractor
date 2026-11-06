// Optional browser QA using Playwright already installed in the sibling app.
let chromium;
try { ({ chromium } = require('playwright')); }
catch {
  try { ({ chromium } = require('../../assessment-database/node_modules/playwright')); }
  catch { ({ chromium } = require(require('node:path').join(require('node:os').homedir(), 'POD/assessment-database/node_modules/playwright'))); }
}
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const artifacts = path.resolve(__dirname, '../artifacts');
  await fs.mkdir(artifacts, { recursive: true });
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_EXECUTABLE || undefined });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1120 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(process.env.BASE_URL || 'http://127.0.0.1:4177');
    await page.screenshot({ path: path.join(artifacts, 'dashboard.png'), fullPage: true });
    await page.locator('#try-example').click();
    await page.getByText('Partial coverage · review ready', { exact: true }).waitFor();
    const frame = page.frameLocator('#document-frame');
    await frame.getByRole('heading', { name: 'Questionnaire · 7 structured items' }).waitFor();
    assert.equal(await frame.locator('.question').count(), 7);
    assert.equal(await frame.locator('.options li').count(), 28);
    await frame.getByText('Feeling nervous, anxious or on edge', { exact: false }).waitFor();
    await page.screenshot({ path: path.join(artifacts, 'gad7-preview.png'), fullPage: true });
    await page.getByRole('button', { name: 'Questions', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#document-frame').contentWindow.scrollY > 600);
    await page.waitForTimeout(600);
    await page.screenshot({ path: path.join(artifacts, 'gad7-questions.png'), fullPage: true });
    await page.getByRole('tab', { name: 'JSON', exact: true }).click();
    assert.match(await page.locator('#json-pane').textContent(), /retained_publisher_source/);
    await page.getByRole('tab', { name: 'Document', exact: true }).click();
    let pending = page.waitForEvent('download');
    await page.getByRole('button', { name: '↓ Document', exact: true }).click();
    await (await pending).saveAs(path.join(artifacts, 'GAD-7.html'));
    pending = page.waitForEvent('download');
    await page.getByRole('button', { name: '↓ JSON', exact: true }).click();
    await (await pending).saveAs(path.join(artifacts, 'GAD-7.json'));
    const data = JSON.parse(await fs.readFile(path.join(artifacts, 'GAD-7.json'), 'utf8'));
    assert.equal(data.questionnaire.length, 7);
    const doc = await browser.newPage();
    await doc.setContent(await fs.readFile(path.join(artifacts, 'GAD-7.html'), 'utf8'));
    await doc.pdf({ path: path.join(artifacts, 'GAD-7.pdf'), format: 'A4', printBackground: true, margin: { top: '18mm', right: '16mm', bottom: '18mm', left: '16mm' } });
    await doc.close();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    await page.screenshot({ path: path.join(artifacts, 'mobile.png'), fullPage: true });
    await page.locator('#mode').selectOption('live');
    await page.locator('#url').fill('https://127.0.0.1/admin');
    await page.getByRole('button', { name: 'Create assessment document' }).click();
    await page.getByRole('alert').filter({ hasText: 'public HTTPS' }).waitFor();
    if (process.env.TEST_LIVE === '1') {
      await page.setViewportSize({ width: 1440, height: 1120 });
      await page.locator('#url').fill('https://novopsych.com/assessments/anxiety/generalised-anxiety-disorder-assessment-gad-7/');
      await page.getByRole('button', { name: 'Create assessment document' }).click();
      await frame.getByRole('heading', { name: 'Questionnaire · 7 structured items' }).waitFor({ timeout: 360000 });
      assert.equal(await frame.locator('.options li').count(), 28);
      assert.equal(await page.locator('#result-label').textContent(), 'LIVE SOURCE EXTRACTION');
      await page.screenshot({ path: path.join(artifacts, 'live-preview.png'), fullPage: true });
      for (const [button, filename] of [['#download-html', 'GAD-7-novopsych-live.html'], ['#download-json', 'GAD-7-novopsych-live.json']]) {
        const download = page.waitForEvent('download');
        await page.locator(button).click();
        await (await download).saveAs(path.join(artifacts, filename));
      }
      const live = JSON.parse(await fs.readFile(path.join(artifacts, 'GAD-7-novopsych-live.json'), 'utf8'));
      assert.equal(live.mode, 'live_source');
      assert.ok(live.sources.length >= 2);
      assert.ok(live.scoring.length > 0);
      assert.equal(live.questionnaire.length, 7);
      assert.equal(live.browser.tabs.filter(t => t.status === 'captured').length, 4);
      const printable = await browser.newPage();
      await printable.setContent(await fs.readFile(path.join(artifacts, 'GAD-7-novopsych-live.html'), 'utf8'));
      await printable.pdf({ path: path.join(artifacts, 'GAD-7-novopsych-live.pdf'), format: 'A4', printBackground: true });
      await printable.close();
      console.log('PASS: live NovoPsych GAD-7, four tabs, seven questions / 28 choices, scoring text, HTML/JSON/PDF artifacts.');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: saved preview, navigation, JSON tab, downloads, PDF export, mobile layout, URL rejection, no browser errors.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
