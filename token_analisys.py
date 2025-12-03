import pandas as pd
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# Leggi il CSV
df = pd.read_csv('memecoin.csv')
print(f"Righe totali nel dataset: {len(df)}")
print(f"\nValori mancanti originali:")
print(df[['launched_at', 'last_activity']].isnull().sum())

# Funzione per parsare le date rimuovendo "(stimato)" in modo sicuro
def parse_date_safe(date_str):
    if pd.isna(date_str):
        return pd.NaT
    try:
        # Rimuove "(stimato)" e spazi extra
        cleaned = str(date_str).replace('(stimato)', '').strip()
        return pd.to_datetime(cleaned, errors='coerce')
    except:
        return pd.NaT

# Parsa le date con gestione errori
df['launched_at_parsed'] = df['launched_at'].apply(parse_date_safe)
df['last_activity_parsed'] = pd.to_datetime(df['last_activity'], errors='coerce')

# Verifica quante date sono state parsate correttamente
print(f"\nDate di lancio parsate: {df['launched_at_parsed'].notna().sum()}/{len(df)}")
print(f"Date last_activity parsate: {df['last_activity_parsed'].notna().sum()}/{len(df)}")

# Filtra solo le righe con ENTRAMBE le date valide
df_clean = df.dropna(subset=['launched_at_parsed', 'last_activity_parsed']).copy()
print(f"\nRighe con entrambe le date valide: {len(df_clean)}")
print(f"Righe scartate: {len(df) - len(df_clean)}")

# Calcola la durata
df_clean['durata_timedelta'] = df_clean['last_activity_parsed'] - df_clean['launched_at_parsed']
df_clean['durata_ore'] = df_clean['durata_timedelta'].dt.total_seconds() / 3600
df_clean['durata_minuti'] = df_clean['durata_timedelta'].dt.total_seconds() / 60

# Filtra eventuali durate negative o anomale
durate_negative = (df_clean['durata_ore'] < 0).sum()
if durate_negative > 0:
    print(f"\nAttenzione: trovate {durate_negative} durate negative (last_activity prima di launched_at)")
    df_clean = df_clean[df_clean['durata_ore'] >= 0].copy()

print(f"\nRighe dopo rimozione durate negative: {len(df_clean)}")
print(f"\nStatistiche durata PRIMA della rimozione outlier (ore):")
print(df_clean['durata_ore'].describe())
'''
# ============================================================
# RIMOZIONE OUTLIER AL 1° E 99° PERCENTILE
# ============================================================
p1 = df_clean['durata_ore'].quantile(0.01)
p99 = df_clean['durata_ore'].quantile(0.99)

print(f"\n--- Rimozione Outlier ---")
print(f"1° percentile: {p1:.2f} ore ({p1*60:.2f} minuti)")
print(f"99° percentile: {p99:.2f} ore ({p99*60:.2f} minuti)")

# Filtra i dati mantenendo solo quelli tra p1 e p99
df_no_outliers = df_clean[
    (df_clean['durata_ore'] <= p99)
].copy()

outliers_rimossi = len(df_clean) - len(df_no_outliers)
print(f"\nOutlier rimossi: {outliers_rimossi} ({outliers_rimossi/len(df_clean)*100:.1f}%)")
print(f"Righe finali dopo rimozione outlier: {len(df_no_outliers)}")

print(f"\nStatistiche durata DOPO rimozione outlier (ore):")
print(df_no_outliers['durata_ore'].describe())

# Mostra alcuni esempi di outlier rimossi
if outliers_rimossi > 0:
    outliers_df = df_clean[
        (df_clean['durata_ore'] > p99)
    ]
    print(f"\n--- Esempi di outlier rimossi ---")
    print(f"Troppo brevi (< {p1:.2f}h):")
    print(outliers_df[outliers_df['durata_ore'] < p1][['Nome', 'durata_ore', 'durata_minuti']].head())
    print(f"\nTroppo lunghi (> {p99:.2f}h):")
    print(outliers_df[outliers_df['durata_ore'] > p99][['Nome', 'durata_ore']].head())

# Usa df_no_outliers per le tue analisi successive
df = df_no_outliers
print(f"\n✅ Dataset finale pronto per l'analisi: {len(df)} righe")
'''
df = df_clean
# ============================================
# STATISTICHE DESCRITTIVE
# ============================================
print("=" * 70)
print("ANALISI STATISTICA COMPLETA - SOPRAVVIVENZA TOKEN")
print("=" * 70)

print(f"\n📊 CAMPIONE ANALIZZATO")
print(f"   Numero totale di token: {len(df)}")

print(f"\n⏱️  STATISTICHE DURATA (in ore)")
print(f"   Media:              {df['durata_ore'].mean():.2f} ore")
print(f"   Mediana:            {df['durata_ore'].median():.2f} ore")
print(f"   Moda:               {df['durata_ore'].mode().values[0]:.2f} ore" if len(df['durata_ore'].mode()) > 0 else "   Moda: N/A")
print(f"   Deviazione std:     {df['durata_ore'].std():.2f} ore")
print(f"   Varianza:           {df['durata_ore'].var():.2f}")
print(f"   Minimo:             {df['durata_ore'].min():.2f} ore")
print(f"   Massimo:            {df['durata_ore'].max():.2f} ore")
print(f"   Range:              {df['durata_ore'].max() - df['durata_ore'].min():.2f} ore")

print(f"\n📈 QUARTILI")
print(f"   Q1 (25%):           {df['durata_ore'].quantile(0.25):.2f} ore")
print(f"   Q2 (50% - Mediana): {df['durata_ore'].quantile(0.50):.2f} ore")
print(f"   Q3 (75%):           {df['durata_ore'].quantile(0.75):.2f} ore")
print(f"   85th (85%):         {df['durata_ore'].quantile(0.85):.2f} ore")
print(f"   99th (99%):         {df['durata_ore'].quantile(0.99):.2f} ore")
print(f"   IQR:                {df['durata_ore'].quantile(0.75) - df['durata_ore'].quantile(0.25):.2f} ore")

print(f"\n⏰ STATISTICHE DURATA (in minuti)")
print(f"   Media:              {df['durata_minuti'].mean():.2f} minuti")
print(f"   Mediana:            {df['durata_minuti'].median():.2f} minuti")
print(f"   Deviazione std:     {df['durata_minuti'].std():.2f} minuti")

print(f"\n📉 ASIMMETRIA E CURTOSI")
print(f"   Skewness:           {df['durata_ore'].skew():.4f}")
print(f"   Kurtosis:           {df['durata_ore'].kurtosis():.4f}")

# Test di normalità
shapiro_stat, shapiro_p = stats.shapiro(df['durata_ore'])
print(f"\n🔬 TEST DI NORMALITÀ (Shapiro-Wilk)")
print(f"   Statistica:         {shapiro_stat:.4f}")
print(f"   P-value:            {shapiro_p:.4f}")
print(f"   Distribuzione:      {'Normale' if shapiro_p > 0.05 else 'Non normale'} (α=0.05)")

# Coefficiente di variazione
cv = (df['durata_ore'].std() / df['durata_ore'].mean()) * 100
print(f"\n📊 VARIABILITÀ")
print(f"   Coefficiente di variazione: {cv:.2f}%")

# ============================================
# ANALISI PER CATEGORIA
# ============================================
print(f"\n" + "=" * 70)
print("ANALISI PER TICKER")
print("=" * 70)
ticker_stats = df.groupby('Ticker').agg({
    'durata_ore': ['count', 'mean', 'median', 'std', 'min', 'max']
}).round(2)
print(ticker_stats)

# ============================================
# DETTAGLIO TOKEN
# ============================================
#print(f"\n" + "=" * 70)
#print("DETTAGLIO PER TOKEN (ordinati per durata)")
#print("=" * 70)
#df_sorted = df.sort_values('durata_ore', ascending=False)
#for idx, row in df_sorted.iterrows():
#    print(f"\n{row['Nome']} ({row['Ticker']})")
#    print(f"  🚀 Lancio:          {row['launched_at_parsed']}")
#    print(f"  ⏹️  Ultima attività: {row['last_activity_parsed']}")
#    print(f"  ⏱️  Durata:          {row['durata_ore']:.2f} ore ({row['durata_minuti']:.2f} minuti)")

# ============================================
# VISUALIZZAZIONI
# ============================================
fig, axes = plt.subplots(2, 3, figsize=(18, 12))
fig.suptitle('Analisi Distribuzione Sopravvivenza Token', fontsize=16, fontweight='bold')

# 1. Istogramma con KDE
axes[0, 0].hist(df['durata_ore'], bins=20, alpha=0.7, color='skyblue', edgecolor='black')
axes[0, 0].axvline(df['durata_ore'].mean(), color='red', linestyle='--', linewidth=2, label=f'Media: {df["durata_ore"].mean():.2f}h')
axes[0, 0].axvline(df['durata_ore'].median(), color='green', linestyle='--', linewidth=2, label=f'Mediana: {df["durata_ore"].median():.2f}h')
axes[0, 0].set_xlabel('Durata (ore)')
axes[0, 0].set_ylabel('Frequenza')
axes[0, 0].set_title('Distribuzione Durata Token')
axes[0, 0].legend()
axes[0, 0].grid(True, alpha=0.3)

# 2. Density plot
df['durata_ore'].plot(kind='density', ax=axes[0, 1], color='purple', linewidth=2)
axes[0, 1].set_xlabel('Durata (ore)')
axes[0, 1].set_ylabel('Densità')
axes[0, 1].set_title('Curva di Densità')
axes[0, 1].grid(True, alpha=0.3)

# 3. Box plot
box_data = axes[0, 2].boxplot(df['durata_ore'], patch_artist=True, 
                               boxprops=dict(facecolor='lightblue'),
                               medianprops=dict(color='red', linewidth=2))
axes[0, 2].set_ylabel('Durata (ore)')
axes[0, 2].set_title('Box Plot - Analisi Quartili')
axes[0, 2].grid(True, alpha=0.3)

# 4. Q-Q plot (normalità)
stats.probplot(df['durata_ore'], dist="norm", plot=axes[1, 0])
axes[1, 0].set_title('Q-Q Plot (Test Normalità)')
axes[1, 0].grid(True, alpha=0.3)

# 5. Bar plot per token
#df_sorted_top = df_sorted.head(10)
#axes[1, 1].barh(df_sorted_top['Nome'] + ' (' + df_sorted_top['Ticker'] + ')', 
#                df_sorted_top['durata_ore'], 
#                color='coral')
#axes[1, 1].set_xlabel('Durata (ore)')
#axes[1, 1].set_title('Top 10 Token per Durata')
#axes[1, 1].grid(True, alpha=0.3, axis='x')

# 6. Violin plot
parts = axes[1, 2].violinplot([df['durata_ore']], positions=[1], showmeans=True, showmedians=True)
for pc in parts['bodies']:
    pc.set_facecolor('lightgreen')
    pc.set_alpha(0.7)
axes[1, 2].set_ylabel('Durata (ore)')
axes[1, 2].set_title('Violin Plot - Distribuzione Completa')
axes[1, 2].set_xticks([1])
axes[1, 2].set_xticklabels(['Tutti i Token'])
axes[1, 2].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('analisi_token_completa.png', dpi=300, bbox_inches='tight')
print(f"\n" + "=" * 70)
print("📊 Grafici salvati in 'analisi_token_completa.png'")

# Salva risultati dettagliati
df_output = df[['Nome', 'Ticker', 'launched_at', 'last_activity', 'durata_ore', 'durata_minuti']]
df_output = df_output.sort_values('durata_ore', ascending=False)
df_output.to_csv('token_durata_analisi_dettagliata.csv', index=False)
print("💾 Risultati salvati in 'token_durata_analisi_dettagliata.csv'")
print("=" * 70)

plt.show()

# Calcolo base
df['launched_at_parsed'] = pd.to_datetime(df['launched_at'].str.replace('(stimato)', '').str.strip())
df['last_activity_parsed'] = pd.to_datetime(df['last_activity'])
df['durata_ore'] = (df['last_activity_parsed'] - df['launched_at_parsed']).dt.total_seconds() / 3600
df = df[np.isfinite(df['durata_ore'])]

# Rimuovi valori <= 0 prima di applicare scala logaritmica
df = df[df['durata_ore'] > 0]

# Statistiche
mean_val = df['durata_ore'].mean()
median_val = df['durata_ore'].median()
q3_val = df['durata_ore'].quantile(0.75)

# Crea plot
fig, ax = plt.subplots(figsize=(8, 6))
parts = ax.violinplot([df['durata_ore']],
                       positions=[1],
                       showmeans=False,
                       showmedians=False)

# Colori
for pc in parts['bodies']:
    pc.set_facecolor('lightgreen')
    pc.set_edgecolor('gray')
    pc.set_alpha(0.7)

# Linee
ax.axhline(mean_val, color='blue', linestyle='--', linewidth=1, label='Mean')
ax.axhline(median_val, color='orange', linestyle='--', linewidth=1, label='Median')
ax.axhline(q3_val, color='purple', linestyle='--', linewidth=1, label='75th percentile')

# SCALA LOGARITMICA
ax.set_yscale('log')

# Dettagli del grafico
ax.set_ylabel('Lifespan (hours)', fontsize=10)
ax.set_xticks([1])
ax.set_xticklabels(['Token'])
ax.grid(True, alpha=0.3, axis='y', which='both')  # 'both' mostra griglia per major e minor ticks

from matplotlib.ticker import LogLocator, LogFormatter

ax.yaxis.set_major_locator(LogLocator(base=10.0, numticks=10))
ax.yaxis.set_minor_locator(LogLocator(base=10.0, subs=np.arange(2, 10) * 0.1, numticks=10))

# Legenda posizionata più in basso
ax.legend(loc='upper right', frameon=False, fontsize=10, bbox_to_anchor=(0.98, 0.92))

plt.savefig('violin_plot_log_scale.png', dpi=300, bbox_inches='tight')
plt.show()

print(f"\nStatistiche durata (ore):")
print(f"N. token: {len(df)}")
print(f"Media: {mean_val:.2f}h")
print(f"Mediana: {median_val:.2f}h")
print(f"75° percentile: {q3_val:.2f}h")
print(f"Min: {df['durata_ore'].min():.2f}h")
print(f"Max: {df['durata_ore'].max():.2f}h")

