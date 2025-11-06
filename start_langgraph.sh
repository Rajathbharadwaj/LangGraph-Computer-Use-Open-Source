#!/bin/bash
source $HOME/miniconda3/etc/profile.d/conda.sh
conda activate newat
langgraph dev --port 8124 --no-browser --no-reload > $HOME/cua/logs/langgraph.log 2>&1
