// Runs the website's inline script against spec/routing_cases.json.
// Usage: node tests/site_conformance.js   (prints JSON, exits 0)
const fs = require('fs'), vm = require('vm'), path = require('path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'website', 'index.html'), 'utf8');
const src = html.split('<script>')[1].split('</script>')[0];
const ctx = { module: { exports: {} } };
vm.createContext(ctx); vm.runInContext(src, ctx);
const site = ctx.module.exports;
const spec = JSON.parse(fs.readFileSync(path.join(root, 'spec', 'routing_cases.json'), 'utf8'));
const name = { forest: 'full', canopy: 'canopy', sprout: 'sprout' };
console.log(JSON.stringify({
  routes: spec.cases.map(c => name[site.routeMode(c.prompt)]),
  shrinks: spec.shrink_cases_site_only.map(c => site.shrinkPrompt(c.in)),
}));
