# pip install DrissionPage

from CloudflareBypassForScraping import CloudflareBypasser as cf
from DrissionPage import ChromiumPage

driver = ChromiumPage()
driver.get("https://nopecha.com/demo/cloudflare")

cf_bypasser = cf.CloudflareBypasser(driver)
cf_bypasser.bypass()
