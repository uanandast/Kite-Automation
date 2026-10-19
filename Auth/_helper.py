import os
import shutil
import tempfile
import time
from urllib.parse import parse_qs, urlparse

import pyotp
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from Cred._base import kite_credentials


class RequestToken:

    @staticmethod
    def get_request_token():
        # Setup Chrome
        chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
        chrome_profile_dir = tempfile.mkdtemp(prefix="kite-login-chrome-")

        options = webdriver.ChromeOptions()
        options.binary_location = chrome_bin
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--remote-debugging-port=0")
        options.add_argument(f"--user-data-dir={chrome_profile_dir}")

        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)

        try:
            login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={kite_credentials.api_key}"
            driver.get(login_url)

            wait = WebDriverWait(driver, 20)

            # Login step
            username = wait.until(EC.presence_of_element_located((By.ID, "userid")))
            username.send_keys(kite_credentials.user_id)

            password_el = driver.find_element(By.ID, "password")
            password_el.send_keys(kite_credentials.password)

            driver.find_element(By.XPATH, "//button[@type='submit']").click()
            time.sleep(5)
            driver.switch_to.default_content()

            # TOTP step (with retry to avoid stale element issues)
            for attempt in range(3):
                try:
                    totp = pyotp.TOTP(kite_credentials.totp_secret).now()
                    print(f"✅ TOTP: {totp}")

                    totp_input = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//input"))
                    )

                    totp_input.clear()
                    totp_input.send_keys(totp)

                    driver.find_element(By.XPATH, "//button[@type='submit']").click()
                    break

                except Exception:
                    print(f"Retrying TOTP... {attempt+1}")
                    time.sleep(2)

            # Wait for redirect with request_token
            wait.until(lambda d: "request_token" in d.current_url)
            current_url = driver.current_url

            if "request_token" not in current_url:
                raise Exception("Login failed: request_token not found")  # noqa: TRY002

            # Extract request_token from redirect URL
            parsed = urlparse(current_url)
            query = parse_qs(parsed.query)
            request_token = query.get("request_token", [None])[0]

            if request_token:
                print(f"✅ Request token: {request_token}")
            else:
                print("❌ Failed to retrieve request token. Check login details or TOTP.")
            
            return request_token

        except Exception as e:
            print(f"❌ Error during login: {e}")
            return None

        finally:
            driver.quit()
            shutil.rmtree(chrome_profile_dir, ignore_errors=True)