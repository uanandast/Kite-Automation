import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
from kiteconnect import KiteConnect
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from cred._base import ACCESS_TOKEN_PATH, PROJECT_ROOT, kite_credentials

WAIT_SECONDS = 20
STALE_RETRIES = 3
LOGS_DIR = PROJECT_ROOT / "logs"


def _extract_page_errors(driver) -> str:
    """Extract visible error messages or alerts from the page."""
    error_texts = []
    selectors = [
        ".error", ".alert", ".danger", ".message",
        "p.error", "div.error", "span.error",
        "[role='alert']", ".form-error",
    ]
    for sel in selectors:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    text = el.text.strip()
                    if text and text not in error_texts:
                        error_texts.append(text)
        except Exception:
            pass
    return " | ".join(error_texts)


def _save_debug_screenshot(driver, prefix: str = "login_error") -> str | None:
    """Save screenshot on failure to assist diagnosis."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        screenshot_path = LOGS_DIR / f"{prefix}_{int(time.time())}.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"📸 Debug screenshot saved to: {screenshot_path}")
        return str(screenshot_path)
    except Exception as err:
        print(f"⚠️ Could not capture debug screenshot: {err}")
        return None


def _retry_stale(action, description: str):
    """Retry an interaction when Kite replaces its login form mid-render."""
    for attempt in range(1, STALE_RETRIES + 1):
        try:
            return action()
        except StaleElementReferenceException:
            if attempt == STALE_RETRIES:
                raise
            print(f"ℹ️ Kite login form refreshed; retrying {description} ({attempt}/{STALE_RETRIES}).")
            time.sleep(0.5)


def _request_token_from_url(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    return query.get("request_token", [None])[0]


def _find_chrome_binary() -> str | None:
    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin and Path(chrome_bin).is_file():
        return chrome_bin

    mac_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for path in mac_paths:
        if Path(path).is_file():
            return path
    return None


def _create_driver():
    options = webdriver.ChromeOptions()
    chrome_bin = _find_chrome_binary()
    if chrome_bin:
        options.binary_location = chrome_bin

    # Headless mode ensures reliable background execution across Docker/AWS and macOS
    is_headless = os.getenv("HEADLESS", "true").lower() not in ("0", "false", "no")
    if is_headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--remote-debugging-port=0")

    # Anti-bot detection flags to prevent headless challenge blocking
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Critical: always isolate profile to prevent conflict with any active browser instance
    profile_dir = tempfile.mkdtemp(prefix="kite-login-chrome-")
    options.add_argument(f"--user-data-dir={profile_dir}")

    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    service = None
    if chromedriver_path and Path(chromedriver_path).is_file():
        service = Service(chromedriver_path)
    elif shutil.which("chromedriver"):
        service = Service(shutil.which("chromedriver"))
    else:
        try:
            service = Service(ChromeDriverManager().install())
        except Exception:
            service = None

    try:
        if service:
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)
    except Exception:
        try:
            driver = webdriver.Chrome(options=options)
        except Exception:
            if profile_dir:
                shutil.rmtree(profile_dir, ignore_errors=True)
            raise

    return driver, profile_dir


def get_request_token():
    try:
        driver, chrome_profile_dir = _create_driver()
    except Exception as e:
        print(f"❌ Failed to initialize Chrome driver: {e}")
        return None

    try:
        login_url = (
            "https://kite.zerodha.com/connect/login?v=3"
            f"&api_key={kite_credentials.api_key}"
        )
        print(f"🌐 Opening Kite login: {login_url}")
        driver.get(login_url)
        wait = WebDriverWait(driver, WAIT_SECONDS)

        # Check for immediate redirect (if session was already active)
        initial_token = _request_token_from_url(driver.current_url)
        if initial_token:
            print("✅ Already authenticated; request token retrieved.")
            return initial_token

        # Check for initial page errors (e.g. invalid API key)
        init_err = _extract_page_errors(driver)
        if init_err:
            print(f"⚠️ Page alert on load: {init_err}")

        def submit_credentials():
            username = wait.until(EC.element_to_be_clickable((By.ID, "userid")))
            username.clear()
            username.send_keys(kite_credentials.user_id)

            password = wait.until(EC.element_to_be_clickable((By.ID, "password")))
            password.clear()
            password.send_keys(kite_credentials.password)
            wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
            ).click()

        _retry_stale(submit_credentials, "credentials")
        print("🔑 Credentials submitted; checking response...")

        # Small pause for response/redirect
        time.sleep(1)

        # Check if already redirected after credential submit
        token_after_creds = _request_token_from_url(driver.current_url)
        if token_after_creds:
            print("✅ Request token retrieved immediately.")
            return token_after_creds

        # Check if Kite rejected the credentials (invalid username/password)
        creds_err = _extract_page_errors(driver)
        if creds_err:
            print(f"❌ Kite rejected credentials: {creds_err}")
            _save_debug_screenshot(driver, "credentials_error")
            return None

        totp_xpath = (
            "//input[@type='number' or @id='otp' or @type='text' "
            "or contains(@placeholder, 'OTP') or contains(@placeholder, 'TOTP')]"
        )

        for attempt in range(1, STALE_RETRIES + 1):
            request_token = _request_token_from_url(driver.current_url)
            if request_token:
                print("✅ Request token retrieved.")
                return request_token

            try:
                otp_input = wait.until(
                    EC.element_to_be_clickable((By.XPATH, totp_xpath))
                )
                otp_input.clear()
                totp_val = pyotp.TOTP(kite_credentials.totp_secret).now()
                otp_input.send_keys(totp_val)
                print("✅ TOTP entered; submitting...")

                # Kite often auto-submits on 6 digits; attempt button click if present
                time.sleep(0.5)
                try:
                    submit_btn = driver.find_elements(By.XPATH, "//button[@type='submit']")
                    if submit_btn and submit_btn[0].is_displayed() and submit_btn[0].is_enabled():
                        submit_btn[0].click()
                except Exception:
                    pass
                break
            except StaleElementReferenceException:
                if attempt == STALE_RETRIES:
                    raise
                print(f"ℹ️ Kite login form refreshed; checking TOTP result ({attempt}/{STALE_RETRIES}).")
                try:
                    request_token = WebDriverWait(driver, 8).until(
                        lambda current_driver: _request_token_from_url(
                            current_driver.current_url
                        )
                    )
                    print("✅ Request token retrieved.")
                    return request_token
                except TimeoutException:
                    continue

        try:
            request_token = wait.until(
                lambda current_driver: _request_token_from_url(current_driver.current_url)
            )
        except TimeoutException:
            totp_err = _extract_page_errors(driver)
            print(f"❌ Timed out waiting for Kite redirect. Current URL: {driver.current_url}")
            if totp_err:
                print(f"❌ Detected page alert: {totp_err}")
            _save_debug_screenshot(driver, "post_totp_timeout")
            return None

        if request_token:
            print("✅ Request token retrieved.")
        else:
            print("❌ Failed to retrieve request token. Check login details or TOTP.")
        
        return request_token

    except Exception as e:
        print(f"❌ Error during login: {type(e).__name__}: {e}")
        try:
            print(f"ℹ️ Page URL when error occurred: {driver.current_url}")
            print(f"ℹ️ Page Title: {driver.title}")
            err_msg = _extract_page_errors(driver)
            if err_msg:
                print(f"ℹ️ Visible Page Alert: {err_msg}")
            _save_debug_screenshot(driver, "login_exception")
        except Exception:
            pass
        return None

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if chrome_profile_dir:
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)

# Run the flow
if __name__ == "__main__":
    request_token = get_request_token()
    if not request_token:
        raise RuntimeError("Login failed: request_token is None")
    kite = KiteConnect(api_key=kite_credentials.api_key)
    data = kite.generate_session(request_token, api_secret=kite_credentials.api_secret)
    access_token = data["access_token"]
    kite_credentials.access_token = access_token
    ACCESS_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_TOKEN_PATH.write_text(access_token)

    print(f"Access token saved to {ACCESS_TOKEN_PATH}!")
