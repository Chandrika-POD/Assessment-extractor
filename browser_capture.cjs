// Chromium has no direct source-network access: route fulfillment uses Python's pinned HTTPS.
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = require('../assessment-database/node_modules/playwright')); }
const input = readline.createInterface({ input: process.stdin });
const pending = new Map();
let initialized = false, sequence = 0;
const emit = data => process.stdout.write(JSON.stringify(data) + '\n');
const ask = url => new Promise(resolve => {
  const id = ++sequence; pending.set(id, resolve); emit({ type: 'request', id, url });
});
input.on('line', line => {
  const data = JSON.parse(line);
  if (!initialized) { initialized = true; run(data).catch(e => { emit({ type: 'error', error: e.message }); process.exit(1); }); }
  else { pending.get(data.id)?.(data); pending.delete(data.id); }
});

async function run({url, html}) {
  let executablePath = process.env.CHROMIUM_EXECUTABLE;
  if (!executablePath && !fs.existsSync(chromium.executablePath())) {
    const cache = path.join(require('node:os').homedir(), '.cache/ms-playwright');
    const installed = fs.existsSync(cache) ? fs.readdirSync(cache).filter(n => n.startsWith('chromium_headless_shell-')).sort().reverse() : [];
    for (const dir of installed) {
      const candidate = path.join(cache, dir, 'chrome-headless-shell-linux64/chrome-headless-shell');
      if (fs.existsSync(candidate)) { executablePath = candidate; break; }
    }
  }
  const browser = await chromium.launch({headless: true, executablePath});
  try {
    const context = await browser.newContext({serviceWorkers: 'block', viewport: {width: 1400, height: 1000}, acceptDownloads: false});
    await context.routeWebSocket('**/*', socket => socket.close());
    let initial = true;
    await context.route('**/*', async route => {
      const req = route.request();
      if (initial && req.isNavigationRequest() && req.url() === url) {
        initial = false;
        return route.fulfill({status: 200, contentType: 'text/html; charset=utf-8', body: html});
      }
      if (req.method() !== 'GET' || !['script', 'stylesheet'].includes(req.resourceType()) || new URL(req.url()).origin !== new URL(url).origin)
        return route.abort();
      const result = await ask(req.url());
      if (result.error) return route.abort();
      return route.fulfill({status: 200, contentType: result.contentType, body: Buffer.from(result.body, 'base64')});
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(e.message.slice(0,200)));
    page.setDefaultTimeout(5000);
    await page.goto(url, {waitUntil: 'load', timeout: 190000});
    await page.waitForLoadState('networkidle', {timeout: 20000}).catch(() => {});
    await page.waitForTimeout(1000);
    const selector = '.entry-content, [data-elementor-type="single-post"], [data-elementor-type="wp-post"], main, article, #content';
    const root = (await page.locator(selector).count()) ? page.locator(selector).first() : page.locator('body');
    const snapshots = [], tabs = [];
    async function snapshot(label) {
      const content = await root.evaluate(element => {
        function copy(node) {
          if (node.nodeType === Node.TEXT_NODE) return node.cloneNode();
          if (node.nodeType !== Node.ELEMENT_NODE) return null;
          if (['SCRIPT','STYLE','NAV','FOOTER','HEADER','NOSCRIPT','IFRAME'].includes(node.tagName)) return null;
          if (node.getAttribute('role') === 'tab') return null;
          const style = getComputedStyle(node);
          if (style.display === 'none' || style.visibility === 'hidden' || node.getAttribute('aria-hidden') === 'true') return null;
          const clone = node.cloneNode(false);
          clone.removeAttribute('hidden');
          clone.removeAttribute('style');
          if (node.getAttribute('role') === 'tabpanel') {
            const heading = document.createElement('h2');
            heading.textContent = document.getElementById(node.getAttribute('aria-labelledby'))?.textContent || 'Assessment tab';
            clone.append(heading);
          }
          for (const child of node.childNodes) { const copied = copy(child); if (copied) clone.append(copied); }
          return clone;
        }
        return copy(element)?.outerHTML || '';
      });
      snapshots.push({label, html: content});
    }
    await snapshot('Initial page');
    const controls = root.locator('[role="tab"], .elementor-accordion .elementor-tab-title, details > summary');
    const seen = new Set();
    for (let i = 0; i < Math.min(await controls.count(), 40); i++) {
      const control = controls.nth(i);
      if (!await control.isVisible()) continue;
      const label = (await control.innerText()).trim();
      const target = await control.getAttribute('aria-controls');
      const key = target || label;
      if (seen.has(key)) continue;
      seen.add(key);
      try {
        if (await control.getAttribute('aria-expanded') !== 'true' || await control.getAttribute('role') === 'tab') await control.click();
        await page.waitForTimeout(300);
        if (target) {
          const panel = page.locator(`[id=${JSON.stringify(target)}]`);
          await panel.waitFor({state: 'visible', timeout: 12000});
        }
        await snapshot(label);
        tabs.push({title: label, status: 'captured'});
      } catch (error) { tabs.push({title: label, status: 'unavailable', error: error.message.slice(0,180)}); }
    }
    emit({type: 'complete', result: {snapshots, tabs, title: await page.title(), page_errors: pageErrors}});
  } finally { await browser.close(); input.close(); }
}
