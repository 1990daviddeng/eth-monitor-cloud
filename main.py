import requests
import time
import numpy as np
from datetime import datetime
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# ==============================
# 🔐 填入你的 Supabase 信息
# ==============================


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==============================
# Binance API
# ==============================

BASE_URL = "https://fapi.binance.com"
SYMBOL = "ETHUSDT"
INTERVAL = "5m"

crowd_history = []
oi_history = []
price_history = []
volume_history = []

# ==============================
# 主循环
# ==============================

while True:
    try:
        # 获取K线
        kline = requests.get(
            f"{BASE_URL}/fapi/v1/klines",
            params={"symbol": SYMBOL, "interval": INTERVAL, "limit": 100},
        ).json()

        closes = [float(x[4]) for x in kline]
        volumes = [float(x[5]) for x in kline]
        price = closes[-1]

        # 获取OI
        oi = float(
            requests.get(
                f"{BASE_URL}/fapi/v1/openInterest",
                params={"symbol": SYMBOL},
            ).json()["openInterest"]
        )

        # 获取多空比
        long_ratio = float(
            requests.get(
                f"{BASE_URL}/futures/data/globalLongShortAccountRatio",
                params={"symbol": SYMBOL, "period": "5m", "limit": 1},
            ).json()[0]["longShortRatio"]
        )

        # CrowdScore
        crowd_score = oi * long_ratio

        crowd_history.append(crowd_score)
        oi_history.append(oi)
        price_history.append(price)
        volume_history.append(volumes[-1])

        # ==============================
        # 4H & 8H 计算（不改口径）
        # ==============================

        inc_4h = None
        inc_8h = None

        if len(crowd_history) >= 48:
            inc_4h = crowd_history[-1] - crowd_history[-48]

        if len(crowd_history) >= 96:
            inc_8h = crowd_history[-1] - crowd_history[-96]

        # ==============================
        # 成交量加速度（不改口径）
        # ==============================

        volume_acc = None
        if len(volume_history) >= 5:
            volume_acc = volume_history[-1] - volume_history[-5]

        # ==============================
        # 背离计算（不改口径）
        # ==============================

        divergence = None
        if len(oi_history) >= 2:
            oi_change = oi_history[-1] - oi_history[-2]
            price_change = price_history[-1] - price_history[-2]
            divergence = oi_change - price_change

        # ==============================
        # Z-score（不改口径）
        # ==============================

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

        # ==============================
        # 写入 Supabase
        # ==============================

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

        print("写入成功:", datetime.utcnow())

    except Exception as e:
        print("错误:", e)


    time.sleep(300)  # 每5分钟执行一次
