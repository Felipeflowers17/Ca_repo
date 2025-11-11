# -*- coding: utf-8 -*-
"""
Configuración General de la Aplicación.

Versión (Fase 5.3 - Corrección de Importación Circular)
- MOVIMOS los UMBRALES aquí para romper el círculo de dependencias.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde el archivo .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", encoding="cp1252")

# --- Configuración de Base de Datos (PostgreSQL) ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está definida en el archivo .env")

# --- ¡NUEVA UBICACIÓN DE CONSTANTES! ---
# Umbrales (movidos de score_config.py para romper importación circular)
UMBRAL_FASE_1 = 5  # Puntos mínimos para pasar a Fase 2
UMBRAL_FINAL_RELEVANTE = 9   # Puntos mínimos para ser "Relevante"

# --- Configuración de Scraping (de tu archivo original) ---
URL_BASE_WEB = "https://buscador.mercadopublico.cl"
URL_BASE_API = "https://api.buscador.mercadopublico.cl"

TIMEOUT_REQUESTS = 30  # 30 segundos
DELAY_ENTRE_PAGINAS = 2 # 2 segundos
MODO_HEADLESS = os.getenv('HEADLESS', 'True').lower() == 'true'

HEADERS_API = {
    'X-Api-Key': 'e93089e4-437c-4723-b343-4fa20045e3bc'
}