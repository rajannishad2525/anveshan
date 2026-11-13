const { chromium } = require('C:/Users/abcom/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:"C:/Program Files/Google/Chrome/Application/chrome.exe"});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765/'); await page.locator('#clusterNav').click();
 await page.waitForFunction(()=>document.querySelector('#clusterList')?.textContent.includes('duplicate copies hidden'),{},{timeout:60000});
 console.log((await page.locator('#clusterList').innerText()).slice(0,900));
 await page.locator('.cluster-open').first().click();await page.waitForFunction(()=>document.querySelector('#clusterModalGrid img')?.naturalWidth>0);
 console.log('modalImages',await page.locator('#clusterModalGrid img').count(),'jsErrors',errors);
 await page.screenshot({path:'datasets/cluster-ui-check.png'});await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
