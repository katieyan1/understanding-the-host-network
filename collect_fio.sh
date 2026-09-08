#!/bin/bash

config=$1
io_size=$2
ssd=$3
STATS_PATH=${4:?stats path is required}

grep "iops        :" "$STATS_PATH/$config.fio$ssd.txt" | tr -d ' ' | tr ',' ' ' | awk '{print $3}' | tr -d 'avg=' | tr -d ',' | awk -v sz=$io_size '{s += $1} END {print s*sz*8/1e9;}'
