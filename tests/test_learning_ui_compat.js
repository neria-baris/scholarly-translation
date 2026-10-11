// Execute the compatibility decision shipped in the UI, without a DOM/provider.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../scholarly_translation/learning.js'), 'utf8');
const start = source.indexOf('function learningUpdateNeeded(');
const end = source.indexOf('// ---- effort ----', start);
const needsUpdate = new Function(source.slice(start, end) + ';return learningUpdateNeeded;')();
const current = {languages: [{id:'fr'}, {id:'ar'}], books: [{chapters:[{title:'Body'}]}]};
assert.equal(needsUpdate(current), false);
assert.equal(needsUpdate({...current, languages:[{id:'fr'}]}), true);
assert.equal(needsUpdate({...current, books:[{}]}), true);
assert.equal(needsUpdate({...current, books:[{chapters:[]}]}), true);
assert.equal(needsUpdate({...current, books:[]}), false);
assert.equal(needsUpdate({...current, books:[current.books[0], {}]}), true);
console.log('6 learning UI compatibility cases passed');
