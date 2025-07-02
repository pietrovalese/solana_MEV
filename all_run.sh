#!/bin/bash

# Step 1: Copia file
cp sandwich.jsonl sandwich_appoggio.jsonl
echo "✅ Copiato sandwich.jsonl -> sandwich_appoggio.jsonl"

# Step 2: Lancia gli script in background e salva i PID
gnome-terminal -- bash -c "python3 sandwich.py; exec bash" &
pid1=$!

gnome-terminal -- bash -c "python3 helius_rpc_details.py; exec bash" &
pid2=$!

gnome-terminal -- bash -c "python3 arbitrage.py; exec bash" &
pid3=$!

gnome-terminal -- bash -c "python3 memecoin.py; exec bash" &
pid4=$!

echo "⏳ Script attivo per 8 ore..."
sleep 28800  # 8 ore

echo "⏹️ Tempo scaduto: terminazione dei processi..."

# (Facoltativo) Uccide eventuali processi Python attivi (più aggressivo):
pkill -f sandwich.py
pkill -f helius_rpc_details.py
pkill -f arbitrage.py
pkill -f memecoin.py

echo "✅ Tutti i processi python terminati."
