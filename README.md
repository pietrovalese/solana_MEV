# 🥪 solana_sandwich

**solana_sandwich** is a tool for monitoring and analyzing **sandwich attacks** on the **Solana** blockchain.  
It performs **web scraping** from multiple sources — including [sandwiched.me](https://sandwiched.me), [solscan.io](https://solscan.io), and [solanaFM.com](https://solanafm.com) — and saves all detected sandwich attack data in **JSON** format for further analysis and visualization.

---

## 🔍 Features

- Automated scraping of sandwich attack data from:
  - [sandwiched.me](https://sandwiched.me)
  - [solscan.io](https://solscan.io)
  - [solanaFM.com](https://solanafm.com)
- Structured export of data in `.json` format
- Tools for analyzing and identifying attack patterns
- Easy-to-use script for visualizing the extracted data

---

## 🚀 How to Use

### 1. Run the Scraper

To collect sandwich attack data and export it as JSON:

```bash
python3 sandwich.py
```

### 2. Run the data visualizer 

To visualize through a web dashboard the data in the json file:

```bash
python3 read_sandwich.py
```

---

## 📁 Project Structure

solana_sandwich/
├── sandwich.py          # Web scraper for sandwiched.me, solscan.io, and solanaFM.com
├── read_sandwich.py     # Script for web-based visualization of sandwich attack data
├── assets/                # Folder containing the css file to configure the web dashboard
|── README.md            # Project documentation
└── sandwich.json            # Json dataset

---