/**
 * List all available chapters from the TCB Scans manga index page.
 * Outputs a JSON file with chapter numbers, titles, and URLs.
 *
 * Usage: node list_chapters.js [start_chapter] [end_chapter] > chapters.json
 */

const CDP = require('chrome-remote-interface');

const startCh = parseInt(process.argv[2]) || 0;
const endCh = parseInt(process.argv[3]) || 9999;

(async () => {
  const client = await CDP();
  const { Page, Runtime } = client;
  await Page.enable();

  await Page.navigate({ url: 'https://tcbonepiecechapters.com/mangas/5/one-piece' });
  await Page.loadEventFired();
  await new Promise(r => setTimeout(r, 3000));

  const { result } = await Runtime.evaluate({
    expression: `JSON.stringify(
      Array.from(document.querySelectorAll('a'))
        .filter(a => a.href && a.href.includes('/chapters/'))
        .map(a => ({
          title: a.innerText.trim(),
          href: a.href
        }))
    )`
  });

  const allLinks = JSON.parse(result.value);
  const chapters = allLinks
    .filter(c => {
      const match = c.title.match(/Chapter (\d+)/);
      return match;
    })
    .map(c => {
      const num = parseInt(c.title.match(/Chapter (\d+)/)[1]);
      const name = c.title.split('\n')[1] || '';
      return { chapter: num, title: name.trim(), url: c.href };
    })
    .filter(c => c.chapter >= startCh && c.chapter <= endCh)
    .sort((a, b) => a.chapter - b.chapter);

  console.log(JSON.stringify(chapters, null, 2));
  console.error(`Found ${chapters.length} chapters (${chapters[0]?.chapter}-${chapters[chapters.length-1]?.chapter})`);
  await client.close();
})().catch(e => { console.error(e.message); process.exit(1); });
