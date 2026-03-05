import requests
import time
import numpy as np
from datetime import datetime, timezone
from supabase import create_client
import os

print("===== ETH Monitor 启动 =====", flush=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ 环境变量未正确读取")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_URL = "https://fapi.binance.com"
SYMBOL = "ETHUSDT"
INTERVAL = "5m"

crowd_history = []
oi_history = []
price_history = []
volume_history = []

def safe_get_json(url, params):
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    return data

while True:
    try:
        print("开始新一轮采集:", datetime.now(timezone.utc), flush=True)

        # ========= KLINE =========
        kline = safe_get_json(
            f"{BASE_URL}/fapi/v1/klines",
            {"symbol": SYMBOL, "interval": INTERVAL, "limit": 100},
        )

        if not isinstance(kline, list):
            print("KLINE异常返回:", kline, flush=True)
            time.sleep(60)
            continue

        closes = [float(x[4]) for x in kline]
        volumes = [float(x[5]) for x in kline]
        price = closes[-1]

        # ========= OI =========
        oi_data = safe_get_json(
            f"{BASE_URL}/fapi/v1/openInterest",
            {"symbol": SYMBOL},
        )

        if "openInterest" not in oi_data:
            print("OI异常返回:", oi_data, flush=True)
            time.sleep(60)
            continue

        oi = float(oi_data["openInterest"])

        # ========= 多空比 =========
        ratio_data = safe_get_json(
            f"{BASE_URL}/futures/data/globalLongShortAccountRatio",
            {"symbol": SYMBOL, "period": "5m", "limit": 1},
        )

        if not isinstance(ratio_data, list) or len(ratio_data) == 0:
            print("多空比异常返回:", ratio_data, flush=True)
            time.sleep(60)
            continue

        long_ratio = float(ratio_data[0]["longShortRatio"])

        # ========= 后续计算（保持不变） =========
        crowd_score = oi * long_ratio

        crowd_history.append(crowd_score)
        oi_history.append(oi)
        price_history.append(price)
        volume_history.append(volumes[-1])

        inc_4h = crowd_history[-1] - crowd_history[-48] if len(crowd_history) >= 48 else None
        inc_8h = crowd_history[-1] - crowd_history[-96] if len(crowd_history) >= 96 else None
        volume_acc = volume_history[-1] - volume_history[-5] if len(volume_history) >= 5 else None

        divergence = None
        if len(oi_history) >= 2:
            divergence = (oi_history[-1] - oi_history[-2]) - (price_history[-1] - price_history[-2])

        crowd_z = None
        extreme_flag = None
        if len(crowd_history) >= 20:
            mean = np.mean(crowd_history)
            std = np.std(crowd_history)
            if std != 0:
                crowd_z = (crowd_score - mean) / std
                if crowd_z > 2:
                    extreme_flag = "极度拥挤-多"
                elif crowd_z < -2:
                    extreme_flag = "极度拥挤-空"

        data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "price": price,
            "open_interest": oi,
            "long_ratio": long_ratio,
            "inc_4h": inc_4h,
            "inc_8h": inc_8h,
            "volume_acc": volume_acc,
            "divergence": divergence,
            "crowd_z": crowd_z,
            "extreme_flag": extreme_flag,
        }

        supabase.table("eth_monitor").insert(data).execute()

        print("写入成功", flush=True)

    except Exception as e:
        print("发生未知错误:", e, flush=True)

    time.sleep(300)
