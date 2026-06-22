const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const page = await browser.newPage();

  const filePath = path.resolve(__dirname, 'architecture-functional.html');
  await page.goto('file:///' + filePath.replace(/\\/g, '/'), { waitUntil: 'networkidle0' });

  // Give fonts / emoji a moment to render
  await new Promise(r => setTimeout(r, 1200));

  await page.setViewport({ width: 1900, height: 1300, deviceScaleFactor: 2 });

  const bodyHandle = await page.$('body');
  const { width, height } = await bodyHandle.boundingBox();
  await bodyHandle.dispose();

  await page.screenshot({
    path: path.resolve(__dirname, 'architecture-functional.png'),
    clip: { x: 0, y: 0, width: Math.ceil(width), height: Math.ceil(height) },
  });

  await browser.close();
  console.log('Done → architecture-functional.png');
})();
