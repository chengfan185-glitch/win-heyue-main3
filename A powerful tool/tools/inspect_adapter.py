from pathlib import Path
import sys, inspect

# ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import execution.adapters.binance_um_futures as mod

print("module file:", getattr(mod, "__file__", "<none>"))
print("module repr:", repr(mod))

# show top-level names in module
print("\nmodule dir() preview:")
print([n for n in dir(mod) if not n.startswith("_")])

# Try to get the class and inspect it
cls = getattr(mod, "BinanceUMFuturesAdapter", None)
print("\nBinanceUMFuturesAdapter:", cls)
if cls is None:
    print("ERROR: BinanceUMFuturesAdapter not defined in module.")
else:
    print("\nAttributes on BinanceUMFuturesAdapter (public):")
    print([n for n in dir(cls) if not n.startswith("_")])
    try:
        src = inspect.getsource(cls)
        print("\n--- SOURCE of BinanceUMFuturesAdapter ---\n")
        print(src)
        print("\n--- end source ---\n")
    except Exception as e:
        print("Could not get source for class:", e)