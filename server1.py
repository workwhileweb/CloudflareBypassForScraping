import json
import re
import os
from urllib.parse import urlparse
from pyvirtualdisplay import Display
from CloudflareBypasser import CloudflareBypasser
from DrissionPage import ChromiumPage, ChromiumOptions
from fastapi import FastAPI, HTTPException, Response, Query
from pydantic import BaseModel
from typing import Dict
import argparse
import sys

# Check if running in Docker mode
DOCKER_MODE = os.getenv("DOCKERMODE", "false").lower() == "true"

# Chromium options arguments
arguments = [
    # "--remote-debugging-port=9222",  # Add this line for remote debugging
    "-no-first-run",
    "-force-color-profile=srgb",
    "-metrics-recording-only",
    "-password-store=basic",
    "-use-mock-keychain",
    "-export-tagged-pdf",
    "-no-default-browser-check",
    "-disable-background-mode",
    "-enable-features=NetworkService,NetworkServiceInProcess,LoadCryptoTokenExtension,PermuteTLSExtensions",
    "-disable-features=FlashDeprecationWarning,EnablePasswordsAccountStorage",
    "-deny-permission-prompts",
    "-disable-gpu",
    "-accept-lang=en-US",
    # "-incognito" # You can add this line to open the browser in incognito mode by default
]

if sys.platform.startswith("win"):
    browser_path = os.getenv("CHROME_PATH", r"C:/Program Files/Google/Chrome/Application/chrome.exe")
else:
    browser_path = os.getenv("CHROME_PATH", "/usr/bin/google-chrome")

app = FastAPI(
    title="Cloudflare Bypass API",
    description="An API service that helps bypass Cloudflare protection and retrieve cookies and HTML content from protected websites.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# Pydantic model for the response
class CookieResponse(BaseModel):
    cookies: Dict[str, str]
    user_agent: str

    class Config:
        schema_extra = {"example": {"cookies": {"cf_clearance": "abc123...", "other_cookie": "value"}, "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."}}


# Function to check if the URL is safe
def is_safe_url(url: str) -> bool:
    parsed_url = urlparse(url)
    ip_pattern = re.compile(r"^(127\.0\.0\.1|localhost|0\.0\.0\.0|::1|10\.\d+\.\d+\.\d+|172\.1[6-9]\.\d+\.\d+|172\.2[0-9]\.\d+\.\d+|172\.3[0-1]\.\d+\.\d+|192\.168\.\d+\.\d+)$")
    hostname = parsed_url.hostname
    if (hostname and ip_pattern.match(hostname)) or parsed_url.scheme == "file":
        return False
    return True


# Function to bypass Cloudflare protection
def bypass_cloudflare(url: str, proxy: str, retries: int, log: bool) -> ChromiumPage:
    if DOCKER_MODE:
        # Start Xvfb for Docker
        display = Display(visible=0, size=(1920, 1080))
        display.start()

        options = ChromiumOptions()
        options.set_argument("--auto-open-devtools-for-tabs", "true")
        options.set_argument("--remote-debugging-port=9222")
        options.set_argument("--no-sandbox")  # Necessary for Docker
        options.set_argument("--disable-gpu")  # Optional, helps in some cases
        if proxy:
            options.set_argument("--proxy-server=" + proxy)
        options.set_paths(browser_path=browser_path).headless(False)
    else:
        options = ChromiumOptions()
        options.set_argument("--auto-open-devtools-for-tabs", "true")
        options.set_paths(browser_path=browser_path).headless(False)

    driver = ChromiumPage(addr_or_opts=options)
    try:
        driver.get(url)
        cf_bypasser = CloudflareBypasser(driver, retries, log)
        cf_bypasser.bypass()
        return driver
    except Exception as e:
        driver.quit()
        if DOCKER_MODE:
            display.stop()  # Stop Xvfb
        raise e


# Endpoint to get cookies
@app.get(
    "/cookies",
    response_model=CookieResponse,
    summary="Get Cloudflare bypass cookies",
    description="Bypasses Cloudflare protection and returns the cookies and user agent needed for future requests.",
    response_description="Returns a dictionary of cookies and the user agent string",
)
async def get_cookies(
    url: str = Query(..., description="The URL of the Cloudflare-protected website"),
    proxy: str = Query(..., description="Proxy server to use (e.g., 'http://proxy:port')"),
    retries: int = Query(5, description="Number of retry attempts for bypassing Cloudflare"),
):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        driver = bypass_cloudflare(url, proxy, retries, log)
        cookies = driver.cookies(as_dict=True)
        user_agent = driver.user_agent
        driver.quit()
        return CookieResponse(cookies=cookies, user_agent=user_agent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint to get HTML content and cookies
@app.get(
    "/html",
    summary="Get HTML content with bypass",
    description="Bypasses Cloudflare protection and returns the full HTML content along with cookies and user agent in headers",
    response_description="Returns HTML content with cookies and user agent in response headers",
)
async def get_html(
    url: str = Query(..., description="The URL of the Cloudflare-protected website"),
    proxy: str = Query(..., description="Proxy server to use (e.g., 'http://proxy:port')"),
    retries: int = Query(5, description="Number of retry attempts for bypassing Cloudflare"),
):
    if not is_safe_url(url):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        driver = bypass_cloudflare(url, proxy, retries, log)
        html = driver.html
        cookies_json = json.dumps(driver.cookies(as_dict=True))

        response = Response(content=html, media_type="text/html")
        response.headers["cookies"] = cookies_json
        response.headers["user_agent"] = driver.user_agent
        driver.quit()
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Main entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cloudflare bypass api")

    parser.add_argument("--nolog", action="store_true", help="Disable logging")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")

    args = parser.parse_args()
    if args.headless and not DOCKER_MODE:
        display = Display(visible=0, size=(1920, 1080))
        display.start()
    if args.nolog:
        log = False
    else:
        log = True
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
