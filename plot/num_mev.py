import numpy as np
import pandas as pd
from scipy import stats

# Dati Sandwich
sandwich_data = {
    'epoch': [808, 809, 810, 811, 812, 813, 814, 815, 816, 817, 818, 819, 820, 821, 
              822, 823, 824, 825, 826, 827, 828, 829, 830, 831, 832, 833, 834, 835, 
              836, 837, 838, 839, 840, 841],
    'count': [2868, 2772, 3530, 2898, 2443, 3094, 3735, 3754, 3834, 5070, 6316, 7902, 
              6582, 6189, 2879, 7418, 9180, 8301, 6095, 4707, 5060, 7076, 4665, 4124, 
              2706, 4059, 3557, 4075, 3265, 4849, 5219, 4046, 4429, 4027]
}

# Dati Arbitraggi
arbitrage_data = {
    'epoch': [814, 815, 816, 817, 818, 819, 822, 823, 824, 825, 826, 827, 828, 829, 
              830, 831, 832, 833, 834, 835, 836],
    'count': [20237, 41597, 45417, 60396, 58006, 27384, 21659, 78477, 92471, 97889, 
              79243, 86644, 61820, 67542, 95054, 87952, 115479, 131501, 72220, 113956, 
              110325]
}

df_sandwich = pd.DataFrame(sandwich_data)
df_arbitrage = pd.DataFrame(arbitrage_data)

print("=" * 80)
print("ANALISI STATISTICA MEV - SOLANA BLOCKCHAIN")
print("=" * 80)
print()

# ============================================================================
# 1. STATISTICHE DESCRITTIVE
# ============================================================================

def calculate_statistics(data, name):
    """Calcola tutte le statistiche descrittive per un dataset"""
    values = data['count'].values
    
    stats_dict = {
        'N° Osservazioni': len(values),
        'Totale': np.sum(values),
        'Media': np.mean(values),
        'Mediana': np.median(values),
        'Moda': stats.mode(values, keepdims=True)[0][0],
        'Deviazione Standard': np.std(values, ddof=0),
        'Varianza': np.var(values, ddof=0),
        'Coefficiente di Variazione (%)': (np.std(values, ddof=0) / np.mean(values)) * 100,
        'Minimo': np.min(values),
        'Q1 (25° percentile)': np.percentile(values, 25),
        'Q2 (50° percentile - Mediana)': np.percentile(values, 50),
        'Q3 (75° percentile)': np.percentile(values, 75),
        'Massimo': np.max(values),
        'Range': np.max(values) - np.min(values),
        'IQR (Range Interquartile)': np.percentile(values, 75) - np.percentile(values, 25),
        'Rapporto Max/Min': np.max(values) / np.min(values),
        'Skewness (Asimmetria)': stats.skew(values),
        'Kurtosis (Curtosi)': stats.kurtosis(values)
    }
    
    return stats_dict

sandwich_stats = calculate_statistics(df_sandwich, 'Sandwich')
arbitrage_stats = calculate_statistics(df_arbitrage, 'Arbitraggi')

print("TABELLA 1: STATISTICHE DESCRITTIVE")
print("-" * 80)
print(f"{'Metrica':<35} {'Sandwich':>20} {'Arbitraggi':>20}")
print("-" * 80)

for key in sandwich_stats.keys():
    s_val = sandwich_stats[key]
    a_val = arbitrage_stats[key]
    
    if isinstance(s_val, (int, np.integer)):
        print(f"{key:<35} {s_val:>20,} {a_val:>20,}")
    else:
        print(f"{key:<35} {s_val:>20,.2f} {a_val:>20,.2f}")

print("-" * 80)
print()

# ============================================================================
# 2. ANALISI DI CORRELAZIONE
# ============================================================================

print("ANALISI DI CORRELAZIONE")
print("-" * 80)

# Merge sui dati per epoche comuni
df_merged = pd.merge(df_sandwich, df_arbitrage, on='epoch', suffixes=('_sandwich', '_arbitrage'))

print(f"Epoche comuni analizzate: {len(df_merged)}")
print(f"Range epoche: {df_merged['epoch'].min()} - {df_merged['epoch'].max()}")
print()

# Correlazione di Pearson
pearson_corr, pearson_pval = stats.pearsonr(df_merged['count_sandwich'], df_merged['count_arbitrage'])

# Correlazione di Spearman (per dati non-parametrici)
spearman_corr, spearman_pval = stats.spearmanr(df_merged['count_sandwich'], df_merged['count_arbitrage'])

print(f"Coefficiente di Pearson (r): {pearson_corr:.4f}")
print(f"P-value (Pearson): {pearson_pval:.4f}")
print(f"R² (varianza spiegata): {pearson_corr**2:.4f} ({pearson_corr**2 * 100:.2f}%)")
print()
print(f"Coefficiente di Spearman (ρ): {spearman_corr:.4f}")
print(f"P-value (Spearman): {spearman_pval:.4f}")
print()

# Interpretazione della correlazione
if pearson_corr > 0.7:
    interp = "FORTE POSITIVA - I fenomeni si muovono congiuntamente"
elif pearson_corr > 0.4:
    interp = "MODERATA POSITIVA - Relazione parziale tra i fenomeni"
elif pearson_corr > 0:
    interp = "DEBOLE POSITIVA - Scarsa relazione tra i fenomeni"
elif pearson_corr > -0.3:
    interp = "DEBOLE NEGATIVA - Scarsa relazione inversa"
else:
    interp = "MODERATA/FORTE NEGATIVA - Relazione inversa"

print(f"Interpretazione: {interp}")
print()

# Test di significatività
alpha = 0.05
if pearson_pval < alpha:
    print(f"✓ La correlazione è statisticamente significativa (p < {alpha})")
else:
    print(f"✗ La correlazione NON è statisticamente significativa (p >= {alpha})")

print("-" * 80)
print()

# ============================================================================
# 3. CONFRONTO QUANTITATIVO
# ============================================================================

print("CONFRONTO QUANTITATIVO TRA SANDWICH E ARBITRAGGI")
print("-" * 80)

# Rapporto medio
avg_ratio = arbitrage_stats['Media'] / sandwich_stats['Media']
print(f"Rapporto medio Arbitraggi/Sandwich: {avg_ratio:.2f}:1")
print(f"  → Per ogni sandwich si verificano circa {avg_ratio:.0f} arbitraggi")
print()

# Totali
total_sandwich = sandwich_stats['Totale']
total_arbitrage = arbitrage_stats['Totale']
total_mev = total_sandwich + total_arbitrage
print(f"Totale Sandwich: {total_sandwich:,.0f} ({total_sandwich/total_mev*100:.2f}% del MEV)")
print(f"Totale Arbitraggi: {total_arbitrage:,.0f} ({total_arbitrage/total_mev*100:.2f}% del MEV)")
print()

# Volatilità comparata
print("Volatilità (CV = Coefficiente di Variazione):")
print(f"  Sandwich: {sandwich_stats['Coefficiente di Variazione (%)']:.2f}%")
print(f"  Arbitraggi: {arbitrage_stats['Coefficiente di Variazione (%)']:.2f}%")

if arbitrage_stats['Coefficiente di Variazione (%)'] > sandwich_stats['Coefficiente di Variazione (%)']:
    diff_cv = arbitrage_stats['Coefficiente di Variazione (%)'] - sandwich_stats['Coefficiente di Variazione (%)']
    print(f"  → Gli arbitraggi sono più volatili di {diff_cv:.2f} punti percentuali")
else:
    diff_cv = sandwich_stats['Coefficiente di Variazione (%)'] - arbitrage_stats['Coefficiente di Variazione (%)']
    print(f"  → I sandwich sono più volatili di {diff_cv:.2f} punti percentuali")
print()

# Stabilità (Range Max/Min)
print("Stabilità (Rapporto Max/Min - valori più bassi = più stabile):")
print(f"  Sandwich: {sandwich_stats['Rapporto Max/Min']:.2f}x")
print(f"  Arbitraggi: {arbitrage_stats['Rapporto Max/Min']:.2f}x")
print()

# Distribuzione (IQR)
print("Concentrazione dei dati (IQR = Range Interquartile):")
print(f"  Sandwich: {sandwich_stats['IQR (Range Interquartile)']:.0f}")
print(f"  Arbitraggi: {arbitrage_stats['IQR (Range Interquartile)']:.0f}")
print(f"  → Il 50% delle epoche ha valori compresi in questo intervallo")
print()

# Picchi temporali
sandwich_peak_epoch = df_sandwich.loc[df_sandwich['count'].idxmax(), 'epoch']
sandwich_peak_value = df_sandwich['count'].max()
arbitrage_peak_epoch = df_arbitrage.loc[df_arbitrage['count'].idxmax(), 'epoch']
arbitrage_peak_value = df_arbitrage['count'].max()

print("Picchi di attività:")
print(f"  Sandwich: Epoca {int(sandwich_peak_epoch)} con {sandwich_peak_value:,} attacchi")
print(f"  Arbitraggi: Epoca {int(arbitrage_peak_epoch)} con {arbitrage_peak_value:,} operazioni")
print(f"  Sfasamento temporale: {abs(int(arbitrage_peak_epoch) - int(sandwich_peak_epoch))} epoche")

print("-" * 80)
print()

# ============================================================================
# 4. OUTPUT LATEX PER LA TESI
# ============================================================================

print("OUTPUT LATEX PER LA TESI")
print("-" * 80)
print()

latex_table = r"""
\begin{table}[H]
\centering
\begin{tabular}{lrr}
\hline
\textbf{Metrica} & \textbf{Sandwich} & \textbf{Arbitraggi} \\
\hline
N° Osservazioni & """ + f"{sandwich_stats['N° Osservazioni']:,}" + " & " + f"{arbitrage_stats['N° Osservazioni']:,}" + r""" \\
Totale Operazioni & """ + f"{sandwich_stats['Totale']:,.0f}" + " & " + f"{arbitrage_stats['Totale']:,.0f}" + r""" \\
Media & """ + f"{sandwich_stats['Media']:,.2f}" + " & " + f"{arbitrage_stats['Media']:,.2f}" + r""" \\
Mediana & """ + f"{sandwich_stats['Mediana']:,.2f}" + " & " + f"{arbitrage_stats['Mediana']:,.2f}" + r""" \\
Deviazione Standard & """ + f"{sandwich_stats['Deviazione Standard']:,.2f}" + " & " + f"{arbitrage_stats['Deviazione Standard']:,.2f}" + r""" \\
Coeff. di Variazione (\%) & """ + f"{sandwich_stats['Coefficiente di Variazione (%)']:.2f}" + " & " + f"{arbitrage_stats['Coefficiente di Variazione (%)']:.2f}" + r""" \\
Minimo & """ + f"{sandwich_stats['Minimo']:,.0f}" + " & " + f"{arbitrage_stats['Minimo']:,.0f}" + r""" \\
Q1 (25° percentile) & """ + f"{sandwich_stats['Q1 (25° percentile)']:,.0f}" + " & " + f"{arbitrage_stats['Q1 (25° percentile)']:,.0f}" + r""" \\
Q3 (75° percentile) & """ + f"{sandwich_stats['Q3 (75° percentile)']:,.0f}" + " & " + f"{arbitrage_stats['Q3 (75° percentile)']:,.0f}" + r""" \\
Massimo & """ + f"{sandwich_stats['Massimo']:,.0f}" + " & " + f"{arbitrage_stats['Massimo']:,.0f}" + r""" \\
Range & """ + f"{sandwich_stats['Range']:,.0f}" + " & " + f"{arbitrage_stats['Range']:,.0f}" + r""" \\
IQR & """ + f"{sandwich_stats['IQR (Range Interquartile)']:,.0f}" + " & " + f"{arbitrage_stats['IQR (Range Interquartile)']:,.0f}" + r""" \\
Rapporto Max/Min & """ + f"{sandwich_stats['Rapporto Max/Min']:.2f}" + " & " + f"{arbitrage_stats['Rapporto Max/Min']:.2f}" + r""" \\
\hline
\end{tabular}
\caption{Statistiche descrittive delle operazioni MEV per epoca}
\label{tab:statistiche_mev}
\end{table}
"""

print(latex_table)
print()

# ============================================================================
# 5. TESTO INTERPRETATIVO PER LA TESI
# ============================================================================

print("TESTO INTERPRETATIVO PER LA TESI")
print("-" * 80)
print()

interpretation = f"""
Il coefficiente di variazione (CV) permette di confrontare la variabilità relativa 
dei due fenomeni: un CV più elevato negli arbitraggi ({arbitrage_stats['Coefficiente di Variazione (%)']:.2f}%) 
rispetto ai sandwich ({sandwich_stats['Coefficiente di Variazione (%)']:.2f}%) indica una maggiore 
instabilità nelle opportunità di arbitraggio, probabilmente dovuta alla natura più 
reattiva di queste operazioni rispetto agli attacchi sandwich che richiedono condizioni 
di mercato più specifiche.

L'analisi dei quartili rivela che il 50% delle epoche presenta un numero di sandwich 
compreso tra {sandwich_stats['Q1 (25° percentile)']:,.0f} e {sandwich_stats['Q3 (75° percentile)']:,.0f}, 
con un intervallo interquartile di {sandwich_stats['IQR (Range Interquartile)']:,.0f}, mentre per gli 
arbitraggi l'intervallo è significativamente più ampio ({arbitrage_stats['IQR (Range Interquartile)']:,.0f}), 
confermando la maggiore volatilità di questo tipo di MEV.

Il coefficiente di correlazione di Pearson tra le due serie temporali è pari a 
r = {pearson_corr:.4f} (p-value = {pearson_pval:.4f}), indicando una correlazione {interp.lower()}.
Questo suggerisce che {"i due fenomeni rispondono a stimoli di mercato comuni" if pearson_corr > 0.5 else "i fenomeni sono guidati da dinamiche parzialmente indipendenti"}.

Il rapporto tra il valore massimo e minimo osservato (max/min ratio) è pari a 
{sandwich_stats['Rapporto Max/Min']:.2f} per i sandwich e {arbitrage_stats['Rapporto Max/Min']:.2f} per gli arbitraggi, 
indicando che le opportunità di arbitraggio presentano oscillazioni più marcate nel tempo.
"""

print(interpretation)