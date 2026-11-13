const endpoint = process.env.CDP_URL || 'http://localhost:29229';
const register = 'https://www.planning.vic.gov.au/planning-approvals/ministerial-permits-register';
const tabs = await (await fetch(endpoint + '/json/list')).json();
let tab = tabs.find(t => t.type === 'page' && t.url.startsWith(register));
const created = !tab;
if (!tab) tab = await (await fetch(endpoint + '/json/new?' + encodeURIComponent(register), {method:'PUT'})).json();
const socket = new WebSocket(tab.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {socket.onopen = resolve; socket.onerror = reject;});
let seq = 0;
const calls = new Map();
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (calls.has(message.id)) {
    calls.get(message.id)(message);
    calls.delete(message.id);
  }
};
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => {calls.delete(id); reject(new Error('CDP timeout: ' + method));}, 45000);
    calls.set(id, message => {
      clearTimeout(timer);
      if (message.error || message.result?.exceptionDetails) reject(new Error(JSON.stringify(message.error || message.result.exceptionDetails)));
      else resolve(message.result);
    });
    socket.send(JSON.stringify({id, method, params}));
  });
}
try {
  if (created) {
    await call('Page.enable');
    const loaded = new Promise((resolve, reject) => {
      const listener = event => {
        if (JSON.parse(event.data).method === 'Page.loadEventFired') {
          clearTimeout(timer);
          socket.removeEventListener('message', listener);
          resolve();
        }
      };
      const timer = setTimeout(() => {socket.removeEventListener('message', listener); reject(new Error('Register load timed out'));}, 45000);
      socket.addEventListener('message', listener);
    });
    await call('Page.navigate', {url:register});
    await loaded;
  }
  const results = [];
  const seen = new Set();
  let expected;
  for (let start = 1; start <= 100001; start += 1000) {
    const url = new URL('https://dotappg-search.funnelback.squiz.cloud/s/search.json');
    url.search = new URLSearchParams({collection:'dotappg~sp-planning-ministerial-permits', profile:'_default',
      query:'!showall', meta_applicationType_not:'"Application to Correct Planning Permit"', num_ranks:'1000',
      start_rank:String(start), sort:'dmetaapplicationReceivedDate'});
    const expression = `(async()=>{const r=await fetch(${JSON.stringify(String(url))});if(!r.ok)throw new Error('Ministerial HTTP '+r.status);return await r.json();})()`;
    const evaluated = await call('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
    const packet = evaluated.result?.value?.response?.resultPacket;
    const summary = packet?.resultsSummary;
    if (!Array.isArray(packet?.results) || !Number.isInteger(summary?.totalMatching)) throw new Error('Invalid ministerial response');
    expected ??= summary.totalMatching;
    if (summary.totalMatching !== expected) throw new Error('Ministerial index changed during export; retry');
    for (const row of packet.results) {
      if (!row.liveUrl || seen.has(row.liveUrl)) throw new Error('Ministerial pagination repeated a record');
      seen.add(row.liveUrl);
      results.push({liveUrl:row.liveUrl, listMetadata:row.listMetadata});
    }
    if (results.length === expected) break;
    if (!packet.results.length || start + packet.results.length <= summary.currStart) throw new Error('Ministerial export stalled');
  }
  if (results.length !== expected) throw new Error('Incomplete ministerial export');
  process.stdout.write(JSON.stringify(results));
} finally {
  socket.close();
  if (created) await fetch(endpoint + '/json/close/' + tab.id);
}
