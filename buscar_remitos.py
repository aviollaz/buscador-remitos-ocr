#!/usr/bin/env python3
"""Punto de entrada: python buscar_remitos.py <comando> ...   (ver --help)"""

from remitos.cli import main

if __name__ == "__main__":  # necesario en Windows por el multiprocessing
    main()
