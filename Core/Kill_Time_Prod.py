import time
from pathlib import Path
import pyotp
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import configparser
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import requests
from datetime import datetime
import tempfile
import shutil


DEFAULT_WAIT_SECONDS = 15
TRANSITION_WAIT_SECONDS = 6
FAST_POLL_SECONDS = 0.2
TELEGRAM_TIMEOUT_SECONDS = 2


# === Your Kite credentials ===

config = configparser.ConfigParser()

config_path = Path(__file__).parent.parent / "Cred" / "Cred_kite_PREM.ini"
config.read(config_path)

api_key = config['Kite']['api_key']
api_secret = config['Kite']['api_secret']
user_id = config['Kite']['user_id']
password = config['Kite']['password']
totp_secret = config['Kite']['totp_secret']  


# Telegram alert function
def send_telegram(message):
    BOT_TOKEN = config.get('Kite', 'BOT_TOKEN')
    CHAT_ID = config.get('Kite', 'CHAT_ID')

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.get(url, params=params, timeout=TELEGRAM_TIMEOUT_SECONDS)
        print("📩 Telegram alert sent")
    except Exception as e:
        print(f"❌ Telegram error: {e}")


def get_request_token():
    # Setup Chrome for Lightsail / Docker
    import os
    options = webdriver.ChromeOptions()
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    chrome_profile_dir = tempfile.mkdtemp(prefix="kite-close-chrome-")

    options.binary_location = chrome_bin
    options.page_load_strategy = "eager"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-sync")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--window-size=1365,768")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-data-dir={chrome_profile_dir}")

    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, DEFAULT_WAIT_SECONDS, poll_frequency=FAST_POLL_SECONDS)
    
    success = False

    def save_debug_screenshot(stage):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"debug_{stage}_{timestamp}.png"
        try:
            driver.save_screenshot(path)
            print(f"📸 Saved debug screenshot: {path}")
        except Exception as screenshot_error:
            print(f"⚠️ Could not save screenshot: {screenshot_error}")

    def click_with_retry(locator, step_name, attempts=3, timeout=DEFAULT_WAIT_SECONDS):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                element = WebDriverWait(
                    driver,
                    timeout,
                    poll_frequency=FAST_POLL_SECONDS,
                ).until(EC.element_to_be_clickable(locator))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                print(f"✅ {step_name} clicked (attempt {attempt}).")
                return element
            except Exception as e:
                last_error = e
                print(f"⚠️ {step_name} click attempt {attempt} failed: {e}")
                time.sleep(0.3)
        raise last_error

    def get_segment_toggle_state(segment_id):
        toggles = driver.find_elements(By.ID, segment_id)
        if not toggles:
            print(f"ℹ️ {segment_id} toggle not found; skipping.")
            return None

        return driver.execute_script(
            """
            const toggle = arguments[0];
            const label = document.querySelector(`label[for="${toggle.id}"]`);

            if (!label) return null;
            if (typeof toggle.checked === 'boolean') return toggle.checked;

            const state =
                toggle.getAttribute('aria-checked') ??
                toggle.getAttribute('data-checked') ??
                label.getAttribute('aria-checked') ??
                label.getAttribute('data-checked');

            if (state !== null && state !== undefined) {
                return ['true', 'checked', 'on', '1'].includes(String(state).toLowerCase());
            }

            return (
                label.classList.contains('active') ||
                label.classList.contains('checked') ||
                label.classList.contains('selected')
            );
            """,
            toggles[0],
        )

    def click_segment(segment_id):
        current_state = get_segment_toggle_state(segment_id)

        if current_state is None:
            return

        if not current_state:
            print(f"ℹ️ {segment_id} toggle is already OFF; skipping.")
            return

        locator = (By.XPATH, f"//label[@for='{segment_id}']")
        if not driver.find_elements(*locator):
            print(f"ℹ️ {segment_id} toggle label not found; skipping.")
            return

        segment_element = wait.until(EC.element_to_be_clickable(locator))
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
            segment_element,
        )
        wait.until(lambda _: get_segment_toggle_state(segment_id) in (False, None))
        print(f"✅ {segment_id} toggle was ON and is now OFF.")

    try:
        login_url = "https://console.zerodha.com/"
        driver.get(login_url)
        print(f"🌐 After opening login page: {driver.current_url}")

        # Click "Login with Kite"
        login_kite_btn = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Login with Kite')]") )
        )
        login_kite_btn.click()
        print(f"🌐 After clicking Login with Kite: {driver.current_url}")

        # Login step
        username = wait.until(EC.presence_of_element_located((By.ID, "userid")))
        username.send_keys(user_id)

        password_el = driver.find_element(By.ID, "password")
        password_el.send_keys(password)

        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        WebDriverWait(
            driver,
            TRANSITION_WAIT_SECONDS,
            poll_frequency=FAST_POLL_SECONDS,
        ).until(lambda d: not d.find_elements(By.ID, "password"))
        driver.switch_to.default_content()
        print(f"🌐 After password submit: {driver.current_url}")

        # TOTP step (with retry to avoid stale element issues)
        for attempt in range(3):
            try:
                totp = pyotp.TOTP(totp_secret).now()
                print(f"✅ TOTP: {totp}")

                totp_input = wait.until(
                    EC.element_to_be_clickable((By.ID, "userid"))
                )

                totp_input.clear()
                totp_input.send_keys(totp)

                driver.find_element(By.XPATH, "//button[@type='submit']").click()
                print(f"🌐 After TOTP submit: {driver.current_url}")
                break

            except Exception as e:
                print(f"Retrying TOTP... {attempt + 1}: {e}")
                time.sleep(0.5)

        # Wait for redirect back to console dashboard
        wait.until(
            lambda d: "console.zerodha.com/dashboard" in d.current_url
        )
        print(f"✅ Logged in successfully, current URL: {driver.current_url}")
        send_telegram(f"✅ Logged in successfully, current URL: {driver.current_url}")

        # Directly navigate to segment activation page
        driver.get("https://console.zerodha.com/account/segment-activation")
        print(f"🌐 Navigated to segment page: {driver.current_url}")

        # Wait for segment page to load
        wait.until(
            EC.presence_of_element_located((By.ID, "form_segment_manage"))
        )
        print("✅ Segment page loaded successfully")
    
        # clicking on nse equity
        try:
            click_segment("NSE_EQ")
        except Exception as e:
            print("❌ Error clicking NSE_EQ:")
            print(f"Exception: {e}")
            save_debug_screenshot("nse_eq_error")

        # click on bse equity
        try:
            click_segment("BSE_EQ")
        except Exception as e:
            print("❌ Error clicking BSE_EQ:")
            print(f"Exception: {e}")
            save_debug_screenshot("bse_eq_error")

        # click on nse fno
        try:
            click_segment("NSE_FO")
        except Exception as e:
            print("❌ Error clicking NSE_FO:")
            print(f"Exception: {e}")
            save_debug_screenshot("nse_fo_error")

        # click on bse fno
        try:
            click_segment("BSE_FO")
        except Exception as e:
            print("❌ Error clicking BSE_FO:")
            print(f"Exception: {e}")
            save_debug_screenshot("bse_fo_error")
                
        #Click on Commodity
        try:
            click_segment("NSE_COM")
        except Exception as e:
            print("❌ Error clicking NSE_COM:")
            print(f"Exception: {e}")
            save_debug_screenshot("nse_com_error")

        # Clicking on continue
        try:
            continue_btn = click_with_retry((
                By.XPATH, "//button[@class='btn btn-blue' and contains(text(), 'Continue ')]"
            ),  "Continue ")

            # Ensure transition to confirm stage before trying to click confirm.
            try:
                wait.until(EC.staleness_of(continue_btn))
            except TimeoutException:
                # Some flows keep the same modal/button node and update in-place.
                print("ℹ️ Confirm modal opened in-place; proceeding to final submit.")
        except Exception as e:
            print("❌ Failed to click Continue button:")
            print(f"Exception: {e}")
            save_debug_screenshot("continue_error")
            return None

        # Clicking on confirm-page continue button
        try:
            confirm_btn = click_with_retry((
                By.XPATH, "//button[@type='submit' and @class='btn btn-blue']"
            ), "Confirm")

            # Wait for post-submit state change instead of fixed sleep.
            try:
                wait.until(EC.staleness_of(confirm_btn))
            except TimeoutException:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            success = True
        except Exception as e:
            print("❌ Failed to click Confirm button:")
            print(f"Exception: {e}")
            save_debug_screenshot("confirm_error")
            return None
        

    except Exception as e:
        print(f"❌ Error during login: {e}")
        save_debug_screenshot("login_error")
        return None

    finally:
        if success:
            print("✅ Account Closed Successfully")
            send_telegram("✅ Account Closed Successfully")
        else:
            print("❌ Account Closure Failed")
            send_telegram("❌ Account Closure Failed")
        driver.quit()
        shutil.rmtree(chrome_profile_dir, ignore_errors=True)

# Run the flow
if __name__ == "__main__":
    get_request_token()
