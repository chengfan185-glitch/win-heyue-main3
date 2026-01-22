from pathlib import Path
import sys

# Add project root to sys.path so `execution` package can be imported
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
print("Added to sys.path:", str(ROOT))

from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter

def main():
    a = BinanceUMFuturesAdapter('live')
    print("test_connection =", a.test_connection())
    print("ts =", a._ts())

if __name__ == "__main__":
    main()