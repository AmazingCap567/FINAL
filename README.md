# Motor de predicción de rating y riesgo de entidades financieras (SBS Perú)

Manual del proyecto. Pensado para que alguien sin contexto previo pueda
entender qué hace el motor, por qué está organizado así, y cómo correrlo.

---

## 1. ¿Qué hace este proyecto? (en lenguaje llano)

Perú tiene ~49 entidades financieras supervisadas por la SBS (bancos,
cajas municipales, cajas rurales y financieras). Cada semestre, hasta 6
clasificadoras de riesgo privadas (ECR: APOYO, CLASS, JCR, MICRORATE,
MOODYS, PCR) les asignan una **calificación crediticia** (parecida a un
rating de bonos: A+, A, A-, B+... hasta E). Esa calificación resume qué
tan sólida está la entidad.

Este motor hace dos cosas:

1. **Predice qué calificación le va a poner cada ECR a cada entidad en el
   próximo semestre**, usando sus estados financieros históricos (activos,
   cartera, morosidad, liquidez, solvencia, etc.). Es un problema de
   clasificación **ordinal** (las categorías están ordenadas: A+ es mejor
   que A, que es mejor que A-, etc.), no una clasificación cualquiera.
2. **Estima el riesgo de deterioro fuerte** de una entidad (una caída
   grande de calificación, el tipo de señal que suele preceder a una
   intervención de la SBS), como objetivo adicional al rating.

**Lo que este proyecto NO hace (todavía):** no tiene interfaz gráfica. Es
el motor de cálculo. Genera archivos Excel limpios (`outputs/interfaz/`)
pensados para que una interfaz futura los lea directamente, sin tener que
re-ejecutar el entrenamiento.

### ¿Por qué importa esto?

Una entidad financiera que se deteriora sin que nadie lo note a tiempo
puede terminar intervenida por la SBS (ver sección 6): sus depositantes y
la estabilidad del sistema financiero están en juego. Anticipar una
caída de calificación (o el riesgo de una intervención) con meses de
anticipación tiene valor real para reguladores, inversionistas y para la
propia gestión de riesgo de las entidades.

---

## 2. Requisitos

```bash
Python 3.10+
pip install -r requirements.txt
```

Incluye: pandas, numpy, scikit-learn, torch (CPU), **mord** (regresión
ordinal), **lightgbm**, openpyxl, lxml, beautifulsoup4, shap (opcional).

---

## 3. Mapa de carpetas

```
data/                          Datos fuente (no se modifican)
├── dataset_bancos.csv
├── dataset_caja_municipal.csv
├── dataset_financieras.xlsx
├── dataset_crac.xlsx
└── clasificaciones/           9 archivos .xls (en realidad HTML) de la SBS,
                                uno por corte semestral MAR2022..MAR2026

motor/                         El motor de predicción en sí
├── config.py                  Rutas, escalas, umbrales, diccionarios de
│                               homologación — la "configuración maestra"
├── utils.py                   Logging con formato de secciones
├── datos/                     Carga, homologación de entidades, integración
│   ├── sbs_loader.py             temporal (anti-fuga), eventos de riesgo
│   ├── financial_loader.py
│   ├── entity_homology.py
│   ├── ratings.py
│   ├── dataset_builder.py
│   └── eventos_intervencion.py   Tabla curada de 4 intervenciones SBS reales
├── features/                  Ingeniería y selección de variables
│   ├── feature_engineering.py    Lags, variaciones, tendencias
│   └── selection.py              Filtro + selección final (RandomForest)
├── modelos/                   Los 4 modelos comparables, cada uno en su
│   │                           propia carpeta con la misma interfaz
│   │                           (entrenar(X, y) -> modelo; predecir(modelo, X) -> preds)
│   ├── modelo_1_hist_gradient_boosting/
│   ├── modelo_2_mlp_ordinal/      (red neuronal PyTorch, multi-tarea)
│   ├── modelo_3_regresion_ordinal/ (mord, interpretable)
│   ├── modelo_4_lightgbm/
│   └── comparacion/
│       ├── baselines_piso.py      Mayoría / persistencia (NO son de los 4)
│       └── seleccion.py           Metodología reproducible del ganador
├── entrenamiento/              (reservado para orquestación futura)
└── evaluacion/                 Métricas, validación temporal, explicabilidad,
                                 reporte HTML

dataset_variables/              Qué variables usa REALMENTE el motor,
├── banco/                      por tipo de entidad (no una lista teórica)
├── cmac/
├── crac/
└── financiera/
    ├── variables_entrenamiento.xlsx
    ├── variables_descripcion.xlsx
    └── resumen_variables.txt

outputs/
├── interfaz/                   Salidas LIMPIAS para la futura interfaz
│                                (un Excel por tipo de entidad + consolidado)
└── analisis/                   Todo lo auxiliar: métricas detalladas,
    ├── auditoria/               artifacts del modelo, reporte HTML.
    ├── predicciones/            La interfaz NUNCA debería necesitar leer
    ├── reporte/                 nada de aquí.
    ├── artifacts/
    └── entidades_excluidas/     Historial de clasificaciones y ficha de
        ├── CMAC/                evento de las entidades excluidas de la
        ├── CRAC/                proyección por intervención/disolución
        └── FINANCIERA/          (1 libro Excel por artefacto x tipo,
                                   1 hoja por entidad — ver sección 9)

scripts/
├── run_evaluacion.py           Evalúa los 4 modelos contra el holdout
│                                conocido (MAR2026) y elige el ganador por ECR
├── run_prediccion.py           Genera la predicción real hacia el futuro
│                                (corte SEP2026) y escribe outputs/interfaz/
├── generar_dataset_variables.py  Genera dataset_variables/ por tipo de entidad
└── exportar_entidades_excluidas.py  Actualiza (idempotente) ficha de evento
                                 + historial de clasificaciones de las
                                 entidades excluidas por intervención SBS
```

---

## 4. Cómo ejecutar

```bash
cd MASTER_PREDICTION_V2

# 1. Evaluar los 4 modelos contra el holdout conocido (MAR2026)
python scripts/run_evaluacion.py

# 2. Generar la documentación de variables por tipo de entidad
python scripts/generar_dataset_variables.py

# 3. Generar la predicción real hacia el futuro (para la interfaz)
python scripts/run_prediccion.py

# 4. Actualizar ficha de evento + historial de clasificaciones de las
#    entidades excluidas por intervención/disolución SBS (sección 9)
python scripts/exportar_entidades_excluidas.py
```

Cada script imprime en consola un resumen legible por secciones. Los
detalles exhaustivos (tablas completas, matrices de confusión) van a
`outputs/analisis/`, no a la consola, para no saturarla.

---

## 5. Los 4 modelos comparables

| # | Modelo | Librería | Por qué se incluye |
|---|---|---|---|
| 1 | HistGradientBoosting | scikit-learn | Robusto, no lineal, referencia estándar |
| 2 | MLP ordinal multi-tarea | PyTorch | Comparte información entre las 6 ECR; predice el *delta* de rating, no el nivel absoluto |
| 3 | Regresión Logística Ordinal | mord | El único que asume explícitamente que las clases están ordenadas; interpretable |
| 4 | LightGBM | lightgbm | Gradient boosting con ponderación de clases nativa (útil para el desbalance) |

**Mayoría** y **Persistencia** (el modelo "no hace nada, asume que no
cambia") existen como piso de referencia en `comparacion/baselines_piso.py`,
pero no compiten como modelos de verdad — si un modelo no le gana a
Persistencia, no aporta valor.

El **ganador por ECR** se elige con un puntaje compuesto (Weighted Kappa +
MAE ordinal + F1 macro, normalizado y ponderado) definido en
`comparacion/seleccion.py`, no por una sola métrica.

---

## 6. Los 8 eventos de salida del mercado usados como referencia

Con solo ~49 entidades y 10 años de historia, no hay suficientes fracasos
reales como para entrenar un clasificador binario de "quiebra" con
confianza estadística. En su lugar, se usa una tabla **curada y verificada
externamente** (`motor/datos/eventos_intervencion.py`) de los 8 casos
reales documentados en el período:

| Entidad | Fecha | Qué pasó |
|---|---|---|
| CRAC Raíz | ago-2023 | Intervenida y liquidada (deterioro de solvencia) |
| Amérika Financiera | ago-2022 | Disolución voluntaria (falló su fusión con Banco Pichincha) |
| CMAC Sullana | jul-2024 | Intervenida y liquidada; cartera transferida a CMAC Piura |
| Financiera Credinka | sep-2024 | Intervenida (deterioro acelerado de solvencia) |
| Deutsche Bank Perú | jun-2016 | Disolución voluntaria (retiro global del banco de 10 países) |
| CRAC Sipán | sep-2021 | Disolución voluntaria (deterioro financiero agravado por la pandemia) |
| Financiera TFC S.A. | dic-2019 | Intervenida y liquidada (reducción de patrimonio efectivo >50% en 12 meses) |
| CRAC Cajamarca | jul-2016 | **Fusión por absorción** por Financiera Credinka (no es un fracaso) |

Cada fila tiene su resolución SBS y fuente. Esta tabla se usa para: (a)
excluir a esas entidades de predicciones futuras después de su fecha de
intervención/disolución/fusión (nunca se les "inventa" un futuro), y (b)
validar cualitativamente que el proxy de riesgo (deterioro de rating)
efectivamente se elevó antes de cada evento de deterioro real (no aplica a
CRAC Cajamarca, que no fue un caso de deterioro sino una fusión).

**Importante:** dos de estas entidades (CMAC Sullana y Credinka) siguieron
reportando datos financieros después de ser intervenidas (el reporte
contable continúa durante el traspaso de cartera). Por eso la tabla está
curada manualmente y verificada contra fuentes externas, en vez de
inferirse solo de "la entidad deja de aparecer en los datos".

### 6.1 Corrección 2026-09: 4 entidades que seguían "vivas" en la proyección

**Síntoma detectado:** la proyección SEP2026 (`outputs/interfaz/`) seguía
generando una fila de predicción para **Deutsche Bank Perú, CRAC
Cajamarca, CRAC Sipán y Financiera TFC S.A.**, pese a que ninguna de las 4
tiene dato financiero ni clasificación SBS reciente:

| Entidad | Último dato financiero | GAP hasta SEP2026 |
|---|---|---|
| Deutsche Bank Perú | jun-2016 | 123 meses |
| CRAC Cajamarca | jul-2016 | 122 meses |
| CRAC Sipán | ago-2021 | 61 meses |
| Financiera TFC S.A. | nov-2019 | 82 meses |

**Causa raíz:** `scripts/run_prediccion.py::build_inference_rows` toma,
para cada entidad, su **último** dato financiero disponible sin ventana de
lookback (a diferencia del entrenamiento, que sí usa
`config.MAX_LOOKBACK_MONTHS`), y confía en
`dataset_builder.excluir_posteriores_a_intervencion` para filtrar
entidades que ya salieron del mercado. Como estas 4 no estaban en
`eventos_intervencion.py`, no había ninguna fecha límite contra la cual
filtrarlas, y el motor terminaba prediciendo un "futuro" con datos de hace
5 a 10 años para entidades que en realidad ya no existen como tales.

**Verificación:** ninguna de las 4 aparece en las clasificaciones SBS
`MAR2022` en adelante (se revisaron los 21 archivos de
`data/clasificaciones/`), y se confirmó cada salida contra fuente externa
(ver tabla de la sección 6 y comentarios en `eventos_intervencion.py`).

**Sobre cambios de nombre (lo pedido explícitamente):** de las 4, **3 son
salidas reales** (disolución voluntaria o intervención — mismo tratamiento
que los 4 casos ya existentes) y **1 es un caso de homología distinto**:

- **CRAC Cajamarca no quebró ni cambió de razón social.** Fue **absorbida
  por fusión** por Financiera Credinka S.A. en 2016 (Res. SBS N.°
  4169-2016). Es un caso distinto al patrón ya resuelto de
  `config.FINANCIAL_ENTITY_CONTINUITY_RENAMES` (que sirve para UNA MISMA
  entidad que cambia de nombre dentro de su propia serie financiera, sin
  traslape — el caso de CrediScotia → Financiera Santander Consumer):
  aquí una entidad entera (CRAC Cajamarca) desaparece dentro del balance
  de **otra** entidad preexistente (Financiera Credinka), que ya tiene su
  propia serie financiera independiente. Fusionar sus `ENTITY_ID` habría
  corrompido el historial de Credinka. **Acción tomada:** en vez de tocar
  la homología, se agregó CRAC Cajamarca a `eventos_intervencion.py` con
  `TIPO_EVENTO="FUSION_POR_ABSORCION"`, reutilizando el mismo mecanismo de
  exclusión de predicción futura (efecto práctico equivalente: no se le
  inventa un futuro como entidad separada). Nota adicional: la entidad
  absorbente, Financiera Credinka, ya está excluida de la proyección
  SEP2026 por su propia intervención posterior (sep-2024), así que ninguna
  de las dos entidades relacionadas genera predicción.
- Deutsche Bank Perú, CRAC Sipán y Financiera TFC S.A. **no tuvieron**
  cambio de razón social; se agregaron a `eventos_intervencion.py` con el
  mismo tratamiento (`DISOLUCION_VOLUNTARIA` / `INTERVENCION_Y_LIQUIDACION`)
  que las entidades ya existentes en la tabla.

**Corrección aplicada:**
1. `motor/datos/eventos_intervencion.py`: se agregaron las 4 entradas
   (fuente y resolución SBS verificadas, ver el archivo).
2. `outputs/interfaz/predicciones_SEP2026_*.xlsx`: se regeneraron sin las
   4 entidades (la exclusión ocurre después de la inferencia del modelo,
   por lo que no fue necesario reentrenar: las predicciones de las
   entidades restantes no cambian).
3. `outputs/analisis/entidades_excluidas_por_intervencion_SEP2026.csv`: se
   agregaron las 4 filas nuevas.
4. `outputs/analisis/entidades_excluidas/`: se corrieron
   `scripts/exportar_entidades_excluidas.py` para generar ficha de evento
   + historial de clasificaciones de las 4 (nueva carpeta `BANCO/` para
   Deutsche Bank Perú; nuevas hojas en `CRAC/` y `FINANCIERA/` — las hojas
   de las entidades ya existentes no se tocaron, por diseño idempotente).

**Nota de alcance:** esta auditoría se limitó a las 4 entidades reportadas.
Dado que la causa raíz es estructural (`build_inference_rows` no valida
antigüedad del dato ni presencia en clasificaciones recientes, solo
depende de que la entidad esté en `eventos_intervencion.py`), se
recomienda como mejora futura agregar una alerta automática en
`run_prediccion.py` cuando `GAP_MESES` de una entidad supere un umbral
(p. ej. 24 meses) y no tenga evento registrado, para no depender solo de
que un analista lo note manualmente.

**Proxy de riesgo continuo (SCORE_DETERIORO / DOWNGRADE_FUERTE):** una
entidad "dispara" este target cuando su calificación cae 2 o más
escalones en un mismo corte, en cualquier ECR. El umbral de 2 se eligió
mirando la distribución real de cambios de rating (las caídas de 1
escalón son comunes y no distinguen mucho; las de 2+ son raras — ~1.5%
de los casos — y coinciden con varios de los eventos reales de la tabla
de arriba).

---

## 7. Metodología: anti-fuga y validación temporal

Regla de oro del proyecto: **para predecir en una fecha, el modelo solo
puede usar información que ya existía en esa fecha.**

- Cada fila del dataset usa el último dato financiero **estrictamente
  anterior** a la fecha de clasificación objetivo (ventana máxima
  configurable). El pipeline se detiene con un error si detecta alguna
  fila con `FECHA_BASE >= FECHA_TARGET`.
- Toda imputación, escalado y selección de variables se ajusta
  ÚNICAMENTE con el conjunto de entrenamiento; nunca con validación,
  holdout, o los datos de predicción futura.
- **Holdout de evaluación: MAR2026** (el corte más reciente con
  clasificación real publicada). Validación (early stopping del MLP):
  SEP2025. Entrenamiento: todos los cortes anteriores.
- Además del holdout único, hay validación **walk-forward** (se repite el
  entrenamiento avanzando el corte de prueba varias veces) para confirmar
  que el desempeño no depende de haber elegido "el mejor" corte de prueba
  por casualidad.

---

## 8. Glosario

- **ECR**: Empresa Clasificadora de Riesgo (agencia de rating): APOYO,
  CLASS, JCR, MICRORATE, MOODYS, PCR.
- **CMAC**: Caja Municipal de Ahorro y Crédito.
- **CRAC**: Caja Rural de Ahorro y Crédito.
- **Rating ordinal**: la calificación (A+, A, A-, ..., E) representada
  como un número (0 = mejor, más alto = peor) para poder hacer aritmética
  ordenada con ella (comparar, restar, calcular error promedio).
- **Notch / escalón**: un paso en la escala de rating (de B+ a B es 1
  notch).
- **Delta de rating**: diferencia entre el rating nuevo y el anterior, en
  notches. Positivo = empeoró (downgrade); negativo = mejoró (upgrade).
- **Holdout**: el corte de datos que el modelo nunca ve durante el
  entrenamiento, reservado para medir qué tan bien generaliza.
- **Walk-forward**: validación que repite el entrenamiento avanzando la
  fecha de corte de prueba varias veces, en vez de usar un único holdout.
- **Fuga de información (data leakage)**: cuando el modelo usa,
  accidentalmente, información que en la realidad no habría estado
  disponible en el momento de la predicción.
- **Weighted Kappa**: métrica de acuerdo ordinal que penaliza más los
  errores grandes (predecir E cuando era A+) que los pequeños (predecir A
  cuando era A-).

---

## 9. Exclusión de entidades quebradas/intervenidas/fusionadas de la proyección SEP2026

Antes de generar la proyección hacia SEP2026 se auditaron las 8 entidades de
`motor/datos/eventos_intervencion.py` (ver sección 6, incluida la sección
6.1 con la corrección de 2026-09) contra la fecha de validación del corte a
predecir. Las 8 tienen fecha de evento **anterior** a SEP2026, por lo que
**se excluyen** de la nueva proyección (no se les "inventa" un futuro tras
haber sido intervenidas/disueltas/fusionadas):

| Entidad | Tipo | Evento | Fecha |
|---|---|---|---|
| CMAC Sullana | CMAC | Intervención y liquidación | 2024-07-11 |
| CRAC Raíz | CRAC | Intervención y liquidación | 2023-08-10 |
| Amérika Financiera | FINANCIERA | Disolución voluntaria | 2022-08-26 |
| Financiera Credinka | FINANCIERA | Intervención | 2024-09-19 |
| Deutsche Bank Perú | BANCO | Disolución voluntaria | 2016-06-12 |
| Financiera TFC S.A. | FINANCIERA | Intervención y liquidación | 2019-12-12 |
| CRAC Sipán | CRAC | Disolución voluntaria | 2021-09-28 |
| CRAC Cajamarca | CRAC | Fusión por absorción (Financiera Credinka) | 2016-07-27 |

Esto ya estaba implementado en `dataset_builder.excluir_posteriores_a_intervencion`
y se refleja en `outputs/analisis/entidades_excluidas_por_intervencion_SEP2026.csv`
(las 4 últimas filas se agregaron en la corrección de 2026-09, ver 6.1).

**Sobre cambios de nombre:** se revisó si alguna de las 8 entidades tuvo un
cambio real de razón social (como el caso ya homologado de CrediScotia
Financiera → Financiera Santander Consumer S.A. en
`config.FINANCIAL_ENTITY_CONTINUITY_RENAMES`, que es una entidad distinta y
sigue activa). **Conclusión: ninguna de las 8 cambió de razón social**
dentro del período de datos — sí hay **una fusión por absorción** (CRAC
Cajamarca, absorbida por Financiera Credinka en 2016), que es un patrón
distinto a un simple cambio de nombre y se resolvió en la tabla de eventos,
no en el diccionario de homología (ver justificación en la sección 6.1).
Lo que sí existe, y ya estaba resuelto por el sistema de homologación
(`motor/datos/entity_homology.py` + `config.ENTITY_NAME_OVERRIDES`), son
abreviaturas/etiquetas distintas entre el nombre que usa la SBS en los
archivos de clasificaciones y el nombre del dataset financiero (p. ej.
`"CRAC RAIZ EN LIQUIDA"` → `"CRAC RAIZ"`, `"AMERIKA FINANC. EL"` →
`"AMERIKA FINANCIERA"`, `"FINANC. CREDINKA"` → `"FINANCIERA CREDINKA"`,
`"CRAC SIPAN LIQUID."` → `"CRAC SIPAN"`, `"FINANCIERA TFC EL"` →
`"FINANCIERA TFC S.A."`; CMAC Sullana, Deutsche Bank Perú y CRAC Cajamarca
homologan 1:1 sin necesidad de override). Se verificó ejecutando el
pipeline de homología que las 8 resuelven correctamente a un único
`ENTITY_ID` canónico — los overrides para Sipán y TFC ya existían en
`config.ENTITY_NAME_OVERRIDES` (se usaban para el entrenamiento histórico);
lo que faltaba no era homología sino la entrada en la tabla de eventos que
las excluyera de la proyección *futura*.

### 9.1 Archivos generados para las entidades excluidas

`scripts/exportar_entidades_excluidas.py` (lógica en
`motor/datos/export_entidades_excluidas.py`) genera/actualiza, para cada
entidad excluida, **únicamente** estos dos artefactos:

1. **Historial de clasificaciones por clasificadora (ECR)**: estructura
   análoga a `data/clasificaciones/<CORTE>.xls` (columnas `Tipo de Entidad`,
   `Entidad` + una columna por ECR: APOYO, CLASS, JCR, MICRORATE, MOODYS,
   PCR), pero con **una fila por corte semestral** (todo el historial
   disponible) en vez de una fila por entidad por archivo. Las filas de
   cortes en o después de la fecha del evento quedan resaltadas.
2. **Ficha de evento**: tipo de evento, fecha, resolución SBS, descripción,
   fuente, último corte disponible y N° de cortes con datos.

```bash
python scripts/exportar_entidades_excluidas.py
```

Salida en `outputs/analisis/entidades_excluidas/`, **una carpeta por tipo
de entidad** y, dentro, **un solo libro Excel por tipo de artefacto** (no
uno por entidad): cada entidad excluida es una **hoja** dentro de ese
libro.

```
outputs/analisis/entidades_excluidas/
├── CMAC/
│   ├── historial_clasificaciones_CMAC.xlsx   (hoja: CMAC Sullana)
│   └── ficha_evento_CMAC.xlsx                (hoja: CMAC Sullana)
├── CRAC/
│   ├── historial_clasificaciones_CRAC.xlsx   (hoja: CRAC RAIZ)
│   └── ficha_evento_CRAC.xlsx                (hoja: CRAC RAIZ)
└── FINANCIERA/
    ├── historial_clasificaciones_FINANCIERA.xlsx  (hojas: Amérika Financiera, Financiera Credinka)
    └── ficha_evento_FINANCIERA.xlsx               (hojas: Amérika Financiera, Financiera Credinka)
```

**Reglas de actualización (idempotente — seguro de re-ejecutar cada vez que
se corre el pipeline, p. ej. si un corte futuro agrega una nueva entidad
quebrada):**

- **Carpeta** (por tipo de entidad): si `config.EXCLUIDAS_DIR/<TIPO>` ya
  existe se reutiliza tal cual; si no existe, se crea.
- **Libro Excel** (por tipo de artefacto × tipo de entidad): si el archivo
  ya existe en disco, se abre y se conserva; si no existe, se crea uno
  nuevo.
- **Hoja** (por entidad): si la hoja de esa entidad ya existe en el libro,
  se reemplaza con los datos actuales (refleja cortes nuevos); si no
  existe, se agrega. Las hojas de **otras** entidades ya presentes en el
  mismo libro —incluidas hojas agregadas manualmente por un analista— **no
  se tocan**.

---

## 10. Limitaciones conocidas de esta etapa (resuelta)

- El modelo 2 (MLP) requiere PyTorch; en entornos sin GPU/con poco
  espacio en disco puede ser el más costoso de instalar.
- Con muestras tan chicas por tipo de entidad (6 a 19 entidades), toda
  métrica de desempeño debe leerse con cautela — no hay volumen para
  intervalos de confianza estrechos.
- El proxy de riesgo (`DOWNGRADE_FUERTE`) es una aproximación interna,
  no una clasificación oficial de riesgo de la SBS ni de ninguna ECR.
- No hay interfaz gráfica todavía; esa es la siguiente etapa del
  proyecto, y consumirá directamente los archivos de `outputs/interfaz/`.
