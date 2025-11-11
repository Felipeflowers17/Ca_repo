# -*- coding: utf-8 -*-
"""
Excepciones Personalizadas de la Aplicación.

Define tipos de error específicos para el flujo de ETL,
permitiendo a la GUI saber exactamente qué fase falló.
"""

class EtlError(Exception):
    """Clase base para todos los errores de ETL."""
    pass

class ScrapingFase1Error(EtlError):
    """Lanzado si el scraping de listado (Fase 1) falla."""
    pass

class DatabaseLoadError(EtlError):
    """Lanzado si la carga (Load) de datos crudos a la BD falla."""
    pass

class DatabaseTransformError(EtlError):
    """Lanzado si la transformación (Transform) de puntajes falla."""
    pass

class ScrapingFase2Error(EtlError):
    """Lanzado si el scraping de fichas de detalle (Fase 2) falla."""
    pass

class RecalculoError(EtlError):
    """Lanzado si el proceso de recálculo de puntajes falla."""
    pass