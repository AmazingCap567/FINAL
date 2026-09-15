# Resumen de la actualización — Peru_SBS.html

## Archivos entregados
- **Peru_SBS.html** — interfaz actualizada (misma identidad visual, misma estructura de componentes).
- **actualizar_interfaz.py** — script que debe vivir en `scripts/actualizar_interfaz.py` dentro del
  proyecto. Lee los outputs reales y reinyecta los datos en el HTML cada vez que se corra
  `run_evaluacion.py` / `run_prediccion.py` de nuevo.

## Qué cambié y por qué

### 1. Nueva pestaña "Modelos de Predicción"
Compara los 4 modelos reales (`1-HistGB`, `2-MLPOrdinal`, `3-RegresionOrdinal`, `4-LightGBM`) usando
**exactamente** la metodología de `motor/modelos/comparacion/seleccion.py` (mismos pesos: Weighted
Kappa 35%, MAE ordinal invertido 25%, F1 macro 20%). El ranking por ECR que reconstruí coincide
100% con `outputs/analisis/modelo_ganador_por_ecr.csv` (lo validé por código).

**CLASS no tiene métricas de holdout** en `outputs/analisis/` — se documenta explícitamente y se
excluye del comparativo (no se inventó un dato).

### 2. Pestaña "Predicción Setiembre" — reescrita por completo
Antes: una fórmula local (`projectAgencyRating`) que "proyectaba" un rating extrapolando la
tendencia del último cambio. Esto violaba el requisito de no fabricar predicciones.

Ahora: lee directamente `outputs/interfaz/predicciones_SEP2026_TODAS.xlsx` (146 filas, 44
entidades), con filtros dependientes Tipo de entidad → Entidad, KPIs reales (mejora/estable/
deterioro/excluidas) y una tabla con "N/D" donde una ECR nunca calificó a una entidad (no se
inventa una calificación).

Dato real relevante: en la predicción real, **0 entidades mejoran**, 115 combinaciones
entidad-ECR se mantienen estables y 31 muestran deterioro de 1 escalón — no hay downgrades
fuertes (≥2 escalones). Esto se refleja tal cual en los KPIs.

### 3. Pestaña "Entidades Intervenidas" — reemplazada
Antes: 5 casos históricos mezclados (algunos reales de otras épocas, no verificados contra los
datos del proyecto). Ahora: los **4 eventos reales** de `motor/datos/eventos_intervencion.py`
(CRAC Raíz, Amérika Financiera, CMAC Sullana, Financiera Credinka), con resolución SBS, fuente y
descripción reales.

Agregué un selector + gráfico de evolución histórica de calificación, construido parseando
`data/clasificaciones/*.xls` (los 21 archivos brutos reales de la SBS). Resultado:
- CRAC Raíz: solo 1 corte con dato real (MAR2016, como "EDPYME RAIZ") — se muestra tal cual, sin
  rellenar huecos.
- Amérika Financiera, CMAC Sullana, Financiera Credinka: 14–18 cortes reales cada una.

### 4. Discrepancia de estructura de carpetas (documentada, no inventada)
El prompt original asumía `scripts/exportar_entidades_excluidas.py` y
`outputs/analisis/entidades_excluidas/`. En el proyecto real esos datos están en
`outputs/analisis/entidades_excluidas_por_intervencion_SEP2026.csv` (generado por
`run_prediccion.py`). Usé ese archivo real en su lugar y lo dejo anotado aquí en vez de fabricar
la estructura esperada.

### 5. Lo que NO toqué
- "Resumen", "Análisis Histórico" y "Modelo Predictivo" (simulador what-if de morosidad) se
  mantienen igual — son ilustrativos y así lo dice el proyecto original; solo les agregué una nota
  aclaratoria de una línea para que no se confundan con las secciones de datos reales nuevas.
- La tabla de ratings históricos reales de bancos dentro de "Análisis Histórico" (`RATINGS_DATA`)
  también quedó intacta: es data real, no relacionada con el problema de la fórmula de predicción.

## Cómo se actualiza en el futuro
```bash
python scripts/actualizar_interfaz.py
```
El script valida que existan los archivos de origen, aborta con un mensaje claro si falta alguno,
y solo reemplaza el bloque marcado `/* DATA_START */ ... /* DATA_END */` del HTML — el resto del
archivo (diseño, componentes) no se toca.

## Limitaciones conocidas
- No pude ejecutar un navegador real (sin acceso a red en este entorno) para verificar el
  renderizado pixel-a-pixel. Sí validé exhaustivamente: balance de paréntesis/llaves/corchetes del
  bloque JSX completo, presencia y unicidad de las 6 pestañas, ausencia de identificadores
  duplicados, y una revisión manual línea por línea de las tres pestañas nuevas/reescritas.
- Corregí en el camino un bug real de edición (una variable `tiposEvento` quedó mal fusionada en un
  paso intermedio) — quedó documentado y corregido antes de la entrega final.
