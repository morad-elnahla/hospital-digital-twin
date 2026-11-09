import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const m = await import(pathToFileURL(resolve(process.argv[2], 'server/index.mjs')).href);
const h = m.default;
const r = await h.fetch(new Request('http://127.0.0.1/'), {ASSETS:{fetch:()=>new Response('',{status:404})}}, {waitUntil(){},passThroughOnException(){}});
console.error(r.status);
process.stdout.write(await r.text());
