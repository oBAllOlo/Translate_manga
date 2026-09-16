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
time.sleep(5)

# Map request id -> url, then fetch body for /api/v1/chapters/<id>
req_map = {}
for entry in d.get_log("performance"):
    try:
        msg = json.loads(entry["message"])["message"]
        if msg.get("method") == "Network.responseReceived":
            u = msg["params"]["response"]["url"]
            rid = msg["params"]["requestId"]
            if "/api/v1/chapters/" in u and "indexes" not in u:
                req_map[rid] = u
    except Exception:
        pass

print("Candidate responses:", req_map)
for rid, u in req_map.items():
    try:
        body = d.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
        print("URL:", u)
        print(body.get("body", "")[:3000])
        print("---")
    except Exception as e:
        print("ERR", u, e)

d.quit()
