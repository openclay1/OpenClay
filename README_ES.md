# *OpenClay*

Soy un agente de IA local que corre en tu computadora. Te ayudo a organizar tu dia — archivos, documentos, reportes, gastos y tareas que describes en lenguaje natural. Todo se queda en tu equipo.

## Lo que hago cada dia

- **Organizar tus carpetas.** Apuntame a un directorio y lo ordeno, renombro y limpio.
- **Resumir archivos y documentos.** Arrastra PDFs, notas o codigo — extraigo lo importante.
- **Redactar reportes y notas.** Describe lo que necesitas, yo escribo la primera version. Tu la refinas.
- **Rastrear gastos y contabilidad.** Dame recibos o notas de transacciones, genero resumenes que puedes guardar.
- **Investigar y sintetizar.** Haz una pregunta, busco en tu wiki y archivos locales, y te doy una respuesta directa.
- **Ingerir conocimiento a un wiki.** Arrastra articulos, documentos, transcripciones — los archivo en un wiki local que crece con el tiempo.
- **Encontrar duplicados y limpiar.** Escaneo directorios para archivos redundantes y te ayudo a recuperar espacio.
- **Planificar tu dia.** Dime en que estas trabajando, lo desgloso en pasos.

## Que mas puedo hacer

- **Publicar en Twitter** — opcional. Si conectas tus claves API, puedo redactar y publicar tweets. No es necesario para que todo lo demas funcione.
- **Recibir tareas desde tu telefono** — puente WebSocket con codigo QR, entrada de voz, subida de archivos por WiFi local.
- **Sanarme y mejorar** — reintentar llamadas fallidas, auto-corregir errores recurrentes, y correr un ciclo de auto-construccion que solo mantiene cambios que pasan todas las pruebas.
- **Proteger cada entrada y salida** — deteccion de inyeccion de prompts, niveles de permiso (VERDE/AMARILLO/ROJO), validacion de salida.

## Porque no agentes en la nube?

Los agentes de IA en la nube son poderosos. Corren en los servidores de otro, requieren su suscripcion, y tus datos pasan por su infraestructura. Cuando cambian los precios, tu flujo se rompe. Cuando una plataforma pivotea, tu agente desaparece.

OpenClay corre en tu computadora. Tus datos nunca salen. Ninguna suscripcion te puede cortar. Ninguna plataforma puede cambiar las reglas. Misma capacidad. Propiedad total.

## Industrias

- **Salud y ciencias de la vida.** Mantener notas de pacientes, resumenes de investigacion y referencias clinicas en un wiki local que nunca toca un servidor en la nube.
- **Finanzas y contabilidad.** Ingerir registros de transacciones, redactar reportes de gastos y mantener registros de auditoria — todo en hardware que tu controlas.
- **Biotecnologia y laboratorios.** Revisar literatura, analizar reportes de lotes, detectar desviaciones y generar resumenes listos para subvenciones.
- **Veterinaria.** Organizar notas SOAP, generar recordatorios de seguimiento y detectar interacciones de medicamentos.
- **Investigacion y trabajo de conocimiento.** Construir una base de conocimiento que crece con articulos, transcripciones y notas — consultala en lenguaje natural, conservala para siempre.

## Como ejecutarme

```bash
# Opcion 1: doble clic en run_openclay.command (Mac) o run_openclay.bat (Windows)
# No necesitas la terminal.

# Opcion 2: desde codigo fuente
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay
pip3 install -r requirements.txt
python3 openclay_app.py
```

Detecto tu computadora, elijo el modelo correcto, lo instalo y abro la ventana. Lo primero que ves es: *Que necesitas hoy?*

## Arquitectura de memoria (Vibe Brain)

| Nivel | Que es | Cuando se carga | Tamano |
|-------|--------|-----------------|--------|
| L0 | Identidad (SOUL.md) | Siempre | ~100 tokens |
| L1 | Conocimiento a largo plazo (BRAIN.md) | Siempre | <500 palabras |
| L2 | Contexto de tarea actual (SESSION.md) | Siempre | <200 palabras |
| L3 | Decisiones pasadas (DECISIONS.md) | Bajo demanda | Ilimitado |

Memoria en archivos markdown. Sin bases de datos. Sin embeddings. Sin nube.

## 5 Agentes diarios

| Agente | Entrada | Salida |
|--------|---------|--------|
| Notas clinicas | Notas de alta, SOAP | Resumen + acciones + alertas |
| Desviaciones de lab | Registros de lotes, QC | Desviaciones + severidad + correctivos |
| Veterinario | Notas SOAP | Formato estructurado + seguimiento |
| Subvenciones | Resumen de investigacion | Borrador listo para solicitud |
| Administrativo | Correos, memos, reportes | 5 puntos + acciones + borrador de respuesta |

## Licencia

MIT — es tuyo.

*OpenClay — Construido localmente. Corre en silencio. Mejora lentamente. Te responde a ti.*

[github.com/openclay1/OpenClay](https://github.com/openclay1/OpenClay)
