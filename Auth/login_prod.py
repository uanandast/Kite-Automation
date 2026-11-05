
from _helper import RequestToken
from kiteconnect import KiteConnect

from Cred._base import ACCESS_TOKEN_PATH, kite_credentials

# Run the flow
if __name__ == "__main__":
    request_token = RequestToken.get_request_token()
    if not request_token:
        raise Exception("Login failed: request_token is None")  # noqa: TRY002

    kite = KiteConnect(api_key=kite_credentials.api_key)
    data = kite.generate_session(request_token, api_secret=kite_credentials.api_secret)
    access_token = data["access_token"]
    kite_credentials.access_token = access_token
    ACCESS_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACCESS_TOKEN_PATH.write_text(access_token)

    print(f"Access token saved to {ACCESS_TOKEN_PATH}!")
