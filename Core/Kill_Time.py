"""Disable currently enabled Zerodha account segments.

Runs locally and in the Lightsail Docker image. In Docker, Chromium and its
matching driver are supplied by CHROME_BIN and CHROMEDRIVER_PATH.
"""

import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pyotp
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from Core.send_notification import send_telegram
from Cred._base import kite_credentials

DEFAULT_WAIT_SECONDS = 15
TRANSITION_WAIT_SECONDS = 6
FAST_POLL_SECONDS = 0.2
SEGMENT_IDS = ("NSE_EQ", "BSE_EQ", "NSE_FO", "BSE_FO", "NSE_COM")


def _create_driver():
    """Use Docker's pinned browser pair, or webdriver-manager for local runs."""
    chrome_bin = os.getenv("CHROME_BIN")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    options = webdriver.ChromeOptions()
    profile_dir = None

    if chrome_bin or chromedriver_path:
        if not chrome_bin or not Path(chrome_bin).is_file():
            raise RuntimeError("CHROME_BIN must point to the Chromium executable.")
        if not chromedriver_path or not Path(chromedriver_path).is_file():
            raise RuntimeError("CHROMEDRIVER_PATH must point to the matching driver.")
        options.binary_location = chrome_bin
        options.page_load_strategy = "eager"
        for argument in (
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--blink-settings=imagesEnabled=false",
            "--window-size=1365,768",
            "--remote-debugging-port=0",
        ):
            options.add_argument(argument)
        profile_dir = tempfile.mkdtemp(prefix="kite-close-chrome-")
        options.add_argument(f"--user-data-dir={profile_dir}")
        service = Service(chromedriver_path)
    else:
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())

    try:
        return webdriver.Chrome(service=service, options=options), profile_dir
    except Exception:
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)
        raise


def get_request_token():
    driver = None
    chrome_profile_dir = None
    success = False

    try:
        driver, chrome_profile_dir = _create_driver()
        wait = WebDriverWait(driver, DEFAULT_WAIT_SECONDS, poll_frequency=FAST_POLL_SECONDS)

        def screenshot(stage):
            path = f"debug_{stage}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.png"
            try:
                driver.save_screenshot(path)
                print(f"Saved debug screenshot: {path}")
            except Exception as error:
                print(f"Could not save debug screenshot: {error}")

        def click_with_retry(locator, name, attempts=3, timeout=DEFAULT_WAIT_SECONDS):
            last_error = None
            for attempt in range(1, attempts + 1):
                try:
                    element = WebDriverWait(driver, timeout, poll_frequency=FAST_POLL_SECONDS).until(
                        EC.element_to_be_clickable(locator)
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    try:
                        element.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", element)
                    print(f"{name} clicked (attempt {attempt}).")
                    return element
                except Exception as error:
                    last_error = error
                    print(f"{name} click attempt {attempt} failed: {error}")
                    time.sleep(0.3)
            raise last_error

        def segment_is_enabled(segment_id):
            toggle = driver.find_elements(By.ID, segment_id)
            if not toggle:
                print(f"{segment_id} toggle not found; skipping.")
                return None
            return driver.execute_script(
                """
                const toggle = arguments[0];
                const label = document.querySelector(`label[for="${toggle.id}"]`);
                if (!label) return null;
                if (typeof toggle.checked === 'boolean') return toggle.checked;
                const state = toggle.getAttribute('aria-checked') ?? toggle.getAttribute('data-checked') ??
                    label.getAttribute('aria-checked') ?? label.getAttribute('data-checked');
                if (state !== null) return ['true', 'checked', 'on', '1'].includes(String(state).toLowerCase());
                return label.classList.contains('active') || label.classList.contains('checked') ||
                    label.classList.contains('selected');
                """,
                toggle[0],
            )

        def disable_segment(segment_id):
            if not segment_is_enabled(segment_id):
                print(f"{segment_id} is already OFF; skipping.")
                return
            label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, f"label[for='{segment_id}']")))
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", label
            )
            wait.until(lambda _: segment_is_enabled(segment_id) in (False, None))
            print(f"{segment_id} is now OFF.")

        driver.get("https://console.zerodha.com/")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Login with Kite')]"))).click()
        wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(kite_credentials.user_id)
        driver.find_element(By.ID, "password").send_keys(kite_credentials.password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        WebDriverWait(driver, TRANSITION_WAIT_SECONDS, poll_frequency=FAST_POLL_SECONDS).until(
            lambda current: not current.find_elements(By.ID, "password")
        )

        for attempt in range(1, 4):
            try:
                otp_input = wait.until(EC.element_to_be_clickable((By.ID, "userid")))
                otp_input.clear()
                otp_input.send_keys(pyotp.TOTP(kite_credentials.totp_secret).now())
                driver.find_element(By.XPATH, "//button[@type='submit']").click()
                break
            except Exception as error:
                if attempt == 3:
                    raise
                print(f"Retrying TOTP ({attempt}/3): {error}")
                time.sleep(0.5)

        wait.until(lambda current: "console.zerodha.com/dashboard" in current.current_url)
        driver.get("https://console.zerodha.com/account/segment-activation")
        wait.until(EC.presence_of_element_located((By.ID, "form_segment_manage")))
        for segment_id in SEGMENT_IDS:
            try:
                disable_segment(segment_id)
            except Exception as error:
                print(f"Could not disable {segment_id}: {error}")
                screenshot(f"{segment_id.lower()}_error")

        continue_button = click_with_retry(
            (By.XPATH, "//button[contains(@class, 'btn-blue') and contains(normalize-space(.), 'Continue')]"),
            "Continue",
        )
        try:
            wait.until(EC.staleness_of(continue_button))
        except TimeoutException:
            print("Confirm modal opened in place; proceeding to confirmation.")
        confirm_button = click_with_retry(
            (By.XPATH, "//button[@type='submit' and contains(@class, 'btn-blue')]"), "Confirm"
        )
        try:
            wait.until(EC.staleness_of(confirm_button))
        except TimeoutException:
            wait.until(lambda current: current.execute_script("return document.readyState") == "complete")
        success = True
    except Exception as error:
        print(f"Account closure failed: {error}")
    finally:
        message = "Account Closed Successfully" if success else "Account Closure Failed"
        print(message)
        try:
            send_telegram(("✅ " if success else "❌ ") + message)
        except Exception as error:
            print(f"Could not send Telegram notification: {error}")
        if driver:
            driver.quit()
        if chrome_profile_dir:
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)


if __name__ == "__main__":
    get_request_token()
