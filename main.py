import requests
import time
import numpy as np
from datetime import datetime
from supabase import create_client
import os

print("===== ETH Monitor 启动 =====", flush=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ 环境变量未正确读取")

print("环境变量读取成功", flush=True)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("Supabase 初始化成功", flush=True)

BASE_URL = "https://fapi.binance.com"
SYMBOL = "ETHUSDT"
INTERVAL = "5m"

crowd_history = []
oi_history = []
price_history = []
volume_history = []

while True:
    try:
        print("开始新一轮采集:", datetime.utcnow(), flush=True)

        kline = requests.get(
            f"{BASE_URL}/fapi/v1/klines",
            params={"symbol": SYMBOL, "interval": INTERVAL, "limit": 100},
            timeout=15
        ).json()

        closes = [float(x[4]) for x in kline]
        volumes = [float(x[5]) for x in kline]
        price = closes[-1]

        oi = float(
            requests.get(
                f"{BASE_URL}/fapi/v1/openInterest",
                params={"symbol": SYMBOL},
                timeout=15
            ).json()["openInterest"]
        )

        long_ratio = float(
            requests.get(
                f"{BASE_URL}/futures/data/globalLongShortAccountRatio",
                params={"symbol": SYMBOL, "period": "5m", "limit": 1},
                timeout=15
            ).json()[0]["longShortRatio"]
        )

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
            "time": datetime.utcnow().isoformat(),
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

        print("写入成功:", datetime.utcnow(), flush=True)

    except Exception as e:
        print("发生错误:", e, flush=True)

    time.sleep(300)

