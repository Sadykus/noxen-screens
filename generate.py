"""Noxen: рисует экран сна 480x800 (BMP, 8-bit grayscale) со свежими данными.
Запускается GitHub Actions каждое утро. Если какой-то источник не ответил,
берёт прошлые значения из state.json, чтобы экран не ломался."""
import calendar, datetime as dt, json, math, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

TZ = dt.timezone(dt.timedelta(hours=5))          # Астана, UTC+5
LAT, LON, CITY = 51.17, 71.43, "Астана"
QUOTE = "Если не знаешь, к какой гавани плывёшь, ни один ветер не будет попутным."
AUTHOR = "— Сенека, «Письма к Луцилию», LXXI"
FOOTER_L, FOOTER_R = "для связи · Instagram", "@sadykus"
OUT, STATE = Path("screen.bmp"), Path("state.json")
MONTHS = ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
DAYS = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "noxen-screen/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def icon_kind(code):                     # WMO-код погоды -> значок шаблона
    if code <= 1: return "sun"
    if code == 2: return "part"
    return "cloud"                       # облачно, туман, осадки

def fetch_weather(monday):
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,wind_speed_10m_max"
           "&wind_speed_unit=ms&timezone=Asia%%2FAlmaty&past_days=7&forecast_days=8") % (LAT, LON)
    d = json.loads(get(url))["daily"]
    by_date = {t: i for i, t in enumerate(d["time"])}
    out = []
    for k in range(7):
        day = monday + dt.timedelta(days=k)
        i = by_date.get(day.isoformat())
        if i is None or d["temperature_2m_max"][i] is None:
            out.append(None); continue
        out.append((icon_kind(d["weather_code"][i]), round(d["temperature_2m_max"][i]),
                    round(d["temperature_2m_min"][i]), round(d["wind_speed_10m_max"][i])))
    return out

def fetch_rates():
    root = ET.fromstring(get("https://nationalbank.kz/rss/rates_all.xml?switch=russian"))
    rates, date = {}, ""
    for it in root.iter("item"):
        code = it.findtext("title")
        if code in ("USD", "EUR", "RUB"):
            rates[code] = float(it.findtext("description")) / float(it.findtext("quant") or 1)
            date = it.findtext("pubDate") or date
    return rates, date[:5]               # "22.10.2026" -> "22.10"

def fetch_btc():
    return json.loads(get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"))["bitcoin"]["usd"]

def money(v, dec):                       # 452.12 -> "452,12"; 82771 -> "82 771"
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s

def main():
    now = dt.datetime.now(TZ); today = now.date()
    monday = today - dt.timedelta(days=today.weekday())
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    try: wx = fetch_weather(monday)
    except Exception as e: print("weather failed:", e); wx = state.get("wx", [None] * 7)
    try: rates, rdate = fetch_rates()
    except Exception as e: print("rates failed:", e); rates, rdate = state.get("rates", {}), state.get("rdate", "")
    try: btc = fetch_btc()
    except Exception as e: print("btc failed:", e); btc = state.get("btc")
    STATE.write_text(json.dumps({"wx": wx, "rates": rates, "rdate": rdate, "btc": btc}, ensure_ascii=False))

    W, H, K, G1, WH, M = 480, 800, 0, 85, 255, 24
    D = "/usr/share/fonts/truetype/dejavu/"
    F = lambda n, s: ImageFont.truetype(D + n, s)
    SERIF_I, SANS, SANS_B = "DejaVuSerif-Italic.ttf", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"
    img = Image.new("L", (W, H), WH); d = ImageDraw.Draw(img)
    tl = lambda t, f: d.textlength(t, font=f)
    def center(x0, x1, y, t, f): d.text((x0 + (x1 - x0 - tl(t, f)) / 2, y), t, font=f, fill=K)
    def wrap(text, font, width):
        out, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if tl(t, font) > width: out.append(cur); cur = w
            else: cur = t
        return out + [cur]
    def section(y, title):
        f = F(SANS_B, 15); d.text((M, y), title.upper(), font=f, fill=K)
        x = M + tl(title.upper(), f) + 10; d.line([(x, y + 8), (W - M, y + 8)], fill=G1, width=1)

    fq = F(SERIF_I, 24); y = 26
    for ln in wrap(QUOTE, fq, W - 2 * M): d.text((M, y), ln, font=fq, fill=K); y += 33
    fa = F(SANS_B, 14); d.text((W - M - tl(AUTHOR, fa), y + 4), AUTHOR, font=fa, fill=K); y += 34

    week_no = today.isocalendar()[1]
    section(y, f"{MONTHS[today.month-1]} {today.year} · текущая неделя {week_no}"); y += 26
    cw = (W - 2 * M) / 7
    for i, n in enumerate(DAYS): center(M + i*cw, M + (i+1)*cw, y, n, F(SANS_B, 15))
    y += 22
    weeks = calendar.Calendar(0).monthdayscalendar(today.year, today.month); ch = 40
    fn, fnb = F(SANS, 17), F(SANS_B, 17)
    for r, wk in enumerate(weeks):
        ry = y + r * ch; cur = today.day in wk
        if cur: d.rounded_rectangle([M-4, ry, W-M+4, ry+ch-4], radius=8, fill=140, outline=K, width=2)
        for c, day in enumerate(wk):
            if not day: continue
            mx, my = M + c*cw + cw/2, ry + (ch-4)/2
            f = fnb if (c >= 5 or cur) else fn
            t = str(day); bb = d.textbbox((0, 0), t, font=f)
            d.text((mx - (bb[2]+bb[0])/2, my - (bb[3]+bb[1])/2), t, font=f, fill=K)
    y += len(weeks) * ch + 22

    section(y, f"Погода · {CITY}"); y += 26
    def sun(cx, cy, r):
        for k in range(8):
            a = math.radians(k*45)
            d.line([(cx+(r+3)*math.cos(a), cy+(r+3)*math.sin(a)), (cx+(r+7)*math.cos(a), cy+(r+7)*math.sin(a))], fill=K, width=2)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=K)
    def cloud(cx, cy, fill=140):
        boxes = ([cx-15, cy-3, cx+1, cy+11], [cx-7, cy-11, cx+11, cy+7], [cx+1, cy-3, cx+16, cy+11])
        for b in boxes: d.ellipse([b[0]-2, b[1]-2, b[2]+2, b[3]+2], fill=K)
        d.rectangle([cx-9, cy+2, cx+11, cy+13], fill=K)
        for b in boxes: d.ellipse(b, fill=fill)
        d.rectangle([cx-7, cy+2, cx+9, cy+11], fill=fill)
    sg = lambda v: ("+" if v > 0 else "") + str(v) + "°"
    fdw, fdt, fhi, flo, fw = F(SANS_B,16), F(SANS_B,13), F(SANS_B,18), F(SANS_B,15), F(SANS_B,13)
    for i in range(7):
        x0, x1 = M + i*cw, M + (i+1)*cw; mx = (x0+x1)/2
        day = monday + dt.timedelta(days=i)
        center(x0, x1, y, DAYS[i], fdw); center(x0, x1, y+18, str(day.day), fdt); iy = y + 54
        w = wx[i] if i < len(wx) else None
        if day < today or not w:
            center(x0, x1, iy-10, "—", F(SANS_B, 20))
            center(x0, x1, y+80, "прошёл" if day < today else "нет", F(SANS_B, 11)); continue
        kind, hi, lo, wind = w
        if kind == "sun": sun(mx, iy, 8)
        elif kind == "part": sun(mx+7, iy-7, 6); cloud(mx-3, iy+2)
        else: cloud(mx, iy)
        center(x0, x1, y+76, sg(hi), fhi); center(x0, x1, y+97, sg(lo), flo); center(x0, x1, y+118, f"{wind} м/с", fw)
    y += 170

    section(y, f"Курсы на {rdate or '—'} · Нацбанк РК"); y += 26
    cells = [("USD", f"{money(rates['USD'],2)} ₸" if "USD" in rates else "—"),
             ("EUR", f"{money(rates['EUR'],2)} ₸" if "EUR" in rates else "—"),
             ("RUB", f"{money(rates['RUB'],2)} ₸" if "RUB" in rates else "—"),
             ("BTC", f"${money(btc,0)}" if btc else "—")]
    qw = (W - 2*M) / 4
    for i, (code, val) in enumerate(cells):
        x0, x1 = M + i*qw, M + (i+1)*qw
        center(x0, x1, y, code, F(SANS_B, 15)); center(x0, x1, y+18, val, F(SANS_B, 17))

    d.line([(M, H-44), (W-M, H-44)], fill=K, width=2)
    fs, fb = F(SANS_B, 15), F(SANS_B, 18)
    d.text((M, H-31), FOOTER_L, font=fs, fill=K)
    d.text((W - M - tl(FOOTER_R, fb), H-33), FOOTER_R, font=fb, fill=K)
    img.save(OUT); img.save("preview.png")
    print("ok", now.isoformat())

if __name__ == "__main__":
    main()
