import os
import glob
import pandas as pd
import logging
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import datetime
import warnings

# Configurazione plotting
plt.style.use('default')
sns.set_palette("husl")
warnings.filterwarnings('ignore')

# Configurazione logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_required_columns(df: pd.DataFrame, required_cols: List[str], file_name: str) -> bool:
    """Verifica che il DataFrame contenga le colonne richieste."""
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.warning(f"File {file_name}: colonne mancanti: {missing_cols}")
        return False
    return True

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Pulisce il DataFrame rimuovendo spazi dai nomi delle colonne e gestendo valori mancanti."""
    # Pulizia nomi colonne
    df.columns = df.columns.str.strip()
    
    # Sostituisce valori non numerici con 0 per le colonne numeriche
    numeric_cols = ['30d_sandwich_rate', '60d_sandwich_rate', 'total_stake']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    return df

def calculate_total_stake(df: pd.DataFrame) -> pd.DataFrame:
    """Calcola total_stake se non presente, usando colonne che terminano con '_stake'."""
    if "total_stake" not in df.columns:
        stake_cols = [c for c in df.columns if c.endswith("_stake")]
        if stake_cols:
            df["total_stake"] = df[stake_cols].sum(axis=1)
            logger.info(f"Calcolato total_stake da colonne: {stake_cols}")
        else:
            logger.warning("Nessuna colonna stake trovata, impostando total_stake a 0")
            df["total_stake"] = 0
    return df

def process_single_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Processa un singolo file CSV e restituisce i risultati dell'analisi."""
    file_name = os.path.basename(file_path)
    logger.info(f"Processando file: {file_name}")
    
    try:
        # Estrae il numero dell'epoca dal nome del file
        epoch_num = None
        if "epoch_" in file_name:
            try:
                epoch_num = int(file_name.split("epoch_")[1].split(".")[0])
            except:
                epoch_num = None
        
        # Legge il CSV
        df = pd.read_csv(file_path)
        
        if df.empty:
            logger.warning(f"File {file_name} è vuoto")
            return None
            
        # Pulisce il DataFrame
        df = clean_dataframe(df)
        
        # Calcola total_stake se necessario
        df = calculate_total_stake(df)
        
        # Verifica colonne essenziali
        required_cols = ['30d_sandwich_rate', '60d_sandwich_rate', 'total_stake']
        if not validate_required_columns(df, required_cols, file_name):
            return None
        
        # Rimuove righe con total_stake pari a 0
        df = df[df['total_stake'] > 0]
        
        if df.empty:
            logger.warning(f"File {file_name}: nessun validatore con stake > 0")
            return None
        
        # Calcoli principali
        total_stake = df["total_stake"].sum()
        
        if total_stake == 0:
            logger.warning(f"File {file_name}: total_stake della rete è 0")
            return None
        
        weighted_30d = (df["30d_sandwich_rate"] * df["total_stake"]).sum() / total_stake
        weighted_60d = (df["60d_sandwich_rate"] * df["total_stake"]).sum() / total_stake
        
        # Calcola impatto e top 10
        df["impact_30d"] = df["30d_sandwich_rate"] * df["total_stake"]
        df_top10 = df.sort_values(by="impact_30d", ascending=False).head(10)
        df_top10 = df_top10.copy()  # Evita SettingWithCopyWarning
        df_top10["epoch_file"] = file_name
        df_top10["epoch_num"] = epoch_num
        
        # Verifica che esistano le colonne necessarie per il risultato finale
        result_cols = ["epoch_file", "epoch_num", "validator_name", "vote_account", "total_stake", 
                      "30d_sandwich_rate", "60d_sandwich_rate", "impact_30d"]
        
        available_cols = [col for col in result_cols if col in df_top10.columns]
        if 'validator_name' not in df_top10.columns:
            logger.warning(f"File {file_name}: colonna 'validator_name' mancante, usando indice")
            df_top10['validator_name'] = f"validator_{df_top10.index}"
        
        if 'vote_account' not in df_top10.columns:
            logger.warning(f"File {file_name}: colonna 'vote_account' mancante, usando indice")
            df_top10['vote_account'] = f"account_{df_top10.index}"
        
        return {
            'summary': {
                "epoch_file": file_name,
                "epoch_num": epoch_num,
                "weighted_30d_sandwich_rate": weighted_30d,
                "weighted_60d_sandwich_rate": weighted_60d,
                "total_stake": total_stake,
                "num_validators": len(df)
            },
            'top10': df_top10[available_cols],
            'all_data': df  # Conserva tutti i dati per analisi aggiuntive
        }
        
    except Exception as e:
        logger.error(f"Errore processando file {file_name}: {str(e)}")
        return None

def compute_trend(df: pd.DataFrame) -> pd.Series:
    """Calcola il trend tra prima e ultima epoca per un validatore."""
    try:
        df_sorted = df.sort_values("epoch_num") if "epoch_num" in df.columns else df.sort_values("epoch_file")
        
        if len(df_sorted) < 2:
            return pd.Series({"trend_30d": "insufficient_data", "trend_60d": "insufficient_data"})
        
        first_30d = df_sorted.iloc[0]["30d_sandwich_rate"]
        last_30d = df_sorted.iloc[-1]["30d_sandwich_rate"]
        first_60d = df_sorted.iloc[0]["60d_sandwich_rate"]
        last_60d = df_sorted.iloc[-1]["60d_sandwich_rate"]
        
        trend_30d = "increased" if last_30d > first_30d else ("decreased" if last_30d < first_30d else "stable")
        trend_60d = "increased" if last_60d > first_60d else ("decreased" if last_60d < first_60d else "stable")
        
        return pd.Series({"trend_30d": trend_30d, "trend_60d": trend_60d})
    
    except Exception as e:
        logger.error(f"Errore nel calcolo del trend: {str(e)}")
        return pd.Series({"trend_30d": "error", "trend_60d": "error"})

def create_visualizations(summary_df: pd.DataFrame, final_df: pd.DataFrame, 
                         top_validators_df: pd.DataFrame, output_dir: str = "plots"):
    """Crea visualizzazioni specifiche per la tesi sui validatori scorretti."""
    
    # Crea directory per i plot se non esiste
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 1. TREND SANDWICH RATES NEL TEMPO
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    if 'epoch_num' in summary_df.columns and summary_df['epoch_num'].notna().any():
        x_data = summary_df['epoch_num']
        x_label = 'Numero Epoca'
        title_suffix = 'per Epoca'
    else:
        x_data = range(len(summary_df))
        x_label = 'File (ordine temporale)'
        title_suffix = 'nel Tempo'
    
    ax1.plot(x_data, summary_df['weighted_30d_sandwich_rate'], 'b-o', linewidth=2, markersize=6)
    ax1.set_title(f'Weighted 30-day Sandwich Rate {title_suffix}', fontsize=14, fontweight='bold')
    ax1.set_xlabel(x_label)
    ax1.set_ylabel('Weighted Sandwich Rate')
    ax1.grid(True, alpha=0.3)
    
    ax2.plot(x_data, summary_df['weighted_60d_sandwich_rate'], 'r-o', linewidth=2, markersize=6)
    ax2.set_title(f'Weighted 60-day Sandwich Rate {title_suffix}', fontsize=14, fontweight='bold')
    ax2.set_xlabel(x_label)
    ax2.set_ylabel('Weighted Sandwich Rate')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/sandwich_rates_trend.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # 2. PERSISTENZA DEI VALIDATORI SCORRETTI
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Filtra solo i validatori che appaiono in più epoche
    persistent_validators = final_df[final_df['top10_count'] > 1].sort_values('top10_pct', ascending=False)
    
    if len(persistent_validators) > 15:
        persistent_validators = persistent_validators.head(15)
    
    bars = ax.barh(range(len(persistent_validators)), persistent_validators['top10_pct'])
    ax.set_yticks(range(len(persistent_validators)))
    ax.set_yticklabels([f"Validator {i+1}" for i in range(len(persistent_validators))])
    ax.set_xlabel('Percentuale di Epoche in Top 10 (%)')
    ax.set_title('Validatori con Comportamento Scorrretto Persistente\n(Presenti in Top 10 per più epoche)', 
                 fontsize=14, fontweight='bold')
    
    # Colora le barre in base alla percentuale
    for i, bar in enumerate(bars):
        pct = persistent_validators.iloc[i]['top10_pct']
        if pct >= 80:
            bar.set_color('red')
        elif pct >= 50:
            bar.set_color('orange') 
        else:
            bar.set_color('yellow')
    
    # Aggiungi valori sulle barre
    for i, pct in enumerate(persistent_validators['top10_pct']):
        ax.text(pct + 1, i, f'{pct:.1f}%', va='center')
    
    ax.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/persistent_malicious_validators.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # 3. DISTRIBUZIONE SANDWICH RATES
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    if 'avg_30d_sandwich_rate' in final_df.columns:
        ax1.hist(final_df['avg_30d_sandwich_rate'], bins=30, alpha=0.7, color='blue', edgecolor='black')
        ax1.set_title('Distribuzione Average 30-day Sandwich Rate', fontweight='bold')
        ax1.set_xlabel('Average 30-day Sandwich Rate')
        ax1.set_ylabel('Numero di Validatori')
        ax1.grid(True, alpha=0.3)
    
    if 'avg_60d_sandwich_rate' in final_df.columns:
        ax2.hist(final_df['avg_60d_sandwich_rate'], bins=30, alpha=0.7, color='red', edgecolor='black')
        ax2.set_title('Distribuzione Average 60-day Sandwich Rate', fontweight='bold')
        ax2.set_xlabel('Average 60-day Sandwich Rate')
        ax2.set_ylabel('Numero di Validatori')
        ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/sandwich_rates_distribution.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # 4. HEATMAP DEI TOP VALIDATORI NEL TEMPO
    if len(top_validators_df) > 0:
        # Prepara i dati per la heatmap
        pivot_data = top_validators_df.pivot_table(
            values='30d_sandwich_rate', 
            index='vote_account', 
            columns='epoch_file', 
            fill_value=0
        )
        
        # Prendi solo i top 15 validatori per leggibilità
        top_validators_for_heatmap = final_df.head(15)['vote_account'].tolist()
        pivot_data_filtered = pivot_data.loc[
            pivot_data.index.isin(top_validators_for_heatmap)
        ]
        
        fig, ax = plt.subplots(figsize=(15, 8))
        sns.heatmap(pivot_data_filtered, annot=True, fmt='.3f', cmap='Reds', 
                   ax=ax, cbar_kws={'label': '30-day Sandwich Rate'})
        ax.set_title('Heatmap: Sandwich Rates dei Top Validatori Scorretti nel Tempo', 
                     fontsize=14, fontweight='bold')
        ax.set_xlabel('File Epoca')
        ax.set_ylabel('Vote Account (Top Validatori)')
        
        # Ruota le etichette dell'asse x per leggibilità
        plt.xticks(rotation=45)
        plt.yticks(rotation=0)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/validators_heatmap.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    # 5. ANALISI TREND
    if 'trend_30d' in final_df.columns:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        trend_counts_30d = final_df['trend_30d'].value_counts()
        ax1.pie(trend_counts_30d.values, labels=trend_counts_30d.index, autopct='%1.1f%%', startangle=90)
        ax1.set_title('Trend 30-day Sandwich Rate\n(Primi vs Ultimi dati)', fontweight='bold')
        
        if 'trend_60d' in final_df.columns:
            trend_counts_60d = final_df['trend_60d'].value_counts()
            ax2.pie(trend_counts_60d.values, labels=trend_counts_60d.index, autopct='%1.1f%%', startangle=90)
            ax2.set_title('Trend 60-day Sandwich Rate\n(Primi vs Ultimi dati)', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/trend_analysis.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    # 6. CORRELAZIONE STAKE vs SANDWICH RATE
    if len(top_validators_df) > 0:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        ax1.scatter(top_validators_df['total_stake'], top_validators_df['30d_sandwich_rate'], 
                   alpha=0.6, s=50)
        ax1.set_xlabel('Total Stake')
        ax1.set_ylabel('30-day Sandwich Rate')
        ax1.set_title('Correlazione: Stake vs 30-day Sandwich Rate', fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        ax2.scatter(top_validators_df['total_stake'], top_validators_df['60d_sandwich_rate'], 
                   alpha=0.6, s=50, color='red')
        ax2.set_xlabel('Total Stake')
        ax2.set_ylabel('60-day Sandwich Rate')
        ax2.set_title('Correlazione: Stake vs 60-day Sandwich Rate', fontweight='bold')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/stake_correlation.png', dpi=300, bbox_inches='tight')
        plt.show()
    
    print(f"\n✅ Tutte le visualizzazioni sono state salvate in '{output_dir}/'")

def generate_thesis_report(summary_df: pd.DataFrame, final_df: pd.DataFrame, 
                          top_validators_df: pd.DataFrame, num_files: int):
    """Genera un report specifico per la tesi sui validatori scorretti."""
    
    print("\n" + "="*80)
    print("📊 REPORT VALIDATORI SCORRETTI - ANALISI PER TESI")
    print("="*80)
    
    # Statistiche generali
    print(f"\n🔍 PANORAMICA GENERALE:")
    print(f"   • File processati: {len(summary_df)}/{num_files}")
    print(f"   • Validatori unici analizzati: {len(final_df)}")
    print(f"   • Media validatori per epoca: {summary_df['num_validators'].mean():.1f}")
    
    # Analisi comportamento scorretto persistente
    persistent_malicious = final_df[final_df['top10_count'] > 1]
    highly_persistent = final_df[final_df['top10_pct'] >= 50]
    
    print(f"\n🚨 VALIDATORI CON COMPORTAMENTO SCORRETTO:")
    print(f"   • Validatori presenti in Top 10 per più epoche: {len(persistent_malicious)}")
    print(f"   • Validatori presenti in ≥50% delle epoche: {len(highly_persistent)}")
    
    if len(highly_persistent) > 0:
        print(f"   • Sandwich rate medio (30d) dei più persistenti: {highly_persistent['avg_30d_sandwich_rate'].mean():.6f}")
        print(f"   • Sandwich rate massimo (30d): {highly_persistent['avg_30d_sandwich_rate'].max():.6f}")
    
    # Top validatori più problematici
    print(f"\n🎯 TOP 5 VALIDATORI PIÙ PROBLEMATICI:")
    top_5_problematic = final_df.head(5)
    for i, (_, validator) in enumerate(top_5_problematic.iterrows(), 1):
        print(f"   {i}. Vote Account: {validator['vote_account']}")
        print(f"      - Presente in {validator['top10_pct']:.1f}% delle epoche")
        if 'avg_30d_sandwich_rate' in validator:
            print(f"      - Sandwich rate medio (30d): {validator['avg_30d_sandwich_rate']:.6f}")
        if 'trend_30d' in validator:
            print(f"      - Trend: {validator['trend_30d']}")
        print()
    
    # Analisi trend generali
    print(f"\n📈 TREND GENERALI DELLA RETE:")
    print(f"   • Weighted 30d sandwich rate medio: {summary_df['weighted_30d_sandwich_rate'].mean():.6f}")
    print(f"   • Weighted 60d sandwich rate medio: {summary_df['weighted_60d_sandwich_rate'].mean():.6f}")
    
    if len(summary_df) > 1:
        trend_30d = "crescente" if summary_df['weighted_30d_sandwich_rate'].iloc[-1] > summary_df['weighted_30d_sandwich_rate'].iloc[0] else "decrescente"
        trend_60d = "crescente" if summary_df['weighted_60d_sandwich_rate'].iloc[-1] > summary_df['weighted_60d_sandwich_rate'].iloc[0] else "decrescente"
        print(f"   • Trend 30d: {trend_30d}")
        print(f"   • Trend 60d: {trend_60d}")
    
    # Raccomandazioni per la tesi
    print(f"\n📝 EVIDENZE CHIAVE PER LA TESI:")
    print(f"   • Esistenza di validatori con comportamento scorretto persistente")
    print(f"   • {len(highly_persistent)} validatori mostrano pattern di sandwich attacks ricorrenti")
    print(f"   • La concentrazione di attacchi sandwich suggerisce comportamenti intenzionali")
    print(f"   • Necessità di meccanismi di governance per penalizzare validatori scorretti")
    
    print("="*80)

def main():
    """Funzione principale per l'analisi dei validatori."""
    try:
        # Setup percorsi
        BASE_DIR = os.path.dirname(os.path.dirname(__file__))
        DATASET_DIR = os.path.join(BASE_DIR, "dataset_validatori")
        
        if not os.path.exists(DATASET_DIR):
            logger.error(f"Directory dataset non trovata: {DATASET_DIR}")
            return
        
        files = glob.glob(os.path.join(DATASET_DIR, "validator_epoch_*.csv"))
        
        if not files:
            logger.error(f"Nessun file CSV trovato in: {DATASET_DIR}")
            return
        
        logger.info(f"Trovati {len(files)} file da processare")
        
        # Processa tutti i file
        summary = []
        top_validators_list = []
        
        for file_path in sorted(files):  # Ordina i file per consistenza
            result = process_single_file(file_path)
            if result:
                summary.append(result['summary'])
                top_validators_list.append(result['top10'])
            else:
                logger.warning(f"File {os.path.basename(file_path)} saltato a causa di errori")
        
        if not summary:
            logger.error("Nessun file processato con successo")
            return
        
        # Crea DataFrame di riepilogo
        summary_df = pd.DataFrame(summary)
        print("\n=== RIEPILOGO WEIGHTED RATES ===")
        print(summary_df)
        
        if not top_validators_list:
            logger.error("Nessun dato sui top validators disponibile")
            return
        
        # Combina tutti i top validators
        top_validators_df = pd.concat(top_validators_list, ignore_index=True)
        print(f"\n=== TOP 10 VALIDATORI PER EPOCA ({len(top_validators_df)} record) ===")
        print(top_validators_df.head())
        
        # Analisi di persistenza
        if 'vote_account' not in top_validators_df.columns:
            logger.error("Colonna 'vote_account' non disponibile per l'analisi di persistenza")
            return
        
        persistence = top_validators_df.groupby("vote_account").size().reset_index(name="top10_count")
        
        # Calcola percentuali
        num_epochs = len([s for s in summary])  # Usa il numero di epoche processate con successo
        persistence["top10_pct"] = persistence["top10_count"] / num_epochs * 100
        
        # Calcola medie
        numeric_columns = ['30d_sandwich_rate', '60d_sandwich_rate']
        available_numeric = [col for col in numeric_columns if col in top_validators_df.columns]
        
        if available_numeric:
            mean_rates = top_validators_df.groupby("vote_account")[available_numeric].mean().reset_index()
            
            # Rinomina colonne
            rename_dict = {}
            for col in available_numeric:
                new_name = col.replace('30d_sandwich_rate', 'avg_30d_sandwich_rate').replace('60d_sandwich_rate', 'avg_60d_sandwich_rate')
                rename_dict[col] = new_name
            
            mean_rates.rename(columns=rename_dict, inplace=True)
        else:
            mean_rates = persistence[['vote_account']].copy()  # Solo vote_account se non ci sono dati numerici
        
        # Calcola trends
        try:
            trends = top_validators_df.groupby("vote_account").apply(compute_trend, include_groups=False).reset_index()
        except Exception as e:
            logger.error(f"Errore nel calcolo dei trend: {str(e)}")
            trends = persistence[['vote_account']].copy()
            trends['trend_30d'] = 'error'
            trends['trend_60d'] = 'error'
        
        # Combina risultati finali
        final_df = persistence.copy()
        final_df = final_df.merge(mean_rates, on="vote_account", how="left")
        final_df = final_df.merge(trends, on="vote_account", how="left")
        
        # Ordina per persistenza
        final_df = final_df.sort_values(by="top10_pct", ascending=False)
        
        print(f"\n=== ANALISI PERSISTENZA VALIDATORI (Top 20) ===")
        print(final_df.reset_index(drop=True).head(20))
        
        # Genera visualizzazioni per la tesi
        create_visualizations(summary_df, final_df, top_validators_df)
        
        # Genera report specifico per la tesi
        generate_thesis_report(summary_df, final_df, top_validators_df, len(files))
        
    except Exception as e:
        logger.error(f"Errore generale nell'esecuzione: {str(e)}")
        raise

if __name__ == "__main__":
    main()