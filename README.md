# 🥪 Solana Sandwich & Arbitrage Analysis

**solana_sandwich** is a complete toolkit for **collecting, analyzing, and visualizing** data related to **sandwich attacks**, **arbitrage trades**, and **memecoin activity** on the **Solana** blockchain.  
The project integrates **Helius API** for transaction enrichment and supports an **automated end-to-end analysis and visualization pipeline**.

---

## 🔍 Main Features

- **Data Collection:**
  - `sandwich.py` → detects and saves **sandwich attacks** from [sandwiched.me](https://sandwiched.me)
  - `arbitrage.py` → collects **arbitrage trades** from [sandwiched.me](https://sandwiched.me)
  - `memecoin.py` and `memecoin_pumpfun.py` → monitor and store **memecoin-related data** in `.csv` format
  - `helius_rpc_details.py` → integrates with **Helius API** for Solana transaction enrichment

- **Analysis and Computation:**
  - The `analysis/` folder contains scripts for:
    - quantitative and statistical analysis of the datasets  
    - cross-comparison between sandwich, arbitrage, and memecoin data  
    - generation of consolidated datasets and metrics

- **Visualization and Plotting:**
  - The `plot/` folder includes scripts to generate **plots and visualizations** from the analyzed data  
  - Enables automated reporting and exploratory insights

---

## 📁 Project Structure

```
solana_sandwich/
├── analysis/               # Analysis scripts and data processing
├── plot/                   # Plotting and visualization scripts
├── .gitignore
├── README.md
├── requirements.txt         # Project dependencies
├── all_run.sh               # Automated run script
├── sandwich.py              # Sandwich attack data collector
├── arbitrage.py             # Arbitrage trade collector
├── memecoin.py              # Memecoin data collector
├── memecoin_pumpfun.py      # Memecoin tracking on pump.fun
├── helius_rpc_details.py    # Helius API integration
├── coinmarketcap.py         # Market data support
└── dataset/ (optional)      # Folder for generated JSON/CSV data
```

---

## ⚙️ Usage

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Collect Data

To gather sandwich and arbitrage data:

```bash
python3 sandwich.py
python3 arbitrage.py
```

To collect memecoin data:

```bash
python3 memecoin.py
python3 memecoin_pumpfun.py
```

### 3. Run Analysis

Execute the analysis scripts inside the `analysis/` folder:

```bash
python3 analysis/main_analysis.py
```

### 4. Generate Plots

Create plots and visual summaries:

```bash
python3 plot/main_plot.py
```

### 5. Automated Execution

Run the full pipeline automatically:

```bash
bash all_run.sh
```

---

## 🔗 Key Dependencies

- `requests`
- `pandas`
- `matplotlib`
- `beautifulsoup4`
- `tqdm`
- `helius` (API)
- `json`, `csv`

---

## 📊 Output Structure

- **Raw data** → stored in `.json` and `.csv` format  
- **Processed analysis** → stored in `analysis/results/`  
- **Plots and figures** → stored in `plot/output/`

---

## 🧭 Roadmap

- Extend support to additional Solana DEXs and data sources  
- Automate time-series analysis and anomaly detection  
- Add interactive dashboards for live analytics  

---

## 📜 License

This project is released under the **MIT License**.
