# -*- coding: utf-8 -*-
"""
Punto de Entrada Principal de la Aplicación.

Este script es el único que debe ser ejecutado para iniciar
la aplicación GUI.

Se encarga de:
1. Configurar el sys.path para que Python encuentre los módulos en 'src'.
2. Importar y configurar el logger principal.
3. Iniciar la función 'run_gui' que lanza la ventana.
4. Capturar cualquier error fatal que ocurra fuera de la GUI.
"""

import sys
from pathlib import Path

# --- Configuración del Path ---
# Añade la carpeta raíz al path del sistema para que
# Python pueda encontrar 'src' y 'config'
# Esto es crucial para que las importaciones (ej. from src.gui...) funcionen
FILE = Path(__file__).resolve()
ROOT = FILE.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
# ------------------------------

# Importar el logger (ahora que el path está configurado)
from src.utils.logger import configurar_logger  # noqa: E402

# Configura el logger principal para este script
logger = configurar_logger("run_app")


def main():
    """Función principal que lanza la aplicación."""
    logger.info("=====================================")
    logger.info("Iniciando Monitor de Compras Ágiles...")
    logger.info("=====================================")

    try:
        # Importa la función de la GUI aquí, no a nivel global
        # para que el logger se configure primero.
        from src.gui.gui_main import run_gui

        # Llama a la función que inicia la GUI
        run_gui()

    except ImportError as e:
        logger.critical(f"Error de importación. ¿Falta 'src' en el path? Error: {e}")
        # (En un futuro, mostrar un pop-up de error)
    except Exception as e:
        logger.critical(f"Error fatal no controlado en main: {e}", exc_info=True)
        # (En un futuro, mostrar un pop-up de error)
    finally:
        logger.info("Aplicación cerrada.")


if __name__ == "__main__":
    main()
