"""38커뮤니케이션 공모주 일정을 data/ipos.json으로 만든다."""
import html as htmllib
import json
import re
import ssl
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "ipos.json"
KST = timezone(timedelta(hours=9))
TRACKED = ("sub_start", "sub_end", "listing", "price_final")
LIST_URL = "https://www.38.co.kr/html/fund/index.htm?o=k"
DETAIL_URL = "https://www.38.co.kr/html/fund/?o=v&no={no}"


def fetch(url):
    # 38.co.kr은 오래된 암호 방식이라 OpenSSL 3 기본(SECLEVEL 2)에서 handshake failure가 난다.
    # 공개 일정을 읽기만 하므로 이 요청에서만 보안 수준을 1로 낮춘다.
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return r.read().decode("euc-kr", errors="replace")


def period(text):
    """'2026.12.30~01.02' -> ('2026-12-30', '2027-01-02')"""
    m = re.search(r"(\d{4})\.(\d\d)\.(\d\d)\s*~\s*(?:(\d{4})\.)?(\d\d)\.(\d\d)", text)
    y, m1, d1, y2, m2, d2 = m.groups()
    y2 = int(y2) if y2 else int(y) + (int(m2) < int(m1))
    return f"{y}-{m1}-{d1}", f"{y2}-{m2}-{d2}"


def _flat(html):
    """태그 사이 글자를 '|'로 이은 한 줄. 빈 조각은 버린다.
    빈 표 칸은 '-'로 남긴다. 버리면 '주간사|' 뒤에 다음 칸 글자가 붙어 값으로 읽힌다."""
    html = re.sub(r"(<td[^>]*>)(?:\s|&nbsp;|<(?!/?td)[^>]*>)*(</td>)", r"\1-\2", html, flags=re.I)
    parts = (re.sub(r"\s+", " ", htmllib.unescape(p).replace("\xa0", " ")).strip()
             for p in re.split(r"<[^>]*>", html))
    return "|".join(p for p in parts if p)


def _num(s):
    return int(s.replace(",", ""))


def parse_list(html):
    rows, seen = [], set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        m = re.search(r"o=v&amp;no=(\d+)[^>]*>(.*?)</a>", tr, re.S)
        p = re.search(r"\d{4}\.\d\d\.\d\d~\d\d\.\d\d", tr)
        if not m or not p or int(m.group(1)) in seen:
            continue
        no = int(m.group(1))
        seen.add(no)
        start, end = period(p.group(0))
        rows.append({"no": no, "name": _flat(m.group(2)), "sub_start": start, "sub_end": end})
    return rows


def parse_detail(html, no):
    t = _flat(html)

    def get(pat):
        m = re.search(pat, t)
        return m.groups() if m else None

    def val(label):
        v = get(label + r"\|([^|]+)")
        return None if not v or v[0] == "-" else v[0]

    sub = get(r"공모청약일\|([\d.]+ ~ [\d.]+)")
    start, end = period(sub[0]) if sub else (None, None)
    listing = get(r"상장일\|(\d{4})\.(\d\d)\.(\d\d)")
    final = get(r"확정공모가\|([\d,]+)\|? ?원")
    band = get(r"희망공모가액\|([\d,]+) ~ ([\d,]+)")
    least = get(r"최저 : ([\d,]+) 주")
    rates = re.findall(r"청약증거금율 : (\d+)%", t)
    return {
        "no": no,
        "name": get(r"종목명\|([^|]+)")[0],
        "sub_start": start,
        "sub_end": end,
        "listing": "-".join(listing) if listing else None,
        "price_final": _num(final[0]) if final else None,
        "price_band": [_num(band[0]), _num(band[1])] if band else None,
        "brokers": [b.strip() for b in (val("주간사") or "").split(",") if b.strip()],
        "min_shares": _num(least[0]) if least else None,
        "margin_rate": int(rates[1]) / 100 if len(rates) > 1 else 0.5,
        "progress": val("진행상황"),
    }


def merge(old, fresh, listed, today, now):
    """fresh: 이번에 상세를 읽은 종목들. listed: 목록에 있던 번호 전체."""
    ipos = {k: {**v, "changes": list(v.get("changes", []))} for k, v in old.get("ipos", {}).items()}
    for new in fresh:
        key = str(new["no"])
        prev = ipos.get(key)
        changes = prev["changes"] if prev else []
        if prev:
            changes += [{"at": now, "field": f, "old": prev.get(f), "new": new[f]}
                        for f in TRACKED if prev.get(f) is not None and prev.get(f) != new[f]]  # 미정→확정은 정정 아님
        ipos[key] = {**new, "status": "active", "changes": changes}
    for key, v in ipos.items():
        if int(key) not in listed and v["sub_end"] and v["sub_end"] >= today:
            v["status"] = "cancel_suspect"
    return {"updated": now, "ipos": ipos}


def main(fetch=fetch, today=None, pause=1):
    now = datetime.now(KST)
    today = today or now.date().isoformat()
    since = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    try:
        rows = parse_list(fetch(LIST_URL))
        if not rows:
            raise ValueError("목록 0건")
        fresh = []
        for r in rows:
            if r["sub_end"] < since:
                continue
            d = parse_detail(fetch(DETAIL_URL.format(no=r["no"])), r["no"])
            if not d["sub_start"]:  # 상세의 청약일이 비면 목록 값을 쓴다
                d.update(sub_start=r["sub_start"], sub_end=r["sub_end"])
            fresh.append(d)
            time.sleep(pause)
    except Exception as e:  # noqa: BLE001 — 어떤 실패든 파일은 그대로 둔다
        print(f"수집 실패: {e!r} — ipos.json을 그대로 둔다", file=sys.stderr)
        return 1
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"ipos": {}}
    data = merge(old, fresh, {r["no"] for r in rows}, today, now.isoformat(timespec="seconds"))
    if data["ipos"] == old.get("ipos"):
        print("변경 없음")
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"저장: {len(data['ipos'])}종목")
    return 0


if __name__ == "__main__":
    sys.exit(main())
