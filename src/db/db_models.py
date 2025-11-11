# -*- coding: utf-8 -*-
"""
Modelos de la Base de Datos (SQLAlchemy ORM).

(Versión 7.0 - Añadida columna para 2do llamado)
"""

import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    Index,
)
from typing import Optional, List


class Base(DeclarativeBase):
    type_annotation_map = {
        dict[str, any]: JSON,
        list[dict[str, any]]: JSON,
    }

# --- Tablas de Jerarquía (Idea #4) ---

class CaSector(Base):
    __tablename__ = "ca_sector"
    
    sector_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    
    organismos: Mapped[List["CaOrganismo"]] = relationship(back_populates="sector")

    def __repr__(self):
        return f"<CaSector(nombre='{self.nombre}')>"

        
class CaOrganismo(Base):
    __tablename__ = "ca_organismo"
    
    organismo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    
    sector_id: Mapped[int] = mapped_column(ForeignKey("ca_sector.sector_id"))
    
    sector: Mapped["CaSector"] = relationship(back_populates="organismos", lazy="joined")
    
    licitaciones: Mapped[List["CaLicitacion"]] = relationship(back_populates="organismo")

    def __repr__(self):
        return f"<CaOrganismo(nombre='{self.nombre}')>"

        
# --- Tablas de Aplicación ---

class CaLicitacion(Base):
    __tablename__ = "ca_licitacion"
    
    ca_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_ca: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, doc="El código de Mercado Público (ej. 1234-56-COT25)"
    )
    nombre: Mapped[Optional[str]] = mapped_column(String(1000))
    monto_clp: Mapped[Optional[float]] = mapped_column(Float)
    
    fecha_publicacion: Mapped[Optional[datetime.date]] = mapped_column()
    fecha_cierre: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True))
    
    # --- ¡NUEVA COLUMNA! (Tu Punto 3) ---
    fecha_cierre_segundo_llamado: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # --- FIN NUEVA COLUMNA ---

    estado_ca_texto: Mapped[Optional[str]] = mapped_column(String(255))
    
    proveedores_cotizando: Mapped[Optional[int]] = mapped_column(Integer)
    descripcion: Mapped[Optional[str]] = mapped_column(String)
    direccion_entrega: Mapped[Optional[str]] = mapped_column(String(1000))
    productos_solicitados: Mapped[Optional[list[dict[str, any]]]] = mapped_column(
        JSON, nullable=True, doc="Lista de productos solicitados"
    )
    
    puntuacion_final: Mapped[int] = mapped_column(
        Integer, default=0, index=True, doc="El score final (Fase 1 + Fase 2)"
    )
    
    organismo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ca_organismo.organismo_id")
    )
    
    organismo: Mapped[Optional["CaOrganismo"]] = relationship(
        back_populates="licitaciones", lazy="joined"
    )
    
    seguimiento: Mapped["CaSeguimiento"] = relationship(
        back_populates="licitacion",
        cascade="all, delete-orphan",
        lazy="joined",
    )

    def __repr__(self):
        return f"<CaLicitacion(codigo_ca='{self.codigo_ca}', score={self.puntuacion_final})>"


class CaSeguimiento(Base):
    __tablename__ = "ca_seguimiento"
    
    ca_id: Mapped[int] = mapped_column(
        ForeignKey("ca_licitacion.ca_id", ondelete="CASCADE"), primary_key=True
    )
    
    es_favorito: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    es_ofertada: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    
    licitacion: Mapped["CaLicitacion"] = relationship(
        back_populates="seguimiento"
    )

    def __repr__(self):
        return f"<CaSeguimiento(ca_id={self.ca_id}, fav={self.es_favorito}, oft={self.es_ofertada})>"


# --- Tablas de Configuración (Idea #2) ---

class CaKeyword(Base):
    __tablename__ = "ca_keyword"
    
    keyword_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    tipo: Mapped[str] = mapped_column(String(50), index=True)
    puntos: Mapped[int] = mapped_column(Integer)

    def __repr__(self):
        return f"<CaKeyword(keyword='{self.keyword}', tipo='{self.tipo}', puntos={self.puntos})>"


class CaOrganismoPrioritario(Base):
    __tablename__ = "ca_organismo_prioritario"
    
    org_prio_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    organismo_id: Mapped[int] = mapped_column(
        ForeignKey("ca_organismo.organismo_id", ondelete="CASCADE"),
        unique=True
    )
    
    puntos: Mapped[int] = mapped_column(Integer)
    
    organismo: Mapped["CaOrganismo"] = relationship(lazy="joined")

    def __repr__(self):
        return f"<CaOrganismoPrioritario(org_id={self.organismo_id}, puntos={self.puntos})>"