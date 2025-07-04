#!/bin/bash

# Nome della sessione tmux
SESSION="sandwich_session"

# Step 1: Copia file
cp sandwich.jsonl sandwich_appoggio.jsonl
echo "✅ Copiato sandwich.jsonl -> sandwich_appoggio.jsonl"

# Step 2: Crea nuova sessione tmux in background
tmux new-session -d -s $SESSION -n main

# Step 3: Lancia i comandi nei vari pannelli

# Pannello 0: sandwich.py
tmux send-keys -t $SESSION:0 'python3 sandwich.py; bash' C-m

# Split orizzontale per helius_rpc_details.py
tmux split-window -h -t $SESSION
tmux send-keys -t $SESSION 'python3 helius_rpc_details.py; bash' C-m

# Split verticale per arbitrage.py
tmux split-window -v -t $SESSION:0.0
tmux send-keys -t $SESSION 'python3 arbitrage.py; bash' C-m

# Se vuoi un altro split per memecoin.py
tmux select-pane -t $SESSION:0.1
tmux split-window -v -t $SESSION
tmux send-keys -t $SESSION 'python3 memecoin.py; bash' C-m

tmux attach -t $SESSION

# Step 5: Uccidi la sessione tmux
#tmux kill-session -t $SESSION

