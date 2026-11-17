"""Disable currently enabled Zerodha account segments.

Runs locally and in the Lightsail Docker image. In Docker, Chromium and its
matching driver are supplied by CHROME_BIN and CHROMEDRIVER_PATH.
"""

import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure project root is in sys.path so core and cred can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pyotp
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

try:
    from core.send_notification import send_telegram
except ModuleNotFoundError:
    from send_notification import send_telegram

from cred._base import kite_credentials

DEFAULT_WAIT_SECONDS = 15
TRANSITION_WAIT_SECONDS = 6
FAST_POLL_SECONDS = 0.2
SEGMENT_IDS = ("NSE_EQ", "BSE_EQ", "NSE_FO", "BSE_FO", "NSE_COM")
IST = ZoneInfo("Asia/Kolkata")


def log_event(message, started_at=None):
    """Write an IST timestamp and, when supplied, the elapsed phase duration."""
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    duration = "" if started_at is None else f" | elapsed: {time.perf_counter() - started_at:.2f}s"
    print(f"[{timestamp}]{duration} {message}")


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


def get_request_token(driver=None):
    external_driver = driver is not None
    chrome_profile_dir = None
    success = False
    run_started_at = time.perf_counter()
    log_event("Account-closure flow started.")

    try:
        if driver is None:
            browser_started_at = time.perf_counter()
            driver, chrome_profile_dir = _create_driver()
            log_event("Browser started.", browser_started_at)
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
            action_started_at = time.perf_counter()
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
                    log_event(f"{name} clicked (attempt {attempt}).", action_started_at)
                    return element
                except Exception as error:
                    last_error = error
                    log_event(
                        f"{name} click attempt {attempt} failed: {error}", action_started_at
                    )
                    time.sleep(0.3)
            raise last_error

        def click_confirm_button():
            """Locate and click the final confirmation button in the modal or prompt."""
            candidate_locators = [
                # 1. Any button inside an active modal/dialog/popup with Confirm, Disable, Continue, Proceed, or Yes
                (
                    By.XPATH,
                    (
                        "//*[contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'popup') or @role='dialog']"
                        "//button[contains(normalize-space(.), 'Confirm') or contains(normalize-space(.), 'Disable') or "
                        "contains(normalize-space(.), 'Continue') or contains(normalize-space(.), 'Proceed') or "
                        "contains(normalize-space(.), 'Yes') or contains(@class, 'btn-blue')]"
                    ),
                ),
                # 2. Any button on the page explicitly reading Confirm, Disable, or Proceed
                (
                    By.XPATH,
                    "//button[contains(normalize-space(.), 'Confirm') or contains(normalize-space(.), 'Disable') or contains(normalize-space(.), 'Proceed')]",
                ),
                # 3. Action button with btn-blue
                (
                    By.XPATH,
                    "//button[contains(@class, 'btn-blue') and (@type='submit' or @type='button')]",
                ),
                # 4. Standard submit button fallback
                (By.XPATH, "//button[@type='submit']"),
            ]

            last_err = None
            for locator in candidate_locators:
                try:
                    btn = WebDriverWait(driver, 4, poll_frequency=FAST_POLL_SECONDS).until(
                        EC.element_to_be_clickable(locator)
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)
                    log_event(f"Confirm button clicked using locator: {locator[1]}")
                    return btn
                except Exception as err:
                    last_err = err
                    continue

            # Diagnostics: log all visible buttons on page to identify the current modal structure
            try:
                buttons = driver.find_elements(By.TAG_NAME, "button")
                btn_info = [
                    f"<{b.tag_name} type='{b.get_attribute('type')}' class='{b.get_attribute('class')}'>{b.text.strip()}</button>"
                    for b in buttons
                    if b.is_displayed()
                ]
                print(f"⚠️ Visible buttons on page when confirm failed: {btn_info}")
            except Exception as inspect_err:
                print(f"Could not inspect visible buttons: {inspect_err}")
            screenshot("confirm_error")
            raise last_err or TimeoutException("Confirmation button not found in modal.")

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
            segment_started_at = time.perf_counter()
            if not segment_is_enabled(segment_id):
                log_event(f"{segment_id} is already OFF; skipping.", segment_started_at)
                return
            label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, f"label[for='{segment_id}']")))
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", label
            )
            wait.until(lambda _: segment_is_enabled(segment_id) in (False, None))
            log_event(f"{segment_id} is now OFF.", segment_started_at)

        login_started_at = time.perf_counter()
        log_event("Opening Zerodha Console login page.")
        driver.get("https://console.zerodha.com/")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Login with Kite')]"))).click()
        log_event("Kite login form opened.", login_started_at)
        credentials_started_at = time.perf_counter()
        wait.until(EC.presence_of_element_located((By.ID, "userid"))).send_keys(kite_credentials.user_id)
        driver.find_element(By.ID, "password").send_keys(kite_credentials.password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        WebDriverWait(driver, TRANSITION_WAIT_SECONDS, poll_frequency=FAST_POLL_SECONDS).until(
            lambda current: not current.find_elements(By.ID, "password")
        )
        log_event("Credentials submitted; waiting for TOTP.", credentials_started_at)

        totp_started_at = time.perf_counter()
        log_event("Starting TOTP verification.")
        for attempt in range(1, 4):
            try:
                # The 2FA screen input on Kite is number/otp, not userid.
                otp_input = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//input[@type='number' or @id='otp' or contains(@placeholder, 'OTP') or contains(@placeholder, 'TOTP')]",
                        )
                    )
                )
                otp_input.clear()
                otp_input.send_keys(pyotp.TOTP(kite_credentials.totp_secret).now())
                click_with_retry((By.XPATH, "//button[@type='submit']"), "TOTP submit")
                WebDriverWait(
                    driver, DEFAULT_WAIT_SECONDS, poll_frequency=FAST_POLL_SECONDS
                ).until(
                    lambda current: "console.zerodha.com" in current.current_url
                    and "kite.zerodha.com" not in current.current_url
                )
                log_event("TOTP accepted; signed in to Zerodha Console.", totp_started_at)
                break
            except (StaleElementReferenceException, TimeoutException) as error:
                if (
                    "console.zerodha.com" in driver.current_url
                    and "kite.zerodha.com" not in driver.current_url
                ):
                    break
                if attempt == 3:
                    raise
                print(f"Kite refreshed during TOTP; retrying ({attempt}/3): {error}")
                time.sleep(0.5)

        wait.until(
            lambda current: "console.zerodha.com" in current.current_url
            and "kite.zerodha.com" not in current.current_url
        )
        segment_page_started_at = time.perf_counter()
        log_event("Opening account segment-activation page.")
        driver.get("https://console.zerodha.com/account/segment-activation")
        wait.until(EC.presence_of_element_located((By.ID, "form_segment_manage")))
        log_event("Segment-activation page loaded.", segment_page_started_at)
        for segment_id in SEGMENT_IDS:
            try:
                disable_segment(segment_id)
            except Exception as error:
                print(f"Could not disable {segment_id}: {error}")
                screenshot(f"{segment_id.lower()}_error")

        continue_started_at = time.perf_counter()
        log_event("Submitting selected segment changes.")
        continue_button = click_with_retry(
            (By.XPATH, "//button[contains(@class, 'btn-blue') and contains(normalize-space(.), 'Continue')]"),
            "Continue",
        )
        try:
            wait.until(EC.staleness_of(continue_button))
        except TimeoutException:
            print("Confirm modal opened in place; proceeding to confirmation.")
        log_event("Confirmation dialog ready.", continue_started_at)

        confirm_started_at = time.perf_counter()
        log_event("Confirming account-segment closure.")
        confirm_button = click_confirm_button()
        try:
            wait.until(EC.staleness_of(confirm_button))
        except TimeoutException:
            wait.until(lambda current: current.execute_script("return document.readyState") == "complete")
        success = True
        log_event("Account-segment closure confirmed.", confirm_started_at)
    except Exception as error:
        log_event(f"Account closure failed: {error}", run_started_at)
        if driver:
            screenshot("closure_failed")
    finally:
        message = "Account Closed Successfully" if success else "Account Closure Failed"
        log_event(message, run_started_at)
        try:
            send_telegram(("✅ " if success else "❌ ") + message)
        except Exception as error:
            print(f"Could not send Telegram notification: {error}")
        if driver and not external_driver:
            driver.quit()
        if chrome_profile_dir:
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)
    return success


if __name__ == "__main__":
    get_request_token()
