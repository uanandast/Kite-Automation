"""Static risk-management configuration shared by Monitor operations."""

INDEX_STRIKE_STEP = {"BANKNIFTY": 100, "NIFTY": 50, "SENSEX": 100}
INDEX_FREEZE_QTY = {"NIFTY": 1755, "BANKNIFTY": 900, "SENSEX": 1000}

ACCOUNT_LOCK_POSITION_CHECK_SECONDS = 120
ACCOUNT_LOCK_POSITION_POLL_SECONDS = 2
# Positions refresh immediately after a WebSocket order update; this periodic
# REST call is the safety reconciliation if a WebSocket event is missed.
POSITION_RECONCILIATION_SECONDS = 2
MONITOR_LOOP_SECONDS = 0.2
MARGIN_BUFFER = 0.003
ALLOWED_OPTION_EXCHANGES = ("BFO", "NFO", "MCX")
