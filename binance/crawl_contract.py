"""Fetch eligible Binance USD-M contracts and refresh monitor symbols."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


FUTURES_API_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SPOT_API_URL = "https://api.binance.com/api/v3/exchangeInfo"
SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_CONFIG_PATH = SCRIPT_DIR / "Contract.json"
CONTRACT_SNAPSHOT_PATH = SCRIPT_DIR / "contract_symbols.json"


def fetch_exchange_info(api_url: str) -> dict[str, object]:
	request = Request(api_url, headers={"User-Agent": "binance-contract-crawler/1.0"})
	with urlopen(request, timeout=30) as response:
		payload = json.load(response)

	if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
		raise ValueError(f"Binance exchangeInfo response has no symbols list: {api_url}")

	return payload


def fetch_contracts() -> tuple[list[dict[str, str]], int, int, int]:
	futures_payload = fetch_exchange_info(FUTURES_API_URL)
	spot_payload = fetch_exchange_info(SPOT_API_URL)
	futures_symbols = futures_payload["symbols"]
	spot_entries = spot_payload["symbols"]

	# 現貨基準：只接受狀態為 TRADING、且以 USDT 計價的現貨交易對。
	spot_symbols = {
		item["symbol"]
		for item in spot_entries
		if item.get("quoteAsset") == "USDT" and item.get("status") == "TRADING"
	}

	# 期貨基準：只接受可交易、USDT 計價、COIN 類的 PERPETUAL；
	# 並要求同一 symbol 也存在於上面的現貨清單，季度交割合約因此排除。
	contracts = [
		{
			"symbol": item["symbol"],
			"baseAsset": item["baseAsset"],
			"contractType": item["contractType"],
		}
		for item in futures_symbols
		if item.get("quoteAsset") == "USDT"
		and item.get("status") == "TRADING"
		and item.get("underlyingType") == "COIN"
		and item.get("contractType") == "PERPETUAL"
		and item.get("symbol") in spot_symbols
	]
	contracts.sort(key=lambda item: item["symbol"])

	if not contracts:
		raise ValueError("Binance returned no perpetual contracts with matching active USDT spot pairs")

	return (
		contracts,
		int(futures_payload["serverTime"]),
		int(spot_payload["serverTime"]),
		len(spot_symbols),
	)


def write_json_atomically(path: Path, payload: dict[str, object]) -> None:
	temporary_path: Path | None = None
	try:
		with tempfile.NamedTemporaryFile(
			mode="w",
			encoding="utf-8",
			newline="\n",
			dir=path.parent,
			suffix=".tmp",
			delete=False,
		) as temporary_file:
			temporary_path = Path(temporary_file.name)
			json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
			temporary_file.write("\n")
		temporary_path.replace(path)
	finally:
		if temporary_path is not None and temporary_path.exists():
			temporary_path.unlink()


def main() -> None:
	contracts, futures_server_time_ms, spot_server_time_ms, spot_pair_count = fetch_contracts()
	symbols = [item["symbol"] for item in contracts]
	base_assets = sorted({item["baseAsset"] for item in contracts})
	futures_server_time = datetime.fromtimestamp(futures_server_time_ms / 1000, tz=timezone.utc)
	spot_server_time = datetime.fromtimestamp(spot_server_time_ms / 1000, tz=timezone.utc)

	with CONTRACT_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
		config = json.load(config_file)

	monitor_config = config.get("monitor")
	if not isinstance(monitor_config, dict):
		raise ValueError("Contract.json must contain a monitor object")

	monitor_config["symbols"] = symbols

	snapshot = {
		"source": FUTURES_API_URL,
		"spot_source": SPOT_API_URL,
		"server_time_utc": futures_server_time.isoformat(),
		"spot_server_time_utc": spot_server_time.isoformat(),
		"filters": {
			"quoteAsset": "USDT",
			"status": "TRADING",
			"underlyingType": "COIN",
			"contractType": "PERPETUAL",
			"requires_matching_spot_symbol": True,
			"spot_quoteAsset": "USDT",
			"spot_status": "TRADING",
		},
		"matching_spot_pair_count": spot_pair_count,
		"contract_count": len(contracts),
		"unique_base_asset_count": len(base_assets),
		"contract_types": sorted({item["contractType"] for item in contracts}),
		"contracts": contracts,
	}

	write_json_atomically(CONTRACT_SNAPSHOT_PATH, snapshot)
	write_json_atomically(CONTRACT_CONFIG_PATH, config)

	print(f"Binance futures server time: {futures_server_time.isoformat()}")
	print(f"Binance spot server time: {spot_server_time.isoformat()}")
	print(f"Active USDT spot pairs: {spot_pair_count}")
	print(f"Contract pairs: {len(symbols)}")
	print(f"Unique base assets: {len(base_assets)}")
	print(f"Updated: {CONTRACT_CONFIG_PATH}")
	print(f"Saved: {CONTRACT_SNAPSHOT_PATH}")


if __name__ == "__main__":
	try:
		main()
	except (OSError, URLError, ValueError, KeyError, json.JSONDecodeError) as error:
		raise SystemExit(f"Contract crawl failed: {error}") from error
