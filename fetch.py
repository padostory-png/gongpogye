"""
공포계 — 시장 체온 계산 스크립트
지표 4개: S&P500, SOX(반도체), VIX, 하이일드 스프레드
0 = 2020.03 코로나 공포 / 100 = 반도체 슈퍼사이클 과열
"""
import json, os
import numpy as np
import requests
import yfinance as yf

FRED_KEY = os.environ.get("FRED_API_KEY", "")
OUT = "data"
os.makedirs(OUT, exist_ok=True)

# ---------- 1. 데이터 수집 ----------
T = {"sp": "^GSPC", "sox": "^SOX", "vix": "^VIX"}
raw = yf.download(list(T.values()), period="400d", auto_adjust=False, progress=False)["Close"]
raw = raw.dropna(how="all").ffill()

def last(t):     return float(raw[t].iloc[-1])
def high52(t):   return float(raw[t].iloc[-252:].max())
def drawdown(t): return (last(t) / high52(t) - 1) * 100
def ret1y(t):
    s = raw[t].dropna()
    base = s.iloc[-252] if len(s) >= 252 else s.iloc[0]
    return (s.iloc[-1] / base - 1) * 100

def fred_latest(series):
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series, "api_key": FRED_KEY, "file_type": "json",
                "sort_order": "desc", "limit": 10}, timeout=30).json()
    for o in r["observations"]:
        if o["value"] not in (".", ""):
            return float(o["value"]), o["date"]
    raise RuntimeError("FRED no data")

sp_dd,  sp_ret  = drawdown(T["sp"]),  ret1y(T["sp"])
sox_dd, sox_ret = drawdown(T["sox"]), ret1y(T["sox"])
vix             = last(T["vix"])
hy, hy_date     = fred_latest("BAMLH0A0HYM2")   # 미국 하이일드 OAS (%)

# ---------- 2. 점수 변환 (0~100, 공식 고정) ----------
def interp(x, xs, ys):
    return float(np.clip(np.interp(x, xs, ys), 0, 100))

# 기준점: 코로나(2020.03) ≈ 6 / 평상시 ≈ 54 / 조정 ≈ 32 / 반도체 과열 ≈ 81
score_sp  = interp(sp_dd,  [-34, -20, -10, -5, 0], [0, 12, 25, 35, 42]) + interp(sp_ret,  [-20, 0, 10, 30, 50],  [0, 10, 20, 38, 58])
score_sox = interp(sox_dd, [-45, -30, -15, -5, 0], [0, 12, 25, 35, 42]) + interp(sox_ret, [-30, 0, 20, 60, 100], [0, 10, 20, 40, 58])
score_hy  = interp(hy,  [2.5, 3, 3.5, 4, 5.5, 8, 11], [100, 80, 60, 45, 30, 12, 0])
score_vix = interp(vix, [9, 13, 17, 22, 30, 45, 82],  [100, 72, 52, 38, 24, 10, 0])

W = {"sp": 0.30, "sox": 0.30, "hy": 0.25, "vix": 0.15}
total = round(score_sp*W["sp"] + score_sox*W["sox"] + score_hy*W["hy"] + score_vix*W["vix"], 1)

def zone(s):
    if s < 20: return "공포 극단"
    if s < 30: return "공포"
    if s < 50: return "조정"
    if s < 80: return "활황"
    return "과열"

today = {
    "date": str(raw.index[-1].date()),
    "score": total,
    "zone": zone(total),
    "parts": {
        "sp":  {"value": round(sp_dd, 2),  "ret1y": round(sp_ret, 1),  "score": round(score_sp, 1),  "w": W["sp"]},
        "sox": {"value": round(sox_dd, 2), "ret1y": round(sox_ret, 1), "score": round(score_sox, 1), "w": W["sox"]},
        "hy":  {"value": round(hy, 2),     "date": hy_date,            "score": round(score_hy, 1),  "w": W["hy"]},
        "vix": {"value": round(vix, 2),                                 "score": round(score_vix, 1), "w": W["vix"]},
    },
}

# ---------- 3. 무엇이 움직였나 ----------
hist_path = f"{OUT}/history.json"
history = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
prev = next((h for h in reversed(history) if h["date"] != today["date"]), None)
if prev:
    names = {"sp": "S&P", "sox": "반도체", "hy": "스프레드", "vix": "VIX"}
    moves = []
    for k in W:
        d = (today["parts"][k]["score"] - prev["parts"][k]["score"]) * W[k]
        if abs(d) >= 0.3:
            moves.append(f"{names[k]} {d:+.1f}")
    today["change"] = round(total - prev["score"], 1)
    today["why"] = ", ".join(moves) if moves else "큰 변화 없음"
else:
    today["change"] = 0.0
    today["why"] = "첫 기록"

# ---------- 4. 저장 ----------
if history and history[-1]["date"] == today["date"]:
    history[-1] = today
else:
    history.append(today)
history = history[-400:]
json.dump(history, open(hist_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(today, open(f"{OUT}/latest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"[{today['date']}] 공포계 {total} ({today['zone']})  {today['change']:+} | {today['why']}")
print(f"  S&P 고점比 {sp_dd:.1f}%  SOX 고점比 {sox_dd:.1f}%  HY {hy:.2f}%  VIX {vix:.1f}")
