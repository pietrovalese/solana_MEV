import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# Dati aggiornati con 10 validatori
data = {
    "vote_account": [
        "26pV97Ce83ZQ6Kz",
        "3N7s9zXMZ4QqvHQ",
        "BT8LZUvQVwFHRGw",
        "DdCNGDpP7qMgoAy",
        "CvSb7wdQAFpHuSp",
        "CcaHc2L43ZWjwCH",
        "he1iusunGwqrNta",
        "CatzoSMUkTRidT5",
        "HZKopZYvv8v6un2",
        "F5b1wSUtpaYDnpj"
    ],
    "top10_pct": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 95.238095, 66.666667, 61.904762],
    "avg_30d_sandwich_rate": [1.385714, 1.257143, 55.623810, 2.0, 1.695238, 1.490476, 1.3, 1.565, 1.85, 8.469231]
}

# Creazione DataFrame
df = pd.DataFrame(data)

# Impostazioni per il plot
x = np.arange(len(df))
width = 0.4

plt.figure(figsize=(14, 6))

# Barre affiancate
plt.bar(x - width/2, df["top10_pct"], width, label="Top 10 Presence (%)", alpha=0.8)
plt.bar(x + width/2, df["avg_30d_sandwich_rate"], width, label="Avg 30d Sandwich Rate", alpha=0.8)

# Etichette e stile
plt.title("Top 10 Validators: Presence vs 30-Day Sandwich Rate")
plt.xlabel("Validator (vote_account)")
plt.ylabel("Values")
plt.xticks(x, df["vote_account"], rotation=45, ha="right")
plt.legend()
plt.grid(axis="y", linestyle="--", alpha=0.5)
plt.tight_layout()

plt.show()
