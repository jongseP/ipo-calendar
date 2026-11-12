// 화면 규칙(순수 함수). index.html과 tests/test_view.mjs가 같이 쓴다.
// 날짜는 "YYYY-MM-DD" 문자열. 시간대 문제를 피하려고 계산은 UTC 기준으로 한다.
// 38커뮤니케이션의 '최저 : - 주'가 늘 비어 있어 쓰는 기본값. 보통 10주지만 증권사에 따라 20·50주도 있다.
const DEFAULT_MIN_SHARES = 10;
// 평일 공휴일(청약을 안 받는 날). 출처: 한국천문연구원 월력요항 2026·2027 (astro.kasi.re.kr/kor/life/post/calendarData)
// ponytail: 해마다 손으로 추가. 2028년 월력요항이 나오면 이어 붙인다.
const HOLIDAYS = new Set([
  "2026-01-01", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-05", "2026-05-25",
  "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05", "2026-10-09", "2026-12-25",
  "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-01", "2027-05-03", "2027-05-05", "2027-05-13",
  "2027-07-19", "2027-08-16", "2027-09-14", "2027-09-15", "2027-09-16", "2027-10-04", "2027-10-11", "2027-12-27",
]);
const PICK_INST_RATE = 800; // 기관경쟁률이 이 값 이상이면 추천(사용자 기준)
const isPick = ipo => (ipo.inst_rate ?? 0) >= PICK_INST_RATE;
const RECORD_STATES = ["subscribed", "holding", "sold"];
const STATE_LABEL = {subscribed: "청약함", holding: "보유 중", sold: "매도함"};

function isoAdd(iso, days) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function mondayOf(iso) {
  const dow = new Date(iso + "T00:00:00Z").getUTCDay(); // 0=일
  return isoAdd(iso, -((dow + 6) % 7));
}

// 청약을 받는 날(평일이고 공휴일이 아님)
const isBizDay = iso => ![0, 6].includes(new Date(iso + "T00:00:00Z").getUTCDay()) && !HOLIDAYS.has(iso);

// "이번 주"의 월요일. 일요일엔 청약이 없으니 다음 주를 본다.
const weekStart = iso => mondayOf(new Date(iso + "T00:00:00Z").getUTCDay() === 0 ? isoAdd(iso, 1) : iso);

function minAmount(ipo) {
  const price = ipo.price_final ?? (ipo.price_band ? ipo.price_band[0] : null);
  const shares = ipo.min_shares ?? DEFAULT_MIN_SHARES;
  return {
    amount: price == null ? null : Math.round(price * shares * ipo.margin_rate),
    shares,
    estimated: ipo.price_final == null,
  };
}

function eventsOn(ipos, iso) {
  const out = [];
  const biz = isBizDay(iso); // 주말·공휴일엔 청약을 안 받는다
  for (const ipo of ipos) {
    if (biz && ipo.sub_start && ipo.sub_start <= iso && iso <= ipo.sub_end) out.push({ipo, kind: "sub"});
    if (ipo.listing === iso) out.push({ipo, kind: "listing"});
  }
  return out;
}

// 월요일 시작 6주(42칸). month는 1~12
function monthGrid(year, month) {
  const first = `${year}-${String(month).padStart(2, "0")}-01`;
  const start = mondayOf(first);
  return Array.from({length: 42}, (_, i) => isoAdd(start, i));
}

function weekItems(ipos, todayIso) {
  const mon = weekStart(todayIso), sun = isoAdd(mon, 6);
  const sub = ipos.filter(i => i.sub_start && i.sub_start <= sun && i.sub_end >= mon)
    .sort((a, b) => a.sub_start.localeCompare(b.sub_start));
  const listing = ipos.filter(i => i.listing && i.listing >= mon && i.listing <= sun)
    .sort((a, b) => a.listing.localeCompare(b.listing));
  return {sub, listing};
}

// 불러온 기록 검사. 형식이 틀리면 Error를 던져서 기존 기록을 지킨다.
function parseRecords(text) {
  let data;
  try { data = JSON.parse(text); } catch { throw new Error("JSON 파일이 아닙니다"); }
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("기록 형식이 아닙니다");
  const intOrNull = v => v === null || Number.isInteger(v);
  for (const [no, r] of Object.entries(data)) {
    if (!/^\d+$/.test(no) || !r || typeof r !== "object" || !RECORD_STATES.includes(r.state)
        || !intOrNull(r.shares ?? null) || r.shares < 0 || !intOrNull(r.profit ?? null)) {
      throw new Error(`종목 ${no}의 기록이 잘못됐습니다`);
    }
  }
  return data;
}
