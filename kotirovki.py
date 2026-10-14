import requests
import pandas as pd

ticker = "SBER"
date_from = "2025-01-01"
date_to = "2025-12-31"

url = (
    "https://iss.moex.com/iss/history/engines/stock/"
    f"markets/shares/boards/TQBR/securities/{ticker}.json"
)

rows = []
start = 0

with requests.Session() as session:
    while True:
        response = session.get(
            url,
            params={
                "from": date_from,
                "till": date_to,
                "start": start,
                "iss.meta": "off",
                "iss.only": "history",
                "history.columns": (
                    "TRADEDATE,SECID,OPEN,HIGH,LOW,CLOSE,VOLUME,VALUE"
                ),
            },
            timeout=30,
        )
        response.raise_for_status()

        block = response.json()["history"]
        page = block["data"]

        if not page:
            break

        rows.extend(page)
        start += len(page)

df = pd.DataFrame(rows, columns=block["columns"])
filename = f"{ticker}_{date_from}_{date_to}.xlsx"
df.to_excel(filename, index=False)

print(f"Сохранено {len(df)} строк: {filename}")
