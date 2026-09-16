from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time, json

opts = Options()
opts.add_argument("--headless=new")
opts.add_argument("--disable-gpu")
opts.add_argument("--window-size=1400,2000")
opts.add_experimental_option("excludeSwitches", ["enable-logging"])

d = webdriver.Chrome(options=opts)
d.get("https://comix.to/title/m0z00-isekai-nonbiri-nouka/9513282-chapter-302")
time.sleep(5)

# Call API from inside the browser (uses the page's auth context)
js = """
const cb = arguments[arguments.length - 1];
(async () => {
  try {
    const r = await fetch('/api/v1/chapters/9513282', {
      headers: {'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
      credentials: 'same-origin'
    });
    const txt = await r.text();
    cb({status: r.status, body: txt.slice(0, 4000)});
  } catch(e) { cb({error: String(e)}); }
})();
"""
d.set_script_timeout(20)
res = d.execute_async_script(js)
print("STATUS:", res.get("status"))
print(res.get("body") or res.get("error"))
d.quit()
