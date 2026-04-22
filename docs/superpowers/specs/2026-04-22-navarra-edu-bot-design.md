# Navarra Edu Bot — Automatización de adjudicación telemática

**Fecha:** 2026-04-22
**Autor:** Vicente Tanco Aguas
**Estado:** Diseño aprobado, pendiente plan de implementación

---

## 1. Contexto y problema

El Gobierno de Navarra publica ofertas de plazas docentes en su portal de adjudicación telemática (`https://appseducacion.navarra.es/atp/index.xhtml`) de lunes a viernes. La ventana de aplicación abre a las 14:00 y el criterio de adjudicación es **primero en solicitar, primero en adjudicar**. Las ofertas se publican entre las 13:30 y las 14:00.

- **Lunes / Martes / Miércoles / Viernes**: solo pueden aplicar quienes figuren como `Disponible` en la lista correspondiente.
- **Jueves**: convocatoria abierta — cualquier persona con formación compatible puede aplicar, con lo que la carrera es extrema.

El portal es frágil bajo carga (especialmente los jueves): sesiones caen, errores 5xx, timeouts. Aplicar manualmente es estresante y, en jueves, casi siempre se pierde frente a postulantes más rápidos.

**Objetivo:** automatización local que detecte ofertas compatibles, notifique al usuario por Telegram para que pre-seleccione las que le interesan, y dispare las aplicaciones en el instante `14:00:00.000` con latencia <500 ms, superando de forma consistente a postulantes humanos.

---

## 2. Perfil del usuario y datos estáticos

- **Grado y Máster**: Ingeniería en Tecnologías Industriales.
- **Máster de Formación del Profesorado (MUFPS)**: pendiente de confirmación del usuario (bloqueante para Secundaria).
- **Localidades preferidas**: Pamplona, Orkoien/Orcoyen, Barañáin.
- **Jornada preferida**: completa > parcial.
- **Especialidades preferidas (orden)**: Tecnología > Matemáticas > Dibujo > resto.

### Listas donde el usuario está `Disponible` (estático, hardcodeado en config)

Aplicables L / M / X / V:

- 0590 Equipos Electrónicos (posición 361)
- 0590 Organización y Proyectos de Fabricación Mecánica (577)
- 0590 Sistemas Electrotécnicos y Automáticos (481)
- 0590 Sistemas Electrónicos (360)
- 0590 Tecnología — CONVOCATORIA (1378)
- 0598 Fabricación e Instalación de Carpintería y Mueble (273)
- 0598 Mantenimiento de Vehículos (459)

### Listas donde el usuario está `Excluido` (no aplicables L/M/X/V, sí los jueves si la formación lo permite)

- 0590 Física y Química
- 0590 Matemáticas
- 0590 Procesos y Productos en Madera y Mueble
- 0590 Tecnología (lista GENERAL, distinta de CONVOCATORIA)

### Correspondencia formación → especialidades (jueves)

Para los jueves, se cruza el título de Ingeniería en Tecnologías Industriales con el **RD 276/2007** y el **RD 800/2022** (especialidades de los cuerpos 0590 y 0598). Se documentará con citas oficiales en `docs/formacion-especialidades.md` durante Fase 2 y el usuario lo revisará antes de su uso real en Fase 5.

Candidatas iniciales (a confirmar con RD): Tecnología, Sistemas Electrónicos, Sistemas Electrotécnicos y Automáticos, Equipos Electrónicos, Organización y Proyectos de Fabricación Mecánica, Matemáticas, Física y Química, Dibujo, Mantenimiento de Vehículos, Fabricación e Instalación de Carpintería y Mueble.

---

## 3. Flujo diario (L–V)

```
13:20  pmset wake schedule → equipo despierta
13:25  launchd arranca el bot
       caffeinate ON (evita sleep hasta 14:05)
       health-check red + NTP sync
       login Educa desde Keychain

13:30  comienza polling de ofertas cada 15 s
  │    por cada oferta nueva:
  │      filter.apply() → elegibilidad + ranking
  │      telegram_bot.notify() con botones ✅/❌
  │      storage.mark_seen()
  │
  │    usuario pulsa botones → storage.preselected[]
  │
13:45  recordatorio Telegram si hay ofertas sin decidir
13:55  segundo recordatorio
13:58  pre-navegación agresiva: cada oferta pre-seleccionada
       queda cargada en su propio contexto Playwright
       justo antes del submit final
13:59:30  health-check de sesión; re-login si cayó
13:59:50  sntp sync final con hora.rediris.es
13:59:58  warm-up HTTP request (TLS handshake precalentado)

14:00:00.000  ┌──────────────────────────────────────┐
              │ asyncio.gather: submit paralelo      │
              │ por cada oferta pre-seleccionada.    │
              │ Preferencia: POST HTTP directo con   │
              │ cookies; fallback a click Playwright.│
              └──────────────────────────────────────┘

14:00-14:05   verificación: consulta "mis aplicaciones del día"
              reconciliar resultados (aplicada / fallo / duplicada)
              reporte final por Telegram
              caffeinate OFF; exit

Si el usuario NO pre-seleccionó nada antes de 14:00:00 → no aplica.
```

---

## 4. Arquitectura

### Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Navegador | Playwright (Chromium) |
| Telegram | `python-telegram-bot` v21 (async) |
| HTTP directo | `aiohttp` (para fast-path submit) |
| Programación | `launchd` (macOS) |
| Keep-awake | `caffeinate -dims` |
| Credenciales | macOS Keychain vía `security` CLI |
| Config | YAML en `~/.navarra-edu-bot/config.yaml` |
| Persistencia | SQLite (`~/.navarra-edu-bot/state.db`) |
| Logs | `structlog` con rotación diaria |
| Tests | `pytest` + fixtures HTML |

### Módulos

```
navarra_edu_bot/
├── scheduler/         arranque, caffeinate, bucle de fases, watchdog
├── scraper/           login Educa, parsing ofertas (Playwright)
├── filter/            reglas por día, ranking, elegibilidad
├── telegram_bot/      notificaciones, callbacks de botones
├── applicator/        submit a 14:00:00.000, fast-path jueves
├── config/            carga YAML, lectura Keychain, validación
├── storage/           SQLite: ofertas, decisiones, historial
└── notifier/          alertas críticas
```

### Flujo de datos

```
launchd → scheduler
           ├─► scraper.login()            [Keychain → cookies]
           ├─► loop 13:30-13:59:
           │     scraper.fetch_offers()
           │     filter.apply()
           │     storage.mark_seen()
           │     telegram_bot.notify(new)
           │     ← callbacks → storage.preselected
           ├─► 13:58: pre-warm contexts
           ├─► 13:59:30: session_healthcheck + NTP
           ├─► 14:00:00.000: applicator.fire_parallel()
           ├─► reconcile + report
           └─► caffeinate OFF, exit
```

### Decisiones clave

- **Playwright headless** con user-agent realista. Fallback a headed si el portal detecta automatización.
- **Login una vez por sesión**, cookies en memoria; no se persisten a disco.
- **Polling 15 s** — balance entre detección rápida y no saturar el portal.
- **Doble contexto warm-standby** (primario + secundario) activo desde 13:58.
- **Fast-path jueves**: pre-navegación + `asyncio.gather` + POST directo con cookies.
- **NTP sync** a `hora.rediris.es` a las 13:59:50 para evitar drift del reloj.

---

## 5. Resiliencia de sesión

El portal pierde sesiones bajo carga, sobre todo los jueves. Salvaguardas:

- Health-check de sesión a las 13:59:30 (petición autenticada ligera); re-login si 401/login-wall.
- Cada respuesta del scraper comprueba si devuelve login screen; si sí, reauth + reintento.
- Backoff agresivo durante la ventana crítica: 100 ms, 300 ms, 700 ms, 1.5 s.
- Warm-standby: dos contextos Playwright con sesión válida desde 13:58; si el primario cae, el secundario dispara sin esperar re-login.
- Presupuesto total de reintentos por oferta: 30 s.
- Logs con status codes, latencias y cookies durante 13:59–14:01.

---

## 6. Fast-Path Jueves (optimización crítica)

Los jueves la velocidad pura determina si se gana la plaza.

- **Pre-navegación desde 13:58**: cada oferta pre-seleccionada carga su pantalla previa al submit en un contexto Playwright propio. Queda todo listo salvo el último click.
- **N contextos paralelos** (máx. 5 o lo que `config.yaml` fije).
- **Trigger a `14:00:00.000` exactos** vía reloj monotónico sincronizado por NTP.
- **POST HTTP directo** con cookies de la sesión Playwright (más rápido que emular click). Fallback a click si el POST falla en validación.
- **Warm-up HTTP a 13:59:58** para que el handshake TCP/TLS no pese en el disparo.
- **Latencia objetivo**: < 500 ms entre `14:00:00.000` y recepción del submit por el servidor.
- **Métrica por oferta**: `t_trigger`, `t_submit_sent`, `t_response_received`.

---

## 7. Seguridad

- **Credenciales Educa**: solo en macOS Keychain, accedidas vía `security find-generic-password`.
- **Token Telegram**: en Keychain.
- **Nunca** en logs, en mensajes Telegram, ni en el repositorio.
- `config.yaml` no contiene secretos; solo preferencias y datos estáticos.
- El repositorio se mantiene local; si se versiona en GitHub, será privado.
- Logs rotan y se purgan a los 30 días.

---

## 8. Riesgos y mitigación

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Mac apagado/suspendido | Día perdido | `pmset wake schedule` 13:20 + `caffeinate` + alerta Telegram si no arranca |
| Sin red | Día perdido | Health-check 13:28; alerta Telegram "aplica manualmente" |
| Cambio de DOM | Aplicación errónea | Selectores estables (`name`/`id`) + snapshot tests diarios a las 12:00 |
| Sesión caída (jueves) | Fallo submit | Doble contexto warm-standby + backoff + reauth automático |
| Aplicación duplicada | Conflicto con RRHH | Reconciliación post-submit contra "mis aplicaciones del día" |
| Respuesta tardía | Oferta perdida | Recordatorios Telegram a 13:45 y 13:55 |
| Bug aplica a algo no deseado | Problema real | Dry-run obligatorio 10+ días laborables antes de submit real |
| Credenciales filtradas | Cuenta comprometida | Solo Keychain; auditoría de que no aparecen en logs |
| Bot colgado | Día perdido silencioso | Watchdog launchd separado cada 5 min |
| CAPTCHA tras intentos fallidos | Bloqueo | Máx 3 reintentos de login; alerta con enlace para resolverlo a mano |

---

## 9. Modo dry-run

Flag `dry_run: true` por defecto en config.

- Ejecuta login, fetch, filter, ranking, pre-navegación y todo el flujo de submit **excepto** el POST/click final.
- Telegram recibe "HUBIERA aplicado a: {ofertas}" con detalle de timing.
- Solo se pasa a `dry_run: false` tras **10 días laborables reales** sin discrepancias.

---

## 10. Plan de pruebas

**Unitarios (pytest):**

- `filter`: reglas por día, ranking, localidades, especialidades, con ofertas sintéticas.
- `scraper`: parsing contra fixtures HTML (portal real capturado), casos "sesión expirada", "500", "sin ofertas".
- `applicator`: submit con mock server que simula éxito/fallo/timeout.

**Integración (local):**

- `test_login.py`: valida credenciales y flujo de login contra el portal real.
- `test_dry_run.py`: ciclo completo fuera de las 14:00 con submit desactivado.

**Canary diario 12:00:**

- Job que hace login + fetch + logout. Notifica Telegram si falla algo estructural antes de la ventana real.

**Comandos Telegram:**

- `/status` → estado del bot, última ejecución, próxima programada.
- `/test` → ciclo dry-run bajo demanda.

**Observabilidad:**

- Tabla SQLite `events` con timestamp de nanosegundos durante 13:59–14:01.
- Export CSV semanal por Telegram: ofertas vistas, aplicadas, fallos, latencias.

---

## 11. Fases de entrega

| Fase | Alcance | Criterio de finalización |
|---|---|---|
| **0 — Scaffold** | Repo, dependencias, Playwright, bot Telegram creado, `launchd` plist preparado | Ping "Hola" recibido en Telegram |
| **1 — Login + fetch dry** | `scraper.login` + `scraper.fetch_offers` + CLI `fetch --dry` | Usuario verifica parsing varios días contra portal real |
| **2 — Filter + ranking + Telegram** | Reglas por día, ranking, investigación formación→especialidades, mensaje Telegram con botones | Un día laborable real: mensajes recibidos, botones funcionales, selecciones en SQLite |
| **3 — Scheduler + watchdog** | `launchd` activo, `caffeinate`, canary 12:00, comandos `/status` `/test` (aún sin applicator) | Semana laborable completa: bot arranca solo a las 13:25, notifica ofertas, recibe botones y registra selección sin aplicar — todo sin intervención manual |
| **4 — Applicator dry-run** | Pre-navegación, NTP, warm-standby, fast-path jueves implementado con submit inhabilitado | 10 días laborables sin discrepancias en logs |
| **5 — Activación real** | Flip de `dry_run: false` | Primer día con usuario presente; semana de observación |
| **6 — Post-MVP (opcional)** | Pre-autorización, estadísticas, migración a VPS | Solo si el usuario lo pide |

**Regla innegociable:** no se activa submit real (Fase 5) hasta que Fase 4 haya corrido ≥10 días laborables.

---

## 12. Fuera de alcance

- Días no laborables.
- Pre-autorización ("aplica siempre a X sin preguntar") — posible en Fase 6 si se pide.
- Gestión de adjudicaciones ya obtenidas, apelaciones, toma de posesión.
- Cambios en las listas del usuario (son estáticas en este diseño; si cambian, se edita `config.yaml`).
- Ejecución en la nube (el diseño es Mac local; Fase 6 contempla VPS).

---

## 13. Consideraciones legales y éticas

- La automatización de la participación en adjudicaciones públicas opera en zona gris. Se asume que el usuario es legalmente responsable de cada aplicación enviada en su nombre.
- El bot no simula identidades ni elude CAPTCHAs de forma adversarial: usa credenciales legítimas del usuario.
- El polling cada 15 s es conservador y no constituye denegación de servicio.
- La decisión final (qué aplicar) es humana: el bot solo acelera la ejecución.
- Si en algún momento el Gobierno de Navarra publicara condiciones de uso que prohíban automatización, el usuario se compromete a reevaluar el proyecto.

---

## 14. Glosario

- **0590**: Cuerpo de Profesores de Enseñanza Secundaria.
- **0598**: Cuerpo de Profesores Especialistas en Sectores Singulares de Formación Profesional.
- **Disponible / Excluido**: estado del postulante en una lista de contratación.
- **CONVOCATORIA / GENERAL**: tipos de lista. El usuario está `Disponible` en Tecnología CONVOCATORIA pero `Excluido` en Tecnología GENERAL.
- **MUFPS**: Máster Universitario en Formación del Profesorado de Secundaria.
- **RD 276/2007**, **RD 800/2022**: reales decretos que regulan las especialidades docentes.
