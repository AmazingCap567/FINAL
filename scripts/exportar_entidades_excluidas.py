# -*- coding: utf-8 -*-
"""
scripts/exportar_entidades_excluidas.py
========================================
Genera/actualiza, para cada entidad excluida de la proyeccion futura por un
evento de intervencion/disolucion SBS confirmado (ver
motor/datos/eventos_intervencion.py), unicamente estos dos artefactos:

  1. Historial de clasificaciones por clasificadora (ECR).
  2. Ficha de evento (por que se excluyo, fecha, resolucion SBS, fuente).

La logica real vive en motor/datos/export_entidades_excluidas.py; este
script solo arma los insumos y llama al orquestador.

Reglas de actualizacion (idempotente, seguro de re-ejecutar):
  - Carpeta por tipo de entidad (CMAC/CRAC/FINANCIERA/BANCO): se reutiliza
    si ya existe; se crea si no.
  - Libro Excel por tipo de artefacto x tipo de entidad: se abre y actualiza
    si ya existe en disco; se crea si no.
  - Hoja por entidad dentro de ese libro: se reemplaza si ya existe (para
    reflejar cortes nuevos); se agrega si no existe. Las hojas de otras
    entidades del mismo tipo no se tocan.

Salida: outputs/analisis/entidades_excluidas/<TIPO>/
    historial_clasificaciones_<TIPO>.xlsx
    ficha_evento_<TIPO>.xlsx

Ejecucion:
    python scripts/exportar_entidades_excluidas.py
"""

from __future__ import annotations
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.utils import section, log
from motor.datos import export_entidades_excluidas as export_mod


def main() -> None:
    section("EXPORTAR ENTIDADES EXCLUIDAS: construyendo insumos (homologacion + clasificaciones SBS)")
    sbs_long_resolved, registry = export_mod.construir_insumos()
    log(f"Universo canonico: {len(registry.canonical_df)} entidades. "
        f"Clasificaciones SBS resueltas: {len(sbs_long_resolved)} filas.")

    export_mod.exportar_entidades_excluidas(sbs_long_resolved, registry)


if __name__ == "__main__":
    main()
