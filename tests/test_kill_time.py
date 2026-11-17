from unittest.mock import MagicMock

import pytest
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By

from Core.Kill_Time import (
    SEGMENT_IDS,
    _create_driver,
    get_request_token,
)


def _make_mock_element():
    el = MagicMock()
    el.is_displayed.return_value = True
    el.is_enabled.return_value = True
    return el


def test_create_driver_missing_binary(monkeypatch):
    monkeypatch.setenv("CHROME_BIN", "/nonexistent/chrome")
    monkeypatch.setenv("CHROMEDRIVER_PATH", "/nonexistent/chromedriver")

    with pytest.raises(RuntimeError, match="CHROME_BIN must point to the Chromium executable"):
        _create_driver()


def test_create_driver_missing_driver(tmp_path, monkeypatch):
    fake_chrome = tmp_path / "chrome"
    fake_chrome.write_text("binary")
    monkeypatch.setenv("CHROME_BIN", str(fake_chrome))
    monkeypatch.setenv("CHROMEDRIVER_PATH", "/nonexistent/chromedriver")

    with pytest.raises(RuntimeError, match="CHROMEDRIVER_PATH must point to the matching driver"):
        _create_driver()


def test_get_request_token_success(monkeypatch):
    mock_driver = MagicMock()
    mock_send = MagicMock()
    monkeypatch.setattr("Core.Kill_Time.send_telegram", mock_send)

    current_urls = [
        "https://console.zerodha.com/",
        "https://kite.zerodha.com/connect/login",
        "https://console.zerodha.com/dashboard",
        "https://console.zerodha.com/account/segment-activation",
    ]
    url_index = [0]

    def get_url():
        idx = min(url_index[0], len(current_urls) - 1)
        return current_urls[idx]

    type(mock_driver).current_url = property(lambda self: get_url())

    def advance_url(*args, **kwargs):
        url_index[0] += 1

    login_kite_btn = _make_mock_element()
    login_kite_btn.click.side_effect = advance_url

    userid_input = _make_mock_element()
    password_input = _make_mock_element()
    submit_btn = _make_mock_element()
    submit_btn.click.side_effect = advance_url

    otp_input = _make_mock_element()

    continue_btn = _make_mock_element()

    def on_continue_click():
        continue_btn.is_enabled.side_effect = StaleElementReferenceException()

    continue_btn.click.side_effect = on_continue_click

    confirm_btn = _make_mock_element()

    def on_confirm_click():
        confirm_btn.is_enabled.side_effect = StaleElementReferenceException()

    confirm_btn.click.side_effect = on_confirm_click

    label_mock = _make_mock_element()

    def mock_find_element(by, value):
        if by == By.ID and value == "userid":
            return userid_input
        if by == By.ID and value == "password":
            return password_input
        if by == By.XPATH and "Login with Kite" in value:
            return login_kite_btn
        if by == By.XPATH and value == "//button[@type='submit']":
            return submit_btn
        if by == By.XPATH and "Continue" in value:
            return continue_btn
        if "Confirm" in value or "Disable" in value:
            return confirm_btn
        if by == By.CSS_SELECTOR and "label[for=" in value:
            return label_mock
        if "input" in value and "otp" in value:
            return otp_input
        return _make_mock_element()

    def mock_find_elements(by, value):
        if by == By.ID and value == "password":
            if url_index[0] >= 2:
                return []
            return [password_input]
        if by == By.ID and value in SEGMENT_IDS:
            return [_make_mock_element()]
        if by == By.TAG_NAME and value == "button":
            return [continue_btn, confirm_btn]
        return [_make_mock_element()]

    mock_driver.find_element.side_effect = mock_find_element
    mock_driver.find_elements.side_effect = mock_find_elements

    segment_states = {s: True for s in SEGMENT_IDS}

    def mock_execute_script(script, *args):
        if "arguments[0].scrollIntoView" in script and "arguments[0].click()" in script:
            for s in SEGMENT_IDS:
                segment_states[s] = False
            return None
        if "toggle.getAttribute" in script:
            return segment_states["NSE_EQ"]
        if "return document.readyState" in script:
            return "complete"
        return None

    mock_driver.execute_script.side_effect = mock_execute_script

    result = get_request_token(driver=mock_driver)

    assert result is True
    mock_send.assert_called_once()
    assert "✅ Account Closed Successfully" in mock_send.call_args[0][0]


def test_get_request_token_failure(monkeypatch):
    mock_driver = MagicMock()
    mock_send = MagicMock()
    monkeypatch.setattr("Core.Kill_Time.send_telegram", mock_send)

    mock_driver.get.side_effect = RuntimeError("Connection timed out")

    result = get_request_token(driver=mock_driver)

    assert result is False
    mock_send.assert_called_once()
    assert "❌ Account Closure Failed" in mock_send.call_args[0][0]
    mock_driver.save_screenshot.assert_called()
