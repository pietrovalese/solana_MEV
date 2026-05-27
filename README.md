# 🥪 Solana Sandwich & Arbitrage Analysis

**solana_sandwich** is a complete toolkit for **collecting, analyzing, and visualizing** data related to **sandwich attacks**, **arbitrage trades**, and **memecoin activity** on the **Solana** blockchain.  
The project integrates **Helius API** for transaction enrichment and supports an **automated end-to-end analysis and visualization pipeline**.

---

## Main Features

- **Data Collection:**
  - `src/core/sandwich.py` → detects and saves **sandwich attacks** from [sandwiched.me](https://sandwiched.me)
  - `src/core/arbitrage.py` → collects **arbitrage trades** from [sandwiched.me](https://sandwiched.me)
  - `src/core/memecoin_pumpfun.py` → monitor and store **memecoin-related data** in `.csv` format
  - `src/core/helius_rpc_details.py` → integrates with **Helius API** for Solana transaction enrichment

- **Analysis and Computation:**
  - The `analysis/` folder contains scripts for:
    - quantitative and statistical analysis of the datasets  
    - cross-comparison between sandwich, arbitrage, and memecoin data  
    - generation of consolidated datasets and metrics

- **Detection and Validation:**
  - The `dataset/` folder includes scripts to download blocks and detect sandwiches attacks  
  - Based on rust implemnetation in `dataset/engine/lib.rs`

- **Validator behaviour analisys:**
  - The `core/validator/` folder includes scripts to compute metrics and detect malicious pattern

---

## 📁 Project Structure

```
solana_sandwich/
├── analysis/               # Analysis scripts and data processing
├── dataset/                   # Check and validate datset
├── src/         # Market data support
    |── core/
        |── sandwich.py
        |── arbitrage.py
        |── helius_rpc_details.py
        |── memecoin_pumpfun.py
    |── validator/
├── .gitignore
├── README.md
├── requirements.txt         # Project dependencies
├── all_run.sh               # Automated run script
```

---

## Dependecies

### 1. Create virtual environment
```bash
python3 -m venv venv
```
Activate the environment
```bash
source ./venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

---

## ⚙️ Usage

### 1. Collect and Enhance Data
To gather sandwich, arbitrage and memcoin data:
```bash
python3 scr/core/sandwich.py
python3 src/core/arbitrage.py
python3 src/core/memecoin_pumpfun.py
```

To enhance both sandwiches and arbitrages data:
```bash
python3 scr/core/helius_rpc_details.py
```

### 2. Run Analysis

Execute the analysis scripts inside the `analisys/` folder:

```bash
python3 analysis/*_analysis.py
```
---

## Output Structure

- **Raw data** → stored in `.jsonl` and `.csv` format  
- **Processed analysis** → stored in `analysis/results/`  

---

## Roadmap

- Extend support to additional Solana DEXs and data sources  
- Automate time-series analysis and anomaly detection  
- Add interactive dashboards for live analytics  

---

## License

This project is released under the **MIT License**.
