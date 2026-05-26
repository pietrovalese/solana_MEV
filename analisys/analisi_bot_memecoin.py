import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from collections import defaultdict
from datetime import datetime
import os

# Configurazione stile grafici
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (15, 10)
plt.rcParams['font.size'] = 10
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
attack_path = os.path.join(BASE_DIR, "verified_attacks_complete.json")
# -------------------------
# CARICAMENTO DATI
# -------------------------
def load_verified_attacks(attack_path):
    """Carica e filtra solo gli attacchi verificati."""
    
    # Prova prima a caricare come singolo JSON
    try:
        with open(attack_path, 'r') as f:
            data = json.load(f)
        
        # Filtra solo attacchi verificati
        verified = [m for m in data['verified_matches'] if m['verification']['verified']]
        stats = data['statistics']
        
    except json.JSONDecodeError:
        # Se fallisce, prova a leggere come JSON multipli (JSONL style)
        print("⚠️  Rilevato formato multiplo, parsing avanzato...")
        
        with open(attack_path, 'r') as f:
            content = f.read()
        
        # Trova l'ultimo JSON valido (quello completo)
        import re
        
        # Cerca tutti i blocchi JSON
        json_blocks = []
        depth = 0
        current_block = ""
        
        for char in content:
            current_block += char
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and current_block.strip():
                    try:
                        block = json.loads(current_block.strip())
                        json_blocks.append(block)
                        current_block = ""
                    except:
                        pass
        
        if not json_blocks:
            raise ValueError("Nessun JSON valido trovato nel file")
        
        # Prendi l'ultimo (quello più completo)
        data = json_blocks[-1]
        verified = [m for m in data['verified_matches'] if m['verification']['verified']]
        stats = data['statistics']
    
    print(f"{'='*80}")
    print(f"CARICAMENTO DATI")
    print(f"{'='*80}")
    print(f"Attacchi totali nel file: {stats['total']}")
    print(f"Attacchi VERIFICATI: {len(verified)} ({len(verified)/stats['total']*100:.1f}%)")
    print(f"{'='*80}\n")
    
    return verified, stats

# -------------------------
# ANALISI DATI
# -------------------------
def analyze_attacks(verified_attacks):
    """Analizza gli attacchi verificati e crea statistiche."""
    
    # DataFrame principale
    df = pd.DataFrame([
        {
            'sandwich_id': a['sandwich_id'],
            'creator': a['creator_attacker_pubkey'],
            'creator_short': a['creator_attacker_pubkey'][:16] + '...',
            'token_name': a['memecoin']['nome'],
            'ticker': a['memecoin']['ticker'],
            'mint': a['memecoin']['mint'],
            'profit_sol': a['profit']['profit_sol'] or 0,
            'value_in': a['profit']['value_in'] or 0,
            'value_out': a['profit']['value_out'] or 0,
            'hours_after_launch': a['timing']['hours_after_launch'],
            'victims': a['victims_count'],
            'timestamp': datetime.fromisoformat(a['sandwich_datetime']),
            'pumpfun_link': a['memecoin']['pumpfun_link']
        }
        for a in verified_attacks
    ])
    
    # Statistiche per creatore
    creator_stats = df.groupby('creator').agg({
        'sandwich_id': 'count',
        'profit_sol': 'sum',
        'victims': 'sum',
        'ticker': lambda x: list(x)
    }).rename(columns={
        'sandwich_id': 'num_attacks',
        'profit_sol': 'total_profit',
        'victims': 'total_victims',
        'ticker': 'tokens'
    }).reset_index()
    
    creator_stats['avg_profit'] = creator_stats['total_profit'] / creator_stats['num_attacks']
    creator_stats['creator_short'] = creator_stats['creator'].str[:16] + '...'
    creator_stats = creator_stats.sort_values('total_profit', ascending=False)
    
    # Statistiche generali
    stats = {
        'total_attacks': len(df),
        'unique_creators': df['creator'].nunique(),
        'unique_tokens': df['ticker'].nunique(),
        'total_profit': df['profit_sol'].sum(),
        'avg_profit': df['profit_sol'].mean(),
        'median_profit': df['profit_sol'].median(),
        'max_profit': df['profit_sol'].max(),
        'total_victims': df['victims'].sum(),
        'avg_victims': df['victims'].mean(),
        'avg_timing_hours': df['hours_after_launch'].mean(),
        'median_timing_hours': df['hours_after_launch'].median()
    }
    
    return df, creator_stats, stats

# -------------------------
# VISUALIZZAZIONI
# -------------------------
def create_visualizations(df, creator_stats, stats):
    """Crea tutte le visualizzazioni grafiche."""
    
    fig = plt.figure(figsize=(20, 12))
    
    # -------------------------
    # 1. STATISTICHE GENERALI (Top)
    # -------------------------
    ax_text = plt.subplot(4, 3, (1, 3))
    ax_text.axis('off')
    
    summary_text = f"""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                    ANALISI ATTACCHI VERIFICATI                               ║
    ║              Creatori che hanno attaccato i propri token                     ║
    ╚══════════════════════════════════════════════════════════════════════════════╝
    
    📊 STATISTICHE GENERALI:
    
    • Attacchi verificati totali:        {stats['total_attacks']}
    • Creatori unici:                    {stats['unique_creators']}
    • Token unici attaccati:             {stats['unique_tokens']}
    • Vittime totali:                    {stats['total_victims']}
    
    💰 PROFITTI:
    
    • Profitto totale verificato:        {stats['total_profit']:.4f} SOL
    • Profitto medio per attacco:        {stats['avg_profit']:.4f} SOL
    • Profitto mediano:                  {stats['median_profit']:.4f} SOL
    • Profitto massimo:                  {stats['max_profit']:.4f} SOL
    
    ⏰ TIMING:
    
    • Tempo medio attacco dopo launch:   {stats['avg_timing_hours']:.2f} ore
    • Tempo mediano:                     {stats['median_timing_hours']:.2f} ore
    • Vittime medie per attacco:         {stats['avg_victims']:.1f}
    """
    
    ax_text.text(0.05, 0.95, summary_text, transform=ax_text.transAxes,
                 fontsize=11, verticalalignment='top', family='monospace',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    # -------------------------
    # 2. TOP 10 CREATORI PER PROFITTO
    # -------------------------
    ax1 = plt.subplot(4, 3, 4)
    top_creators = creator_stats.head(10)
    colors = plt.cm.Reds(np.linspace(0.4, 0.9, len(top_creators)))
    
    bars = ax1.barh(range(len(top_creators)), top_creators['total_profit'], color=colors)
    ax1.set_yticks(range(len(top_creators)))
    ax1.set_yticklabels(top_creators['creator_short'], fontsize=8)
    ax1.set_xlabel('Profitto Totale (SOL)', fontweight='bold')
    ax1.set_title('Top 10 Creatori per Profitto Verificato', fontweight='bold', fontsize=12)
    ax1.invert_yaxis()
    
    # Aggiungi valori sulle barre
    for i, (bar, val) in enumerate(zip(bars, top_creators['total_profit'])):
        ax1.text(val, bar.get_y() + bar.get_height()/2, f' {val:.2f} SOL',
                va='center', fontsize=8, fontweight='bold')
    
    ax1.grid(axis='x', alpha=0.3)
    
    # -------------------------
    # 3. NUMERO ATTACCHI PER CREATORE
    # -------------------------
    ax2 = plt.subplot(4, 3, 5)
    top_by_attacks = creator_stats.nlargest(10, 'num_attacks')
    colors2 = plt.cm.Blues(np.linspace(0.4, 0.9, len(top_by_attacks)))
    
    bars2 = ax2.barh(range(len(top_by_attacks)), top_by_attacks['num_attacks'], color=colors2)
    ax2.set_yticks(range(len(top_by_attacks)))
    ax2.set_yticklabels(top_by_attacks['creator_short'], fontsize=8)
    ax2.set_xlabel('Numero di Attacchi', fontweight='bold')
    ax2.set_title('Top 10 Creatori per Numero di Attacchi', fontweight='bold', fontsize=12)
    ax2.invert_yaxis()
    
    for i, (bar, val) in enumerate(zip(bars2, top_by_attacks['num_attacks'])):
        ax2.text(val, bar.get_y() + bar.get_height()/2, f' {int(val)}',
                va='center', fontsize=9, fontweight='bold')
    
    ax2.grid(axis='x', alpha=0.3)
    
    # -------------------------
    # 4. DISTRIBUZIONE PROFITTI
    # -------------------------
    ax3 = plt.subplot(4, 3, 6)
    
    profit_bins = [0, 0.1, 1, 10, 100, 1000, df['profit_sol'].max() + 1]
    profit_labels = ['0-0.1', '0.1-1', '1-10', '10-100', '100-1k', '1k+']
    df['profit_range'] = pd.cut(df['profit_sol'], bins=profit_bins, labels=profit_labels)
    
    profit_dist = df['profit_range'].value_counts().sort_index()
    colors3 = plt.cm.Greens(np.linspace(0.4, 0.9, len(profit_dist)))
    
    wedges, texts, autotexts = ax3.pie(profit_dist.values, labels=profit_dist.index,
                                         autopct='%1.1f%%', colors=colors3,
                                         startangle=90)
    ax3.set_title('Distribuzione Range di Profitto (SOL)', fontweight='bold', fontsize=12)
    
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
    
    # -------------------------
    # 5. TIMING: ORE DOPO LAUNCH
    # -------------------------
    ax4 = plt.subplot(4, 3, 7)
    
    max_hours = df['hours_after_launch'].max()
    
    # Bins di base
    timing_bins = [0, 1, 6, 24, 72]
    timing_labels = ['0-1h', '1-6h', '6-24h', '1-3d']
    
    # Aggiungi bin "3-7d" se necessario
    if max_hours > 72:
        timing_bins.append(168)  # 7 giorni
        timing_labels.append('3-7d')
    
    # Aggiungi bin finale SOLO se è maggiore dell’ultimo bin
    last_bin = timing_bins[-1]
    final_bin = max_hours + 1
    
    if final_bin > last_bin:
        timing_bins.append(final_bin)
        # Label dinamica per l’ultimo intervallo
        if final_bin > 168:
            timing_labels.append('7d+')
        else:
            timing_labels.append(f'>{last_bin}h')
    
    # Ora bins sono sempre monotonicamente crescenti
    df['timing_range'] = pd.cut(df['hours_after_launch'], bins=timing_bins, labels=timing_labels)
    
    # Grafico
    timing_dist = df['timing_range'].value_counts().sort_index()
    colors4 = plt.cm.Oranges(np.linspace(0.4, 0.9, len(timing_dist)))
    
    bars4 = ax4.bar(range(len(timing_dist)), timing_dist.values, color=colors4)
    ax4.set_xticks(range(len(timing_dist)))
    ax4.set_xticklabels(timing_dist.index, rotation=45, ha='right')
    ax4.set_ylabel('Numero di Attacchi', fontweight='bold')
    ax4.set_title('Distribuzione Timing Attacchi', fontweight='bold', fontsize=12)
    ax4.grid(axis='y', alpha=0.3)
    
    for bar, val in zip(bars4, timing_dist.values):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                 f'{int(val)}', ha='center', va='bottom', fontweight='bold')

    
    # -------------------------
    # 6. SCATTER: PROFITTO vs TIMING
    # -------------------------
    ax5 = plt.subplot(4, 3, 8)
    
    scatter = ax5.scatter(df['hours_after_launch'], df['profit_sol'],
                         s=df['victims']*20, alpha=0.6, c=df['victims'],
                         cmap='viridis', edgecolors='black', linewidth=0.5)
    
    ax5.set_xlabel('Ore dopo Launch', fontweight='bold')
    ax5.set_ylabel('Profitto (SOL)', fontweight='bold')
    ax5.set_title('Profitto vs Timing (dimensione = vittime)', fontweight='bold', fontsize=12)
    ax5.grid(alpha=0.3)
    
    # Aggiungi colorbar per vittime
    cbar = plt.colorbar(scatter, ax=ax5)
    cbar.set_label('Numero Vittime', fontweight='bold')
    
    # -------------------------
    # 7. NUMERO VITTIME
    # -------------------------
    ax6 = plt.subplot(4, 3, 9)
    
    victims_dist = df['victims'].value_counts().sort_index()
    colors6 = plt.cm.Purples(np.linspace(0.4, 0.9, len(victims_dist)))
    
    bars6 = ax6.bar(victims_dist.index, victims_dist.values, color=colors6)
    ax6.set_xlabel('Numero di Vittime', fontweight='bold')
    ax6.set_ylabel('Numero di Attacchi', fontweight='bold')
    ax6.set_title('Distribuzione Numero Vittime per Attacco', fontweight='bold', fontsize=12)
    ax6.grid(axis='y', alpha=0.3)
    
    for bar, val in zip(bars6, victims_dist.values):
        ax6.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f'{int(val)}', ha='center', va='bottom', fontweight='bold', fontsize=8)
    
    # -------------------------
    # 8. TOP TOKEN ATTACCATI
    # -------------------------
    ax7 = plt.subplot(4, 3, 10)
    
    token_attacks = df['ticker'].value_counts().head(10)
    colors7 = plt.cm.Spectral(np.linspace(0.2, 0.8, len(token_attacks)))
    
    bars7 = ax7.barh(range(len(token_attacks)), token_attacks.values, color=colors7)
    ax7.set_yticks(range(len(token_attacks)))
    ax7.set_yticklabels(token_attacks.index, fontsize=9)
    ax7.set_xlabel('Numero di Attacchi', fontweight='bold')
    ax7.set_title('Top 10 Token più Attaccati (dai propri creatori)', fontweight='bold', fontsize=12)
    ax7.invert_yaxis()
    ax7.grid(axis='x', alpha=0.3)
    
    for bar, val in zip(bars7, token_attacks.values):
        ax7.text(val, bar.get_y() + bar.get_height()/2, f' {int(val)}',
                va='center', fontsize=9, fontweight='bold')
    
    # -------------------------
    # 9. EFFICIENZA: PROFITTO / VITTIMA
    # -------------------------
    ax8 = plt.subplot(4, 3, 11)
    
    df['profit_per_victim'] = df.apply(
        lambda row: row['profit_sol'] / row['victims'] if row['victims'] > 0 else 0,
        axis=1
    )
    
    # Top 10 attacchi per efficienza
    top_efficient = df.nlargest(10, 'profit_per_victim')[['ticker', 'profit_per_victim', 'profit_sol']]
    colors8 = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(top_efficient)))
    
    bars8 = ax8.barh(range(len(top_efficient)), top_efficient['profit_per_victim'], color=colors8)
    ax8.set_yticks(range(len(top_efficient)))
    ax8.set_yticklabels(top_efficient['ticker'], fontsize=8)
    ax8.set_xlabel('Profitto per Vittima (SOL)', fontweight='bold')
    ax8.set_title('Top 10 Attacchi più Efficienti', fontweight='bold', fontsize=12)
    ax8.invert_yaxis()
    ax8.grid(axis='x', alpha=0.3)
    
    for i, (bar, val) in enumerate(zip(bars8, top_efficient['profit_per_victim'])):
        ax8.text(val, bar.get_y() + bar.get_height()/2, f' {val:.3f}',
                va='center', fontsize=8, fontweight='bold')
    
    # -------------------------
    # 10. TIMELINE ATTACCHI
    # -------------------------
    ax9 = plt.subplot(4, 3, 12)
    
    df_sorted = df.sort_values('timestamp')
    df_sorted['cumulative_profit'] = df_sorted['profit_sol'].cumsum()
    
    ax9.plot(df_sorted['timestamp'], df_sorted['cumulative_profit'],
            color='darkgreen', linewidth=2, marker='o', markersize=4)
    ax9.fill_between(df_sorted['timestamp'], df_sorted['cumulative_profit'],
                     alpha=0.3, color='green')
    
    ax9.set_xlabel('Data', fontweight='bold')
    ax9.set_ylabel('Profitto Cumulativo (SOL)', fontweight='bold')
    ax9.set_title('Timeline Profitto Cumulativo', fontweight='bold', fontsize=12)
    ax9.grid(alpha=0.3)
    ax9.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig('verified_attacks_analysis.png', dpi=300, bbox_inches='tight')
    print(f"\n✅ Grafico salvato come: verified_attacks_analysis.png")
    plt.show()

# -------------------------
# REPORT DETTAGLIATO
# -------------------------
def print_detailed_report(df, creator_stats, stats):
    """Stampa report testuale dettagliato."""
    
    print(f"\n{'='*80}")
    print(f"REPORT DETTAGLIATO: CREATORI CHE ATTACCANO I PROPRI TOKEN")
    print(f"{'='*80}\n")
    
    print(f"📊 TOP 5 CREATORI PER PROFITTO:\n")
    for i, row in creator_stats.head(5).iterrows():
        print(f"{i+1}. {row['creator']}")
        print(f"   Attacchi: {row['num_attacks']}")
        print(f"   Profitto totale: {row['total_profit']:.4f} SOL")
        print(f"   Profitto medio: {row['avg_profit']:.4f} SOL")
        print(f"   Token attaccati: {', '.join(row['tokens'][:5])}")
        print()
    
    print(f"\n{'─'*80}\n")
    print(f"🎯 DETTAGLIO ATTACCHI VERIFICATI:\n")
    
    for i, row in df.nlargest(10, 'profit_sol').iterrows():
        print(f"{i+1}. {row['token_name']} ({row['ticker']})")
        print(f"   Creatore: {row['creator']}")
        print(f"   Profitto: {row['profit_sol']:.4f} SOL")
        print(f"   Vittime: {row['victims']}")
        print(f"   Timing: {row['hours_after_launch']:.2f} ore dopo launch")
        print(f"   Pump.fun: {row['pumpfun_link']}")
        print(f"   Sandwich ID: {row['sandwich_id']}")
        print()
    
    print(f"\n{'='*80}\n")

# -------------------------
# ESPORTA CSV
# -------------------------
def export_to_csv(df, creator_stats):
    """Esporta i dati in CSV per analisi ulteriori."""
    
    df.to_csv('verified_attacks_details.csv', index=False)
    creator_stats.to_csv('creator_statistics.csv', index=False)
    
    print(f"📄 CSV esportati:")
    print(f"   - verified_attacks_details.csv")
    print(f"   - creator_statistics.csv\n")

# -------------------------
# MAIN
# -------------------------
def main():
    print("\n" + "="*80)
    print("ANALISI GRAFICA E ANALITICA: ATTACCHI VERIFICATI")
    print("Creatori che hanno attaccato i propri token")
    print("="*80 + "\n")
    
    # Carica dati
    verified_attacks, overall_stats = load_verified_attacks(attack_path)

    
    if len(verified_attacks) == 0:
        print("❌ Nessun attacco verificato trovato!")
        return
    
    # Analizza
    df, creator_stats, stats = analyze_attacks(verified_attacks)
    
    # Crea visualizzazioni
    print("📊 Generazione grafici...")
    create_visualizations(df, creator_stats, stats)
    
    # Report dettagliato
    print_detailed_report(df, creator_stats, stats)
    
    # Esporta CSV
    export_to_csv(df, creator_stats)
    
    print("✅ Analisi completata!")

if __name__ == "__main__":
    main()