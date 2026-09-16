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
d.get("https://comix.to/title/m0z00-isekai-nonbiri-nouka/9513282-chapter-302")
time.sleep(6)
# scroll to load lazy images
for _ in range(8):
    d.execute_script("window.scrollBy(0, 1500)")
    time.sleep(0.7)
time.sleep(2)

imgs = d.execute_script("return Array.from(document.querySelectorAll('img')).map(i=>({src:i.currentSrc||i.src, w:i.naturalWidth, h:i.naturalHeight, cls:i.className}))")
print("TOTAL IMGS:", len(imgs))
page_imgs = [i for i in imgs if i["h"] > 400]
print("LARGE IMGS:", len(page_imgs))
for i in page_imgs[:15]:
    print(i["w"], "x", i["h"], "|", i["cls"], "|", i["src"][:120])

print("--- API CALLS ---")
seen = set()
for entry in d.get_log("performance"):
    try:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.requestWillBeSent":
            u = msg["params"]["request"]["url"]
            if "/api/" in u and u not in seen:
                seen.add(u); print(u[:200])
    except Exception:
        pass

print("--- DOM (reader area) ---")
html = d.execute_script("const el=document.querySelector('[class*=reader],[class*=Reader],[class*=page-img],main'); return el?el.outerHTML.slice(0,1500):'NONE';")
print(html)
d.quit()
