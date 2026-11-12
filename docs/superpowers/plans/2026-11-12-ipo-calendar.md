# 공모주 달력 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 38커뮤니케이션 공모주 일정을 자동으로 모아 폰에서 한 달 달력으로 보고, 내 청약·보유·매도 기록을 브라우저에 남기는 개인용 웹페이지.

**Architecture:**
- `fetch_ipos.py`가 GitHub Actions에서 하루 3번 돈다.
  - 38커뮤니케이션 목록과 상세 페이지를 읽는다.
  - 이전 `data/ipos.json`과 비교해 정정과 취소 의심을 표시한 뒤 파일을 갱신하고 커밋한다.
- `index.html`과 `logic.js`는 GitHub Pages 정적 페이지다.
  - `data/ipos.json`을 읽어 그린다.
  - 내 기록은 `localStorage`에만 둔다.
- 구조는 `C:\jongse\ncmh-menu`(식단 사이트)와 같다.

**Tech Stack:**
- Python 3.12 표준 라이브러리만 쓴다(`urllib`, `re`, `json`, `html`).
- 화면은 순수 HTML/CSS/JS다. 외부 라이브러리를 쓰지 않는다.
- 테스트도 같다.
  - 파이썬은 `assert`를 쓴 스크립트다.
  - JS는 `node:assert` + `vm`으로 돌린다.

**Spec:** `C:\jongse\ipo-calendar\docs\superpowers\specs\2026-11-12-ipo-calendar-design.md`

## Global Constraints

- 로그인 없음, 서버 DB 없음.
- 내 기록(상태·배정 수량·수익)은 `localStorage` 키 `ipo-records`에만 저장한다. `data/ipos.json`이나 저장소에 넣지 않는다.
- 데이터 출처:
  - 목록: `https://www.38.co.kr/html/fund/index.htm?o=k`
  - 상세: `https://www.38.co.kr/html/fund/?o=v&no={no}`
  - 둘 다 **EUC-KR**이다.
- 기준 시간대는 KST(UTC+9)다. 날짜는 `YYYY-MM-DD` 문자열로 다룬다.
- 화면 기준은 폰 세로 폭 360~430px이다. 가로 스크롤이 생기면 안 된다.
- 수집이 실패하면 기존 `data/ipos.json`을 그대로 두고 종료 코드 1로 끝낸다. 빈 파일로 덮어쓰지 않는다.
- **커밋·푸시·GitHub 저장소 생성은 사용자가 요청할 때만 한다**(사용자 전역 규칙). 계획의 "커밋 준비" 단계는 변경을 정리해 두는 것까지만이다.
- 2026-11-12 직접 확인한 사실:
  - 상세 페이지의 `최저 : - 주`는 공모가 확정 종목(no=2331)에서도 비어 있다. 그래서 최소 청약 주식 수는 기본값 **10주**를 쓰고 "10주 기준"이라고 표시한다.
  - 10주라는 값 자체는 검증하지 못했다.
- 일반청약자 증거금률은 상세 페이지의 두 번째 `청약증거금율 : 50%`에서 읽는다. 첫 번째(100%)는 기관 몫이다. 읽지 못하면 0.5를 쓴다.

## Review Focus

1. **정정된 일정**: 청약일이나 상장일이 바뀌면 달력은 새 날짜로 옮기고, 종목에 "정정" 표시와 이전 값을 보여 준다.
2. **목록에서 사라진 종목**: 청약 종료일이 아직 지나지 않았는데 목록에서 빠지면 `cancel_suspect`로 바꾼다. 종료일이 지나서 빠진 종목은 그대로 둔다(정상 종료).
3. **값이 빈 칸**: 확정공모가 `-`, 상장일 빈칸, 희망공모가 `-`가 있어도 에러 없이 `null`로 저장한다. 화면에서는 "미정"으로 보여 준다.
4. **달 경계에 걸친 청약**: 예를 들어 `2026.11.27~11.30`, `2026.12.30~01.02` 같은 기간이다. 연도가 넘어가도 끝 날짜의 연도가 맞아야 하고, 두 달 모두에 표시된다.
5. **기록 불러오기에 잘못된 파일**: 형식이 다른 JSON을 불러오면 기존 기록을 유지하고 오류를 알린다.

---

### Task 1: 38커뮤니케이션 파서

**Files:**
- Create: `C:\jongse\ipo-calendar\fetch_ipos.py`
- Create: `C:\jongse\ipo-calendar\tests\test_parse.py`
- Create: `C:\jongse\ipo-calendar\tests\fixtures\list.html`, `detail_2355.html`, `detail_2331.html` (UTF-8로 변환해 저장)

**Interfaces:**
- Produces:
  - `fetch(url: str) -> str`: EUC-KR을 디코딩해 돌려준다. User-Agent는 `Mozilla/5.0`이다.
  - `parse_list(html: str) -> list[dict]`
    - 결과 항목: `{"no": int, "name": str, "sub_start": "YYYY-MM-DD", "sub_end": "YYYY-MM-DD"}`
    - 목록 표의 각 행에서 `o=v&no=(\d+)` 링크와 바로 그 행의 청약기간 `YYYY.MM.DD~MM.DD`를 짝짓는다.
    - 행(`<tr>`) 단위로 자른 뒤 그 안에서 찾는다. 줄 사이를 정규식 하나로 건너뛰면 행이 밀린다(직접 시험해서 확인함).
  - `parse_detail(html: str, no: int) -> dict`
    - 키: `no, name, sub_start, sub_end, listing, price_final, price_band, brokers, min_shares, margin_rate, progress`
    - `price_band`는 `[low, high]` 또는 `null`이다.
    - `brokers`는 `list[str]`이다(쉼표로 나눔).
    - `min_shares`는 `최저 :` 칸이 숫자면 int, 아니면 `null`이다.
    - `progress`는 `진행상황` 칸 문자열이다(예: `"공모주"`).

- [ ] **Step 1: fixture 받기**

```bash
cd /c/jongse/ipo-calendar && mkdir -p tests/fixtures
curl -s -A "Mozilla/5.0" "https://www.38.co.kr/html/fund/index.htm?o=k" | iconv -f euc-kr -t utf-8 > tests/fixtures/list.html
for n in 2355 2331; do curl -s -A "Mozilla/5.0" "https://www.38.co.kr/html/fund/?o=v&no=$n" | iconv -f euc-kr -t utf-8 > tests/fixtures/detail_$n.html; done
```

확인: `grep -c KTE tests/fixtures/detail_2355.html`가 1 이상이어야 한다.

- [ ] **Step 2: 실패하는 테스트 쓰기**

`tests/test_parse.py`는 ncmh-menu의 `tests/test_parse.py`처럼 만든다. `sys.path`에 루트를 넣고 `assert`로 확인한 뒤 `print("ok")`한다.

```python
d = parse_detail(read("detail_2331.html"), 2331)
assert d["name"] == "에이엘로봇"
assert (d["sub_start"], d["sub_end"]) == ("2026-11-06", "2026-11-09")
assert d["listing"] == "2026-11-18"
assert d["price_final"] == 17600
assert d["brokers"] == ["대신증권"]
assert d["min_shares"] is None and d["margin_rate"] == 0.5

d = parse_detail(read("detail_2355.html"), 2355)
assert d["name"] == "KTE" and d["listing"] is None and d["price_final"] is None
assert d["price_band"] == [19000, 23000] and d["brokers"] == ["NH투자증권"]

rows = parse_list(read("list.html"))
kte = next(r for r in rows if r["no"] == 2355)
assert (kte["name"], kte["sub_start"], kte["sub_end"]) == ("KTE", "2026-12-14", "2026-12-15")
assert len({r["no"] for r in rows}) == len(rows) >= 10

# 연도 넘김: 끝 날짜의 월이 시작보다 작으면 다음 해
assert period("2026.12.30~01.02") == ("2026-12-30", "2027-01-02")
```

`period(text: str) -> tuple[str, str]`도 `fetch_ipos.py`에 둔다.

- [ ] **Step 3: 실패 확인**

Run: `python tests/test_parse.py`
Expected: `ImportError` 또는 `AssertionError`

- [ ] **Step 4: `fetch_ipos.py`에 `fetch`, `period`, `parse_list`, `parse_detail` 구현**

상세 페이지 처리 방법:
- `html.unescape` 후 태그를 공백으로 바꾸고, 공백을 줄여 한 줄 텍스트로 만든다.
- 그다음 `라벨 다음 값` 정규식으로 읽는다. 라벨은 `종목명`, `진행상황`, `공모청약일`, `상장일`, `확정공모가`, `희망공모가액`, `주간사`, `최저 :`이다.
- 증거금률은 `청약증거금율 : (\d+)%`의 **두 번째** 일치를 쓴다.

- [ ] **Step 5: 통과 확인**

Run: `python tests/test_parse.py`
Expected: `ok`

- [ ] **Step 6: 커밋 준비** — 변경 파일 목록을 정리만 해 둔다(커밋은 사용자 요청 시).

### Task 2: 병합과 정정·취소 표시, 실행 진입점

**Files:**
- Modify: `C:\jongse\ipo-calendar\fetch_ipos.py`
- Modify: `C:\jongse\ipo-calendar\tests\test_parse.py`
- Create: `C:\jongse\ipo-calendar\data\ipos.json` (첫 실행 결과)

**Interfaces:**
- Consumes: Task 1의 `parse_list`, `parse_detail`, `fetch`
- Produces:
  - `merge(old: dict, fresh: list[dict], listed: set[int], today: str, now: str) -> dict`
    - `old`, 반환값 모두 `ipos.json` 형식이다.
  - `main(fetch=fetch, today=None) -> int`
    - 성공하면 0, 실패하면 1이다. `fetch`는 테스트에서 바꿔 끼운다.
  - `data/ipos.json` 형식(화면이 읽음):

```json
{"updated": "2026-11-12T21:00:00+09:00",
 "ipos": {"2355": {"no": 2355, "name": "KTE", "sub_start": "2026-12-14", "sub_end": "2026-12-15",
   "listing": null, "price_final": null, "price_band": [19000, 23000], "brokers": ["NH투자증권"],
   "min_shares": null, "margin_rate": 0.5, "progress": "공모주",
   "status": "active", "changes": [{"at": "...", "field": "sub_start", "old": "...", "new": "..."}]}}}
```

  - `status`는 `"active"` 또는 `"cancel_suspect"`다.
  - 추적하는 필드: `sub_start, sub_end, listing, price_final`

- [ ] **Step 1: 실패하는 테스트 추가**

```python
old = {"updated": "x", "ipos": {"1": {**BASE, "no": 1, "sub_start": "2026-12-01", "sub_end": "2026-12-02", "status": "active", "changes": []},
                               "2": {**BASE, "no": 2, "sub_start": "2026-12-03", "sub_end": "2026-12-04", "status": "active", "changes": []},
                               "3": {**BASE, "no": 3, "sub_start": "2026-11-01", "sub_end": "2026-11-02", "status": "active", "changes": []}}}
fresh = [{**BASE, "no": 1, "sub_start": "2026-12-08", "sub_end": "2026-12-09"}]
m = merge(old, fresh, {1}, "2026-11-12", "T")
assert m["ipos"]["1"]["sub_start"] == "2026-12-08"
assert {"at": "T", "field": "sub_start", "old": "2026-12-01", "new": "2026-12-08"} in m["ipos"]["1"]["changes"]
assert m["ipos"]["2"]["status"] == "cancel_suspect"       # 아직 안 끝났는데 목록에서 빠짐
assert m["ipos"]["3"]["status"] == "active"               # 이미 끝나서 빠진 건 정상
m2 = merge(m, [{**BASE, "no": 2, "sub_start": "2026-12-03", "sub_end": "2026-12-04"}], {2}, "2026-11-13", "T2")
assert m2["ipos"]["2"]["status"] == "active"              # 다시 나타나면 복구

def boom(url): raise OSError("down")
rc, data = run_main(boom)                                  # ncmh-menu 방식: 임시 파일로 main 실행
assert rc == 1 and data == {"ipos": "old"}                 # 실패 시 기존 파일 유지
```

`BASE`는 테스트 파일 안에 둔다. 나머지 필드를 `None`으로 채운 dict다.

- [ ] **Step 2: 실패 확인** — `python tests/test_parse.py` → `NameError: merge`

- [ ] **Step 3: `merge`, `main` 구현**

`main` 흐름:
1. 목록을 파싱한다.
2. `sub_end >= today − 60일`인 행만 상세 페이지를 받는다. 요청 사이에 `time.sleep(1)`을 둔다.
3. `merge`로 합친다.
4. `data/ipos.json`을 UTF-8, `ensure_ascii=False`, `indent=1`로 쓴다.

실패 처리:
- 목록 파싱 결과가 0건이면 실패로 본다.
- 예외가 나도 실패로 본다.
- 실패하면 파일을 건드리지 않고 1을 돌려준다.

- [ ] **Step 4: 통과 확인** — `python tests/test_parse.py` → `ok`

- [ ] **Step 5: 실제로 한 번 실행**

Run: `cd /c/jongse/ipo-calendar && python fetch_ipos.py && python -c "import json;d=json.load(open('data/ipos.json',encoding='utf-8'));print(len(d['ipos']), d['ipos']['2355']['name'])"`
Expected: 10 이상의 숫자와 `KTE`

- [ ] **Step 6: 커밋 준비**

### Task 3: 화면 규칙(`logic.js`)

**Files:**
- Create: `C:\jongse\ipo-calendar\logic.js`
- Create: `C:\jongse\ipo-calendar\tests\test_view.mjs`

**Interfaces:**
- Consumes: `data/ipos.json` 형식(Task 2)
- Produces (전역 함수, `index.html`과 테스트가 같이 씀):
  - `minAmount(ipo) -> {amount: number|null, shares: number, estimated: boolean}`
    - 가격은 `price_final ?? price_band?.[0]`이다.
    - 주식 수는 `min_shares ?? 10`이다.
    - 금액은 `가격 × 주식수 × margin_rate`이고, 소수점은 반올림한다.
    - `estimated`는 확정공모가가 없을 때 true다.
  - `eventsOn(ipos, iso) -> [{ipo, kind: "sub"|"listing"}]`
    - `sub_start <= iso <= sub_end`이면 `"sub"`, `listing == iso`이면 `"listing"`이다.
  - `monthGrid(year, month) -> string[42]`
    - 월요일 시작 6주 칸이다. 앞뒤 달 날짜도 ISO로 채운다.
  - `weekItems(ipos, todayIso) -> {sub: ipo[], listing: ipo[]}`
    - 오늘이 든 주(월~일)에 청약 기간이 겹치거나 상장하는 종목이다. 날짜순으로 정렬한다.
  - `RECORD_STATES = ["subscribed", "holding", "sold"]`
    - 표시는 청약함 / 보유 중 / 매도함이다.
  - `parseRecords(text: string) -> object`
    - 형식이 `{ "<no>": {state, shares, profit} }`가 아니면 `Error`를 던진다.
    - `state`는 `RECORD_STATES` 중 하나여야 한다.
    - `shares`, `profit`은 정수 또는 null이다.

- [ ] **Step 1: 실패하는 테스트 쓰기** (`vm.runInThisContext`로 `logic.js` 로드. ncmh-menu `tests/test_view.mjs` 방식)

```js
const K = {no:1, price_final:null, price_band:[19000,23000], min_shares:null, margin_rate:0.5,
           sub_start:"2026-11-27", sub_end:"2026-11-30", listing:"2026-12-08"};
assert.deepEqual(minAmount(K), {amount:95000, shares:10, estimated:true});
assert.deepEqual(minAmount({...K, price_final:17600}), {amount:88000, shares:10, estimated:false});
assert.equal(minAmount({...K, price_band:null}).amount, null);
assert.equal(eventsOn([K], "2026-11-28")[0].kind, "sub");
assert.equal(eventsOn([K], "2026-12-08")[0].kind, "listing");
assert.equal(eventsOn([K], "2026-12-01").length, 0);
const g = monthGrid(2026, 11); assert.equal(g.length, 42); assert.equal(g[0], "2026-10-26"); assert.ok(g.includes("2026-11-30"));
assert.deepEqual(weekItems([K], "2026-11-30").sub.map(i=>i.no), [1]);   // 11/30(월) 주에 걸침
assert.throws(() => parseRecords('{"1":{"state":"bought"}}'));
assert.throws(() => parseRecords("not json"));
assert.deepEqual(parseRecords('{"1":{"state":"sold","shares":2,"profit":15000}}'), {"1":{state:"sold",shares:2,profit:15000}});
console.log("ok");
```

- [ ] **Step 2: 실패 확인** — `node tests/test_view.mjs` → `ReferenceError`
- [ ] **Step 3: `logic.js` 구현** (DOM 접근 없음)
- [ ] **Step 4: 통과 확인** — `node tests/test_view.mjs` → `ok`
- [ ] **Step 5: 커밋 준비**

### Task 4: 화면(`index.html`)

**Files:**
- Create: `C:\jongse\ipo-calendar\index.html` (CSS·JS 인라인, `<script src="logic.js">`)

**Interfaces:**
- Consumes: Task 3의 함수 전부, `data/ipos.json`, `localStorage["ipo-records"]`

화면 구성(설계 문서 5절):
- **위쪽: 한 달 달력**
  - `monthGrid`로 그리고, 이전·다음 달 버튼을 둔다.
  - 날짜 칸에는 청약(파랑 계열 띠)과 상장(초록 계열 점)을 표시하고 종목명을 줄여 쓴다.
  - 내 기록이 있는 종목은 상태 배지를 단다(청/보/매).
  - `status=cancel_suspect`인 종목은 취소선과 "취소?"로 표시한다.
  - `changes`가 있는 종목은 "정정" 배지를 단다.
- **아래쪽: "이번 주" 목록**: `weekItems`의 청약·상장 두 묶음이다.
- **종목을 누르면 상세 시트가 열린다**
  - 청약 기간, 상장일("미정" 가능), 증권사, 최소 청약금액을 보여 준다.
    - 최소 청약금액은 `"95,000원 (10주 기준, 예상)"`처럼 쓴다.
  - 정정 이력(이전 값 → 새 값)을 보여 준다.
  - 내 기록을 입력한다: 상태 버튼 3개, 배정 수량, 매도 수익 입력란.
  - 입력값은 바로 `localStorage`에 저장한다.
  - `localStorage` 접근은 try/catch로 감싼다.
- **맨 아래**
  - "기록 내보내기": `ipo-records-YYYY-MM-DD.json`을 내려받는다.
  - "기록 불러오기": 파일을 고르면 `parseRecords`를 거친다. 실패하면 기존 기록을 유지하고 메시지를 띄운다(`alert` 대신 화면 문구).
  - 마지막 갱신 시각(`updated`)을 보여 준다.
- 다크 모드는 `prefers-color-scheme`으로 처리한다.

- [ ] **Step 1: 구현**
- [ ] **Step 2: 로컬 확인**

Run: `cd /c/jongse/ipo-calendar && python -m http.server 8000`

브라우저 폭 390px에서 확인할 것:
- 가로 스크롤이 없다.
- 이번 달 청약 종목이 달력에 보인다.
- 종목을 눌러 "보유 중"과 수량 3을 넣고 새로고침해도 남아 있다.
- 내보낸 파일을 다시 불러올 수 있다.
- 잘못된 파일(`{"a":1}`)을 불러오면 오류 문구가 나오고 기존 기록이 유지된다.

- [ ] **Step 3: 커밋 준비**

### Task 5: 자동 갱신과 배포

**Files:**
- Create: `C:\jongse\ipo-calendar\.github\workflows\update.yml`
- Create: `C:\jongse\ipo-calendar\.gitignore` (`__pycache__/`)

**Interfaces:**
- Consumes: `python tests/test_parse.py`, `node tests/test_view.mjs`, `python fetch_ipos.py`

- [ ] **Step 1: 워크플로 작성**

ncmh-menu `.github/workflows/update.yml`을 그대로 따르되 다음만 바꾼다.
- cron: `"0 22,3,9 * * *"`(KST 07, 12, 18시)
- 커밋 대상: `data/ipos.json`
- 커밋 메시지: `chore: update ipos`
- `concurrency.group`: `update-ipos`

- [ ] **Step 2: 로컬에서 워크플로 명령 순서대로 실행**

Run: `python tests/test_parse.py && node tests/test_view.mjs && python fetch_ipos.py`
Expected: `ok`, `ok`, 종료 코드 0

- [ ] **Step 3: 사용자에게 묻기**

다음을 진행할지 사용자에게 묻는다.
- `gh repo create jongseP/ipo-calendar --public`
- 첫 커밋과 푸시
- GitHub Pages 켜기(main 브랜치 / 루트)

사용자가 승인하면 실행한다. 공개 저장소에는 공개 일정만 들어가고 내 기록은 들어가지 않는다는 점도 함께 알린다.

- [ ] **Step 4: 배포 확인**

`gh workflow run update.yml`을 실행하고 성공하는지 본다. 그다음 `https://jongsep.github.io/ipo-calendar/`가 열리고 달력이 보이는지 확인한다.
