const {chromium}=require(process.env.PLAYWRIGHT_MODULE || '/Users/mac/Downloads/jcode-lite-macos-x64-latest/preset/mcp/node_modules/playwright');
const fs=require('fs');
const assert=require('node:assert/strict');
const origin=process.env.PREVIEW_URL || 'http://127.0.0.1:4173';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH || '/Users/mac/Library/Caches/ms-playwright/chromium-1217/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'});
 const page=await browser.newPage();
 const errors=[];
 page.on('pageerror',err=>errors.push(err.message));
 fs.mkdirSync('qa/screenshots',{recursive:true});
 const results=[];
 for(const width of [320,375,768,1440]){
   await page.setViewportSize({width,height:width>1000?1000:812});
   const response=await page.goto(origin,{waitUntil:'networkidle'});
   assert.equal(response.status(),200);
   await page.evaluate(()=>document.fonts.ready);
   const layout=await page.evaluate(()=>({
     overflow:document.documentElement.scrollWidth>innerWidth,
     columns:getComputedStyle(document.querySelector('.room-grid')).gridTemplateColumns.split(' ').length,
     cards:document.querySelectorAll('.room-card').length,
     language:document.documentElement.lang,
     leaflet:!!window.L,
     markers:document.querySelectorAll('.price-marker').length
   }));
   assert.equal(layout.overflow,false,`Overflow at ${width}`);
   assert.equal(layout.columns,width>=1050?4:2);
   assert.equal(layout.cards,3);
   assert.equal(layout.language,'en');
   assert.equal(layout.leaflet,true);
   assert.equal(layout.markers,0);
   await page.screenshot({path:`qa/screenshots/home-${width}.png`,fullPage:true});
   results.push({width,...layout});
 }
 await page.locator('.languages a[lang="uk"]').click();
 assert.equal(await page.locator('html').getAttribute('lang'),'uk');
 assert.equal(await page.locator('.room-card').count(),3);
 await page.locator('.room-card h3 a').first().click();
 assert.match(page.url(),/\/uk\/rooms\/roma-areeiro-600\/$/);
 const ukMessage=new URL(await page.locator('.inquiry .button').getAttribute('href')).searchParams.get('text');
 assert.match(ukMessage,/Привіт/);assert.match(ukMessage,/600/);assert.match(ukMessage,/Roma-Areeiro/);
 await page.locator('.languages a[lang="pt"]').click();
 assert.match(page.url(),/\/pt\/rooms\/roma-areeiro-600\/$/);
 const ptMessage=new URL(await page.locator('.inquiry .button').getAttribute('href')).searchParams.get('text');
 assert.match(ptMessage,/Olá/);
 await page.locator('.back-link').click();
 assert.match(page.url(),/\/pt\/$/);
 for(const lang of ['','uk/','pt/'])for(const id of ['roma-areeiro-600','roma-areeiro-750','roma-areeiro-650']){
   const response=await page.goto(`${origin}/${lang}rooms/${id}/`,{waitUntil:'domcontentloaded'});
   assert.equal(response.status(),200);
   const meta=await page.locator('meta[property="og:title"]').getAttribute('content');assert.ok(meta.includes('Rumbon'));
   const image=await page.locator('meta[property="og:image"]').getAttribute('content');
   assert.equal((await page.request.get(image.replace(/^https?:\/\/[^/]+/,origin))).status(),200);
 }
 await page.setViewportSize({width:375,height:812});
 await page.goto(`${origin}/uk/rooms/roma-areeiro-750/`,{waitUntil:'networkidle'});
 await page.screenshot({path:'qa/screenshots/room-mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);
 fs.writeFileSync('qa/browser-results.json',JSON.stringify({results,languageSwitch:true,deepLinks:9,whatsapp:true,errors},null,2));
 console.log(JSON.stringify({results,languageSwitch:true,deepLinks:9,whatsapp:true,errors},null,2));
 await browser.close();
})().catch(err=>{console.error(err);process.exit(1)});
