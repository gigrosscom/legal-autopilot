// QA: скриншоты konsilier.com по ширинам и темам. Запуск: node qa-reports/tools/browser-run.mjs <out-dir>
// Доверяет только CA прокси среды (SPKI из /root/.ccr/agent-proxy-ca.crt); проверка TLS не отключается.
import { chromium, devices } from 'playwright';
import { execSync } from 'child_process';
import fs from 'fs';
// Запуск: node qa-reports/tools/browser-run.mjs <out-dir> [token] [caseId]
// Без token — страницы без входа. С token (+caseId) — авторизованные экраны: /cases, /account, /case/{id}.
const out = process.argv[2] || 'qa-reports/shots';
const TOKEN = process.argv[3] || '';
const CASEID = process.argv[4] || '';
fs.mkdirSync(out, { recursive: true });
const spki = execSync("openssl x509 -in /root/.ccr/agent-proxy-ca.crt -pubkey -noout | openssl pkey -pubin -outform der | openssl dgst -sha256 -binary | base64").toString().trim();
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', proxy: { server: process.env.HTTPS_PROXY }, args: ['--ignore-certificate-errors-spki-list=' + spki] });
const IOS_CHROME = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.7339.101 Mobile/15E148 Safari/604.1';
const widths = [[390, 844, true], [360, 780, true], [768, 1024, true], [1440, 900, false]];
const pages = TOKEN
  ? ['/cases', '/account', CASEID ? `/case/${CASEID}` : '/documents', '/documents']
  : ['/', '/start', '/account?signin=1', '/app', '/ops', '/terms', '/documents', '/nonexistent-qa'];
const res = [];
for (const scheme of ['light', 'dark']) for (const [w, h, mobile] of widths) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 2,
    userAgent: mobile ? IOS_CHROME : undefined, colorScheme: scheme, locale: 'ru-RU' });
  if (TOKEN) { // предзагрузить токен в localStorage, чтобы экраны открылись авторизованно
    const seed = await ctx.newPage();
    try { await seed.goto('https://konsilier.com/offline', { waitUntil: 'domcontentloaded', timeout: 20000 }); } catch {}
    await ctx.addInitScript(t => { try { localStorage.setItem('konsilier.token', t); } catch {} }, TOKEN);
    await seed.close();
  }
  for (const p of pages) {
    const page = await ctx.newPage(); const errs = [];
    page.on('console', m => m.type() === 'error' && errs.push(m.text().slice(0, 200)));
    page.on('pageerror', e => errs.push('PAGEERROR ' + e.message.slice(0, 200)));
    let status = 0; try { status = (await page.goto('https://konsilier.com' + p, { waitUntil: 'networkidle', timeout: 30000 }))?.status(); } catch (e) { errs.push('GOTO ' + e.message.slice(0, 120)); }
    await page.waitForTimeout(1500);
    const info = await page.evaluate(() => {
      const t = document.body.innerText;
      const btns = [...document.querySelectorAll('button, a[role=button]')].filter(b => b.offsetParent).map(b => { const s = getComputedStyle(b); return { t: b.innerText.trim().slice(0, 30), f: s.fontFamily.split(',')[0], fs: s.fontSize, h: Math.round(b.getBoundingClientRect().height), r: s.borderRadius, disabled: b.disabled === true || b.getAttribute('aria-disabled') === 'true' }; });
      const small = btns.filter(b => b.h && b.h < 44 && b.t).length;
      // нижнее меню (fixed/sticky у низа) и «белая полоса» под ним
      const nav = document.querySelector('nav, [class*=bottomnav], [class*=bottom-nav], [class*=tabbar], footer');
      let bottomGap = null, navFixed = false;
      if (nav) { const r = nav.getBoundingClientRect(); const cs = getComputedStyle(nav); navFixed = (cs.position === 'fixed' || cs.position === 'sticky'); bottomGap = Math.round(innerHeight - r.bottom); }
      return { overflow: document.documentElement.scrollWidth > innerWidth + 1, bad: ['undefined', 'NaN', 'Lorem', '[object'].filter(x => t.includes(x)), header: (document.querySelector('header')?.innerText || '').replace(/\s+/g, ' ').slice(0, 120), btns: btns.slice(0, 30), small, navFixed, bottomGap, pay: /Оплатить|Оплата|Счёт/.test(t) };
    });
    const name = `${scheme}-${w}${p.replace(/[\/?=]/g, '_') || '_home'}.png`;
    await page.screenshot({ path: `${out}/${name}`, fullPage: false }); // вьюпорт — видно нижнее меню и полосу
    res.push({ scheme, w, p, status, ...info, errs: [...new Set(errs)], shot: name });
    console.log(scheme, w, p, status, info.overflow ? 'OVERFLOW' : '', info.bad.join(','), 'navGap:' + info.bottomGap, errs.length ? 'errs:' + errs.length : '', 'hdr:', info.header.slice(0, 40));
    await page.close();
  }
  await ctx.close();
}
await browser.close();
fs.writeFileSync(`${out}/results.json`, JSON.stringify(res, null, 1));
