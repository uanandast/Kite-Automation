import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pyotp
from kiteconnect import KiteConnect
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from Cred._base import ACCESS_TOKEN_PATH, kite_credentials


def get_request_token():
    # Use the system Chromium/ChromeDriver supplied by Docker when available.
    # webdriver-manager can download a driver that is incompatible with the
    # Chromium version installed in the image.
    chrome_bin = os.getenv("CHROME_BIN")
    chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
    chrome_profile_dir = None
    options = webdriver.ChromeOptions()
    if chrome_bin:
        options.binary_location = chrome_bin
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--remote-debugging-port=0")
        chrome_profile_dir = tempfile.mkdtemp(prefix="kite-login-chrome-")
        options.add_argument(f"--user-data-dir={chrome_profile_dir}")
    else:
        options.add_argument("--start-maximized")

    if chromedriver_path and Path(chromedriver_path).is_file():
        service = Service(chromedriver_path)
    else:
        service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        login_url = (
            "https://kite.zerodha.com/connect/login?v=3"
            f"&api_key={kite_credentials.api_key}"
        )
        driver.get(login_url)

        # Wait and login
        time.sleep(2)
        driver.find_element(By.ID, "userid").send_keys(kite_credentials.user_id)
        driver.find_element(By.ID, "password").send_keys(kite_credentials.password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        # Wait for TOTP screen
        time.sleep(2)
        otp = pyotp.TOTP(kite_credentials.totp_secret).now()
        driver.find_element(By.XPATH, "//input[@type='number']").send_keys(otp)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        # Wait for redirect
        time.sleep(5)
        current_url = driver.current_url

        # Extract request_token from redirect URL
        parsed = urlparse(current_url)
        query = parse_qs(parsed.query)
        request_token = query.get("request_token", [None])[0]

        if request_token:
            print("✅ Request token retrieved.")
        else:
            print("❌ Failed to retrieve request token. Check login details or TOTP.")
        
        return request_token

    except Exception as e:
        print(f"❌ Error during login: {e}")
        return None

    finally:
        driver.quit()
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
