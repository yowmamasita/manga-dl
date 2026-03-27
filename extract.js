/**
 * Extract manga page image URLs from TCB Scans using Chrome DevTools Protocol.
 * Requires Chrome running with --remote-debugging-port=9222
 *
 * Usage: node extract.js <chapters.json> <output.json>
 */

const CDP = require('chrome-remote-interface');
const fs = require('fs');

const chaptersFile = process.argv[2];
const outputFile = process.argv[3];

if (!chaptersFile || !outputFile) {
  console.error('Usage: node extract.js <chapters.json> <output.json>');
  process.exit(1);
}

const chapters = JSON.parse(fs.readFileSync(chaptersFile, 'utf8'));

(async () => {
  const client = await CDP();
  const { Page, Runtime } = client;
  await Page.enable();

  const allChapterImages = [];

  for (const ch of chapters) {
    let correct = false;

    for (let attempt = 1; attempt <= 3 && !correct; attempt++) {
      if (attempt > 1) console.error(`  Retry attempt ${attempt}...`);
      else console.error(`Extracting ch ${ch.chapter}: ${ch.title}`);

      await Page.navigate({ url: ch.url });
      await Page.loadEventFired();
      await new Promise(r => setTimeout(r, 3000));

      const { result } = await Runtime.evaluate({
        expression: `JSON.stringify(
          Array.from(document.querySelectorAll('img.fixed-ratio-content'))
            .map(img => img.src)
        )`
      });

      const images = JSON.parse(result.value);

      // Check for chapter number mismatches in filenames (site caching bug)
      const fileChNums = images.map(url => {
        const fname = url.split('/').pop();
        const match = fname.match(/(\d{4})/);
        return match ? parseInt(match[1]) : null;
      }).filter(n => n && n >= 900 && n <= 1300);

      const hasMismatch = fileChNums.some(n => n !== ch.chapter);

      if (!hasMismatch || fileChNums.length === 0) {
        console.error(`  -> ${images.length} pages OK`);
        allChapterImages.push({
          chapter: ch.chapter,
          title: ch.title,
          images: images
        });
        correct = true;
      } else {
        const wrongCh = fileChNums.find(n => n !== ch.chapter);
        console.error(`  -> WRONG (got ch ${wrongCh}), retrying...`);
        await new Promise(r => setTimeout(r, 2000));
      }
    }

    if (!correct) {
      console.error(`  -> FAILED ch ${ch.chapter} after 3 attempts`);
      allChapterImages.push({
        chapter: ch.chapter,
        title: ch.title,
        images: [],
        status: 'failed'
      });
    }
  }

  fs.writeFileSync(outputFile, JSON.stringify(allChapterImages, null, 2));
  console.error(`\nSaved ${allChapterImages.length} chapters to ${outputFile}`);
  await client.close();
})().catch(e => { console.error(e.message); process.exit(1); });
