import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

vm.runInThisContext(fs.readFileSync(new URL("../logic.js", import.meta.url), "utf8"));

const K = {no:1, price_final:null, price_band:[19000,23000], min_shares:null, margin_rate:0.5,
           sub_start:"2026-11-27", sub_end:"2026-11-30", listing:"2026-12-08"};
assert.deepEqual(minAmount(K), {amount:95000, shares:10, estimated:true});
assert.deepEqual(minAmount({...K, price_final:17600}), {amount:88000, shares:10, estimated:false});
assert.deepEqual(minAmount({...K, price_final:2000, margin_rate:1}), {amount:20000, shares:10, estimated:false}); // 스팩 100%
assert.equal(minAmount({...K, min_shares:20}).amount, 190000);
assert.equal(minAmount({...K, price_band:null}).amount, null);

assert.equal(eventsOn([K], "2026-11-30")[0].kind, "sub");
assert.equal(eventsOn([K], "2026-11-27")[0].kind, "sub");
assert.equal(eventsOn([K], "2026-12-08")[0].kind, "listing");
assert.equal(eventsOn([K], "2026-12-01").length, 0);
assert.equal(eventsOn([K], "2026-11-29").length, 0);   // 청약 기간 중 주말(일)은 표시 안 함
assert.equal(eventsOn([{...K, listing:null}], "2026-12-08").length, 0);

const g = monthGrid(2026, 11);
assert.equal(g.length, 42); assert.equal(g[0], "2026-10-26"); assert.ok(g.includes("2026-11-30"));
const j = monthGrid(2027, 1); assert.equal(j[0], "2026-12-28"); // 연도 넘김

assert.deepEqual(weekItems([K], "2026-11-30").sub.map(i => i.no), [1]);   // 11/30(월) 주에 걸침
assert.deepEqual(weekItems([K], "2026-12-07").sub.map(i => i.no), []);    // 12/7~12/13 주에는 없음
assert.deepEqual(weekItems([K], "2026-12-09").listing.map(i => i.no), [1]);
const L = {...K, no:2, sub_start:"2026-11-23", sub_end:"2026-11-24"};
assert.deepEqual(weekItems([K, L], "2026-11-25").sub.map(i => i.no), [2, 1]);  // 날짜순

// 공휴일: 추석(2027-09-14~16)에 걸친 청약은 그날 띠를 그리지 않는다
const C = {...K, no:3, sub_start:"2027-09-13", sub_end:"2027-09-17", listing:null};
assert.equal(eventsOn([C], "2027-09-13").length, 1);
assert.equal(eventsOn([C], "2027-09-15").length, 0);
assert.equal(eventsOn([C], "2027-09-17").length, 1);
assert.equal(isBizDay("2026-12-25"), false);
assert.equal(isBizDay("2026-12-24"), true);
// 일요일엔 "이번 주"가 다음 주(월~일)
assert.deepEqual(weekItems([K], "2026-11-29").sub.map(i => i.no), [1]);   // 11/29(일) → 11/30 주
assert.deepEqual(weekItems([L], "2026-11-29").sub.map(i => i.no), []);    // 지난 주(11/23~24) 청약은 빠짐
assert.deepEqual(weekItems([L], "2026-11-28").sub.map(i => i.no), [2]);   // 토요일은 그대로 그 주

assert.deepEqual(RECORD_STATES, ["subscribed", "holding", "sold"]);
assert.throws(() => parseRecords('{"1":{"state":"bought"}}'));
assert.throws(() => parseRecords("not json"));
assert.throws(() => parseRecords('{"a":1}'));
assert.throws(() => parseRecords('[1]'));
assert.throws(() => parseRecords('{"1":{"state":"sold","shares":1.5,"profit":null}}'));
assert.deepEqual(parseRecords('{"1":{"state":"sold","shares":2,"profit":15000}}'), {"1":{state:"sold",shares:2,profit:15000}});
assert.deepEqual(parseRecords('{"7":{"state":"subscribed","shares":null,"profit":-3000}}'), {"7":{state:"subscribed",shares:null,profit:-3000}});
assert.throws(() => parseRecords('{"1":{"state":"holding","shares":-3,"profit":null}}'));  // 배정 수량은 0 이상
assert.throws(() => parseRecords("not json"), /JSON 파일이 아닙니다/);                   // 한국어 안내
assert.equal(isPick({inst_rate:800}), true);
assert.equal(isPick({inst_rate:799.9}), false);
assert.equal(isPick({inst_rate:null}), false);
console.log("ok");
