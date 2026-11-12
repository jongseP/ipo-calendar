import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fetch_ipos import parse_detail, parse_list, period  # noqa: E402

F = ROOT / "tests" / "fixtures"


def read(name):
    return (F / name).read_text(encoding="utf-8")


d = parse_detail(read("detail_2331.html"), 2331)
assert d["name"] == "에이엘로봇", d
assert (d["sub_start"], d["sub_end"]) == ("2026-11-06", "2026-11-09"), d
assert d["listing"] == "2026-11-18", d
assert d["price_final"] == 17600, d
assert d["brokers"] == ["대신증권"], d
assert d["min_shares"] is None and d["margin_rate"] == 0.5, d
assert d["progress"] == "공모주", d
assert (d["inst_rate"], d["lockup_pct"], d["retail_rate"]) == (871.74, 1.13, 834.73), d

d = parse_detail(read("detail_2355.html"), 2355)
assert d["name"] == "KTE" and d["listing"] is None and d["price_final"] is None, d
assert d["price_band"] == [19000, 23000] and d["brokers"] == ["NH투자증권"], d
assert (d["inst_rate"], d["lockup_pct"], d["retail_rate"]) == (None, None, None), d  # 수요예측 전

# 유통가능물량: 머리글 순서가 '유통가능|매각제한'(2331)과 '매각제한|유통가능'(2358) 둘 다 맞게 읽는다
assert parse_detail(read("detail_2331.html"), 2331)["float_pct"] == 35.01
assert parse_detail(read("detail_2358.html"), 2358)["float_pct"] == 38.88
assert d["float_pct"] is None  # 표가 없는 종목(2355)

rows = parse_list(read("list.html"))
kte = next(r for r in rows if r["no"] == 2355)
assert (kte["name"], kte["sub_start"], kte["sub_end"]) == ("KTE", "2026-12-14", "2026-12-15"), kte
assert len({r["no"] for r in rows}) == len(rows) >= 10, rows

# 연도 넘김: 끝 날짜의 월이 시작보다 작으면 다음 해
assert period("2026.12.30~01.02") == ("2026-12-30", "2027-01-02")
assert period(" 2026.11.27~11.30 ") == ("2026-11-27", "2026-11-30")

# 빈 칸(&nbsp;만 있는 칸)은 다음 칸 글자를 값으로 읽으면 안 된다
blank = read("detail_2355.html").replace("<b>NH투자증권</b>", "").replace("&nbsp; 공모주	", "&nbsp; ")
d = parse_detail(blank, 2355)
assert d["brokers"] == [] and d["progress"] is None, (d["brokers"], d["progress"])

print("ok1")

# ---- merge: 정정·취소 의심 ----
import json  # noqa: E402
import tempfile  # noqa: E402

import fetch_ipos  # noqa: E402
from fetch_ipos import merge  # noqa: E402

BASE = {k: None for k in ("name", "listing", "price_final", "price_band", "min_shares", "progress")}
BASE.update(brokers=[], margin_rate=0.5)


def item(no, s, e, **kw):
    return {**BASE, "no": no, "sub_start": s, "sub_end": e, **kw}


old = {"updated": "x", "ipos": {
    "1": item(1, "2026-12-01", "2026-12-02", status="active", changes=[]),
    "2": item(2, "2026-12-03", "2026-12-04", status="active", changes=[]),
    "3": item(3, "2026-11-01", "2026-11-02", status="active", changes=[])}}
m = merge(old, [item(1, "2026-12-08", "2026-12-09")], {1}, "2026-11-12", "T")
assert m["ipos"]["1"]["sub_start"] == "2026-12-08", m
assert {"at": "T", "field": "sub_start", "old": "2026-12-01", "new": "2026-12-08"} in m["ipos"]["1"]["changes"], m
assert m["ipos"]["2"]["status"] == "cancel_suspect", m       # 아직 안 끝났는데 목록에서 빠짐
assert m["ipos"]["3"]["status"] == "active", m               # 이미 끝나서 빠진 건 정상
assert old["ipos"]["1"]["sub_start"] == "2026-12-01"         # 입력을 바꾸지 않음
m2 = merge(m, [item(2, "2026-12-03", "2026-12-04")], {2}, "2026-11-13", "T2")
assert m2["ipos"]["2"]["status"] == "active", m2             # 다시 나타나면 복구
assert m2["ipos"]["1"]["changes"] == m["ipos"]["1"]["changes"]  # 이력 유지
m4 = merge(m, [item(1, "2026-12-08", "2026-12-09", listing="2026-12-18", price_final=7000)], {1}, "2026-11-12", "T3")
assert [c["field"] for c in m4["ipos"]["1"]["changes"]] == ["sub_start", "sub_end"], m4  # 미정→확정은 정정 아님
m3 = merge({"ipos": {}}, [item(5, "2026-12-01", "2026-12-02")], {5}, "2026-11-12", "T")
assert m3["ipos"]["5"]["status"] == "active" and m3["ipos"]["5"]["changes"] == [], m3
print("ok2")


# ---- main: 실패하면 기존 파일 유지 ----
def run_main(fetch, today="2026-11-12"):
    tmp = Path(tempfile.mkdtemp()) / "ipos.json"
    tmp.write_text('{"ipos": "old"}', encoding="utf-8")
    fetch_ipos.OUT = tmp
    rc = fetch_ipos.main(fetch=fetch, today=today, pause=0)
    return rc, json.loads(tmp.read_text(encoding="utf-8"))


def boom(url):
    raise OSError("down")


rc, data = run_main(boom)
assert rc == 1 and data == {"ipos": "old"}, (rc, data)
rc, data = run_main(lambda url: "<html>표 없음</html>")
assert rc == 1 and data == {"ipos": "old"}, (rc, data)       # 목록 0건도 실패


def pages(url):
    if "o=k" in url:
        return read("list.html")
    return read("detail_2355.html") if "no=2355" in url else read("detail_2331.html").replace("에이엘로봇", "X")


tmp = Path(tempfile.mkdtemp()) / "ipos.json"
fetch_ipos.OUT = tmp                                         # 파일 없음 = 첫 실행
assert fetch_ipos.main(fetch=pages, today="2026-11-12", pause=0) == 0
data = json.loads(tmp.read_text(encoding="utf-8"))
assert data["ipos"]["2355"]["name"] == "KTE" and data["ipos"]["2355"]["status"] == "active", data["ipos"]["2355"]
assert data["updated"].endswith("+09:00"), data["updated"]

# 상세의 청약일이 비어 있으면 목록의 청약일을 쓴다
def pages_blank(url):
    return pages(url).replace("2026.12.14 &nbsp;~ &nbsp; 2026.12.15", "") if "no=2355" in url else pages(url)


tmp = Path(tempfile.mkdtemp()) / "ipos.json"
fetch_ipos.OUT = tmp
assert fetch_ipos.main(fetch=pages_blank, today="2026-11-12", pause=0) == 0
k = json.loads(tmp.read_text(encoding="utf-8"))["ipos"]["2355"]
assert (k["sub_start"], k["sub_end"]) == ("2026-12-14", "2026-12-15"), k
print("ok3")
