const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const web = path.join(__dirname, '../web/public');
const source = fs.readFileSync(path.join(web, 'app.js'), 'utf8');
const deadlinesSource = source.match(/const LOCK_DEADLINES = \[[\s\S]*?\];/)[0];
const countdownSource = source.match(/function startCountdown\(\) \{[\s\S]*?\r?\n\}\r?\n/)[0];
// Official qualifying schedules checked 23 October 2026:
// formula1.com/en/racing/2026/{united-states,mexico,brazil,las-vegas,qatar,united-arab-emirates}
const expected = [
  [20, '2026-10-24T21:00:00Z'], [21, '2026-10-31T21:00:00Z'],
  [22, '2026-11-07T18:00:00Z'], [23, '2026-11-21T04:00:00Z'],
  [24, '2026-11-28T18:00:00Z'], [25, '2026-12-05T14:00:00Z'],
];
const context = vm.createContext({});
vm.runInContext(deadlinesSource + ';globalThis.deadlines = LOCK_DEADLINES;', context);
for (const [round, lock] of expected) {
  const actual = context.deadlines.find(row => row.round === round);
  assert.equal(actual.lock, lock, `R${round} must match the official qualifying start`);
  assert.equal(actual.sprint, false, `R${round} is a normal weekend`);
}
function countdownAt(now) {
  const elements = {};
  const FakeDate = class extends Date { constructor(value) { super(value === undefined ? now : value); } };
  const sandbox = vm.createContext({
    Date: FakeDate, RACE_FLAGS: {}, setInterval() {},
    document: { getElementById(id) {
      return elements[id] ||= { style: {}, textContent: '', classList: { toggle() {} } };
    } },
  });
  vm.runInContext(deadlinesSource + countdownSource + ';startCountdown();', sandbox);
  return elements;
}
// The old Friday timestamp incorrectly advanced the site to Mexico before FP3/qualifying.
assert.match(countdownAt('2026-10-23T22:00:00Z').countdownRace.textContent, /R20/);
assert.equal(countdownAt('2026-10-23T22:00:00Z').countdownTimer.textContent, '23h 0m 0s');
assert.match(countdownAt('2026-10-24T20:59:59Z').countdownRace.textContent, /R20/);
assert.match(countdownAt('2026-10-24T21:00:00Z').countdownRace.textContent, /R21/);
assert.equal(new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Africa/Johannesburg', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
}).format(new Date(expected[0][1])), '23:00');
const deadlinePage = fs.readFileSync(path.join(web, 'tools/f1-fantasy-deadline/index.html'), 'utf8');
assert.match(deadlinePage, /October 24, 2026 21:00 UTC/);
assert.doesNotMatch(deadlinePage, /October 23, 2026 21:30 UTC/);
const austinPage = fs.readFileSync(path.join(web, 'picks/united-states-gp-2026/index.html'), 'utf8');
assert.match(austinPage, /Team lock:<\/strong> October 24, 2026 21:00 UTC/);
console.log('PASS: official remaining-round deadlines, Austin countdown rollover, local time and static pages.');
