#!/usr/bin/env python3
"""Punto de entrada: python buscador.py <comando> ...   (ver --help)"""

from buscador.cli import main

if __name__ == "__main__":  # necesario en Windows por el multiprocessing
    main()
