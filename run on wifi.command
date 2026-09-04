#!/bin/bash
# Start Saphal Book and let phones, tablets and other computers on the same
# wifi use it as well. The addresses to open are printed in this window.
cd "$(dirname "$0")"
python3 start.py --lan
