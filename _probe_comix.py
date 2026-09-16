from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time, json

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--disable-gpu")
opts.add_argument("--window-size=1400,2000")
opts.add_experimental_option("excludeSwitches", ["enable-logging"])
opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})

d = webdriver.Chrome(options=opts)
d.get("https://comix.to/title/m0z00-isekai-nonbiri-nouka")
time.sleep(6)
d.execute_script("window.scrollTo(0, document.body.scrollHeight)")
time.sleep(3)

js = """
const anchors = Array.from(document.querySelectorAll('a'));
return anchors.map(a => ({href: a.getAttribute('href'), text: (a.innerText||'').trim().slice(0,80)}));
"""
links = d.execute_script(js)
seen = set(); out = []
for l in links:
    h = l.get("href") or ""
    if not h or h in seen: continue
    seen.add(h); out.append(l)

chapter_links = [l for l in out if "chapter" in (l["href"] or "").lower()]
print("TOTAL LINKS:", len(out), " CHAPTER-LIKE:", len(chapter_links))
for l in chapter_links[:30]:
    print(l["href"], "|", l["text"][:60])

print("--- API CALLS ---")
api_urls = set()
for entry in d.get_log("performance"):
    try:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.requestWillBeSent":
            u = msg["params"]["request"]["url"]
            if "/api/" in u:
                api_urls.add(u)
                hdrs = msg["params"]["request"].get("headers", {})
                interesting = {k: v for k, v in hdrs.items() if k.lower() not in ("accept","accept-encoding","accept-language","user-agent","referer","cookie","sec-ch-ua","sec-ch-ua-mobile","sec-ch-ua-platform","sec-fetch-dest","sec-fetch-mode","sec-fetch-site","priority")}
                if interesting:
                    print("HEADERS for", u[:120], ":", interesting)
    except Exception:
        pass
for u in sorted(api_urls):
    print(u)

print("--- DOM SAMPLE (chapter container) ---")
html = d.execute_script("const el=document.querySelector('[class*=chapter], [class*=Chapter]'); return el ? el.outerHTML.slice(0,2000) : 'NONE';")
print(html)

d.quit()
