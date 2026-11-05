import os
import time
from datetime import datetime

import pyotp
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from send_notification import send_telegram
from webdriver_manager.chrome import ChromeDriverManager

from Cred._base import kite_credentials


def get_request_token():
    # Setup Brave Browser
    options = webdriver.ChromeOptions()
    options.binary_location = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    #options.add_argument("--start-maximized")
    options.add_argument("--headless")  # Run in background
    options.add_argument("--disable-gpu")  # Optional for compatibility
    options.add_argument("--no-sandbox")  # Optional for Linux
    options.add_argument("--window-size=1920,1080")  # Set standard size
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    success = False

    def save_debug_screenshot(stage):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # noqa: DTZ005
        path = f"debug_{stage}_{timestamp}.png"
        try:
            driver.save_screenshot(path)
            print(f"📸 Saved debug screenshot: {path}")
        except Exception as screenshot_error:
            print(f"⚠️ Could not save screenshot: {screenshot_error}")

    def click_with_retry(locator, step_name, attempts=3, timeout=15):
        last_error = None
        for attempt in range(1, attempts + 1):
            try:
                wait = WebDriverWait(driver, timeout)
                element = wait.until(EC.element_to_be_clickable(locator))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                time.sleep(0.3)
                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                print(f"✅ {step_name} clicked (attempt {attempt}).")
                return element
            except Exception as e:
                last_error = e
                print(f"⚠️ {step_name} click attempt {attempt} failed: {e}")
                time.sleep(1)
        raise last_error

    try:
        login_url = "https://kite.zerodha.com/"
        driver.get(login_url)

        # Wait and login
        time.sleep(2)
        driver.find_element(By.ID, "userid").send_keys(kite_credentials.user_id)
        driver.find_element(By.ID, "password").send_keys(kite_credentials.password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()

        # Wait for TOTP screen
        time.sleep(2)
        otp = pyotp.TOTP(kite_credentials.totp_secret).now()
        print(f"✅ TOTP: {otp}")
        driver.find_element(By.XPATH, "//input[@type='number']").send_keys(otp)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        time.sleep(2)

        driver.get("https://console.zerodha.com/account/segment-activation")
        time.sleep(2)
    
        # clicking on nse equity
        try:
            wait = WebDriverWait(driver, 10)
            segment_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//label[@for='NSE_EQ']"
            )))
            segment_element.click()
            print("✅ Segment clicked successfully.")
            time.sleep(1)
        except Exception as e:
            print("❌ Error clicking segment:")
            print(f"Exception: {e}")
            return
        
        # click on bse equity
        try:
            wait = WebDriverWait(driver, 10)
            segment_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//label[@for='BSE_EQ']"
            )))
            segment_element.click()
            print("✅ Segment clicked successfully.")
            time.sleep(1)
        except Exception as e:
            print("❌ Error clicking segment:")
            print(f"Exception: {e}")
            return



        # click on nse fno
        try:
            wait = WebDriverWait(driver, 10)
            segment_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//label[@for='NSE_FO']"
            )))
            segment_element.click()
            print("✅ Segment clicked successfully.")
            time.sleep(1)
        except Exception as e:
            print("❌ Error clicking segment:")
            print(f"Exception: {e}")
            return
        # click on bse fno
        try:
            wait = WebDriverWait(driver, 10)
            segment_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//label[@for='BSE_FO']"
            )))
            segment_element.click()
            print("✅ Segment clicked successfully.")
            time.sleep(1)
        except Exception as e:
            print("❌ Error clicking segment:")
            print(f"Exception: {e}")
            return
        
        # click on nse commodity
        try:
            wait = WebDriverWait(driver, 10)
            segment_element = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//label[@for='NSE_COM']"
            )))
            segment_element.click()
            print("✅ Segment clicked successfully.")
            time.sleep(1)
        except Exception as e:
            print("❌ Error clicking segment:")
            print(f"Exception: {e}")
            return


        # Clicking on continue
        try:
            continue_btn = click_with_retry((
                By.XPATH, "//button[@class='btn btn-blue' and contains(text(), 'Continue')]"
            ),  "Continue", timeout=20)

            # Ensure transition to confirm stage before trying to click confirm.
            wait = WebDriverWait(driver, 15)
            try:
                wait.until(EC.staleness_of(continue_btn))
            except TimeoutException:
                # Some flows keep the same modal/button node and update in-place.
                print("ℹ️ Confirm modal opened in-place; proceeding to final submit.")
        except Exception as e:
            print("❌ Failed to click Continue button:")
            print(f"Exception: {e}")
            save_debug_screenshot("continue_error")
            return

        # Clicking on confirm-page continue button
        try:
            confirm_btn = click_with_retry((
                By.XPATH, "//button[@type='submit' and @class='btn btn-blue']"
            ), "Confirm", timeout=20)

            # Wait for post-submit state change instead of fixed sleep.
            wait = WebDriverWait(driver, 20)
            try:
                wait.until(EC.staleness_of(confirm_btn))
            except TimeoutException:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            success = True
        except Exception as e:
            print("❌ Failed to click Confirm button:")
            print(f"Exception: {e}")
            save_debug_screenshot("confirm_error")
            return
        

    except Exception as e:
        print(f"❌ Error during login: {e}")
        save_debug_screenshot("login_error")
        return

    finally:
        if success:
            os.system('say "Account Closed Successfully"')
            send_telegram("✅ Account Closed Successfully")
        else:
            os.system('say "Account Closure Failed"')
            send_telegram("❌ Account Closure Failed")
        driver.quit()

# Run the flow
if __name__ == "__main__":
    get_request_token()
