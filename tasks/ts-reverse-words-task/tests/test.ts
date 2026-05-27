// @ts-ignore
const { reverseWords } = require('../solution/index');

function runTests() {
  const assert = require('assert');
  assert.strictEqual(reverseWords('  hello   world  '), 'world hello');
  assert.strictEqual(reverseWords('a good   example'), 'example good a');
  assert.strictEqual(reverseWords(''), '');
  assert.strictEqual(reverseWords('    '), '');
  assert.strictEqual(reverseWords('one'), 'one');
  console.log('All tests passed');
}

try {
  runTests();
  process.exit(0);
} catch (err: any) {
  console.error('Test failed:', err && err.message ? err.message : err);
  process.exit(1);
}
