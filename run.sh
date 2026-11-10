#!/bin/bash

x=300
y=305
size=64
output_dir=missing_02

uv run render.py \
    -s ./missing_02.txt \
    -i ./labels.jpg \
    -o "$output_dir" \
    -p $x,$y \
    -f Georgia \
    -z $size \
    --small-caps
