# Anfaia Daily AI 🤖📰

Sistema autónomo **multiagente** que cada día selecciona, contextualiza y publica
en **Discord** una noticia sobre Inteligencia Artificial, agentes IA, robótica,
automatización y open source de IA. No copia la noticia: la **explica, la
contextualiza y genera debate** en una comunidad técnica.

Además publica un **boletín semanal en HTML** (alojado en **GitHub Pages**) que
recopila las noticias más relevantes de la semana —al menos una de cada
categoría— con una **reflexión editorial del conjunto**, y lo **anuncia en
Discord**. Véase «Boletín semanal» más abajo.

Construido con **arquitectura hexagonal (puertos y adaptadores)** para que la
lógica de negocio sea independiente de proveedores (LLM, fuentes, base de datos,
canal de publicación) y pueda evolucionar a frameworks de orquestación como
**LangGraph, CrewAI, DeepAgents o AutoGen** sin reescribir el dominio.

---

## ✨ Características

- **6 agentes** especializados que colaboran en un pipeline:
  1. **News Collector** — recolecta de RSS + APIs y normaliza a `NewsItem`.
  2. **News Classifier** — clasifica (AI, Agents, Robotics, Open Source, Automation, Research) y puntúa relevancia (0-100).
  3. **Duplicate Detector** — evita repetir noticias (URL exacta + similitud semántica por embeddings en PostgreSQL/pgvector).
  4. **News Editor** — convierte la noticia en contenido editorial estructurado.
  5. **Discussion Generator** — genera una pregunta abierta para fomentar debate.
  6. **Discord Publisher** — publica como *embed* con reintentos y gestión de errores.
- **Dos motores de orquestación** seleccionables por configuración (`WORKFLOW_ENGINE`):
  - `sequential` (por defecto): pipeline determinista en código.
  - `deepagents`: la decisión editorial (qué publicar, cómo redactarlo y qué
    preguntar) se delega a un **agente deliberativo** con planificación,
    subagentes (editor-investigador, verificador de hechos, dinamizador) y
    **verificación de la fuente original** vía `fetch_url`. Degrada al motor
    clásico ante cualquier fallo. Véase «Motor deepagents» más abajo.
- **Boletín semanal en HTML** publicado en **GitHub Pages** y anunciado en
  Discord (canal propio opcional): índice navegable + página por semana con
  reflexión editorial del conjunto. Véase «Boletín semanal».
- **Scheduler diario y semanal** (APScheduler) configurables por hora y zona horaria.
- **LLM intercambiable**: OpenAI, Anthropic u OpenRouter.
- **API REST** completa (FastAPI) para operar y observar el sistema.
- **Observabilidad**: logging estructurado (structlog), métricas y healthcheck.
- **Tests** unitarios y de integración con cobertura ≥ 80%.

---

## 🏗️ Arquitectura

```
app/
├── domain/          # Entidades y objetos de valor (núcleo, sin dependencias)
├── interfaces/      # Puertos: contratos abstractos (LLM, fuentes, repos, publisher, agente, editorial)
├── application/     # Casos de uso (orquestación de alto nivel)
├── agents/          # Los 6 agentes + cerebro editorial clásico (dependen solo de puertos)
├── workflows/       # Orquestación: pipeline secuencial + motor deepagents + helpers editoriales
├── infrastructure/  # Adapters concretos: llm/, embeddings/, sources/, discord/, scheduler/, persistence/, editorial/, hosting/, newsletter/
├── database/        # SQLAlchemy 2.x + repositorio PostgreSQL/pgvector
├── api/             # FastAPI: rutas + esquemas + dependencias
└── core/            # Config, logging, métricas, contenedor de DI
```

### Flujo del workflow

```
Collect News → Classify → Remove Duplicates → Rank
   → Generate Article → Generate Discussion → Publish to Discord → Save History
```

### Por qué hexagonal

- El **dominio** (`domain/`) no conoce FastAPI, SQLAlchemy ni ningún SDK.
- Los **agentes** dependen de **puertos** (`interfaces/`), no de implementaciones.
- La **infraestructura** implementa esos puertos; cambiar de proveedor LLM, de
  base vectorial o de canal de publicación no toca la lógica de negocio.
- El **contenedor** (`core/container.py`) es el único *composition root* que
  ensambla todo a partir de la configuración.

---

## 🚀 Puesta en marcha con Docker (recomendado)

Requisitos: Docker y Docker Compose.

```bash
# 1. Configura el entorno
cp .env.example .env
# Edita .env y rellena al menos:
#   - OPENAI_API_KEY (o ANTHROPIC_API_KEY / OPENROUTER_API_KEY + LLM_PROVIDER)
#   - DISCORD_TOKEN y DISCORD_CHANNEL_ID

# 2. Levanta app + PostgreSQL (con pgvector)
docker compose up --build
```

El contenedor espera a PostgreSQL, aplica las migraciones Alembic y arranca la
API en `http://localhost:8000`. Documentación interactiva en
`http://localhost:8000/docs`.

> La imagen Docker instala por defecto el extra `deepagents`, así que puedes
> activar el motor deliberativo poniendo `WORKFLOW_ENGINE=deepagents` en `.env`
> (véase «Motor deepagents»). Para una imagen mínima sin esos paquetes,
> construye con `INSTALL_EXTRAS="" docker compose build`.

---

## 🧑‍💻 Desarrollo local (sin Docker)

Requisitos: Python 3.12 y un PostgreSQL con la extensión `pgvector`
(`CREATE EXTENSION vector;`).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env   # ajusta DATABASE_URL a tu PostgreSQL local (host localhost)

# Aplica migraciones
alembic upgrade head

# Arranca la API
uvicorn app.main:app --reload
```

> Necesitas una API key válida para el proveedor LLM activo (`LLM_PROVIDER`): la
> app no arranca sin ella. En cambio, los **embeddings** sí caen automáticamente
> al proveedor *hash* determinista (offline) si falta `OPENAI_API_KEY`. Y en
> tiempo de ejecución, si una **llamada** al LLM falla, los agentes degradan a
> heurísticas/fallbacks para no bloquear la publicación.

---

## 🔌 API REST

| Método | Ruta              | Descripción                                            |
|--------|-------------------|--------------------------------------------------------|
| GET    | `/health`         | Estado del servicio.                                   |
| GET    | `/news`           | Lista el histórico (filtros `limit`, `offset`, `category`). |
| GET    | `/news/{id}`      | Detalle de una noticia.                                |
| POST   | `/workflow/run`   | Ejecuta el pipeline diario completo bajo demanda.      |
| POST   | `/newsletter/run` | Genera y publica el boletín semanal bajo demanda.      |
| POST   | `/discord/test`   | Publica un mensaje de prueba en Discord.               |
| GET    | `/stats`          | Métricas: analizadas, publicadas, descartadas, por categoría, última ejecución. |

Ejemplos:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/workflow/run
curl -X POST http://localhost:8000/newsletter/run
curl -X POST http://localhost:8000/discord/test -H 'Content-Type: application/json' -d '{"message":"Hola comunidad"}'
curl http://localhost:8000/stats
```

---

## ⚙️ Configuración (`.env`)

| Variable | Descripción | Por defecto |
|----------|-------------|-------------|
| `LLM_PROVIDER` | `openai` \| `anthropic` \| `openrouter` | `openai` |
| `LLM_MODEL` | Modelo del proveedor activo | `gpt-4o-mini` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` | Claves de API | — |
| `EMBEDDING_PROVIDER` | `openai` \| `hash` | `openai` |
| `EMBEDDING_DIM` | Dimensión del vector | `1536` |
| `DUPLICATE_SIMILARITY_THRESHOLD` | Umbral coseno de duplicado | `0.86` |
| `DISCORD_TOKEN` / `DISCORD_CHANNEL_ID` | Credenciales de Discord (noticia diaria) | — |
| `NEWSLETTER_DISCORD_CHANNEL_ID` | Canal aparte para el boletín (si vacío, usa `DISCORD_CHANNEL_ID`) | — |
| `DATABASE_URL` | DSN async de PostgreSQL | `postgresql+asyncpg://anfaia:anfaia@postgres:5432/anfaia` |
| `POST_TIME` | Hora de publicación diaria (HH:MM) | `09:00` |
| `TIMEZONE` | Zona horaria | `Europe/Madrid` |
| `MIN_RELEVANCE_SCORE` | Score mínimo para publicar | `55` |
| `MAX_ITEMS_PER_SOURCE` | Items recogidos por fuente | `15` |
| `WORKFLOW_ENGINE` | Motor de orquestación: `sequential` \| `deepagents` | `sequential` |
| `EDITORIAL_SHORTLIST_SIZE` | Candidatas únicas entre las que elige el cerebro editorial | `5` |
| `DEEPAGENTS_RECURSION_LIMIT` | Tope de iteraciones del deep agent | `50` |
| `NEWSLETTER_ENABLED` | Activa el scheduler semanal del boletín | `false` |
| `NEWSLETTER_DAY_OF_WEEK` / `NEWSLETTER_POST_TIME` | Día (cron) y hora del boletín | `mon` / `09:00` |
| `NEWSLETTER_TOP_N` | Tope de noticias (crece para cubrir 1 por categoría) | `6` |
| `NEWSLETTER_MIN_RELEVANCE` | Score mínimo para entrar en el boletín | `50` |
| `NEWSLETTER_EXTRA_RELEVANCE` | Score mínimo de las noticias extra (más allá del suelo por categoría) | `80` |
| `NEWSLETTER_DEDUP_THRESHOLD` | Umbral coseno de duplicado dentro del boletín | `0.86` |
| `NEWSLETTER_LOGO_URL` | Logo mostrado en la cabecera del boletín | `https://anfaia.org/ANFAIA_logo_web.png` |
| `NEWSLETTER_BASE_URL` | URL pública base de GitHub Pages (obligatoria para publicar) | — |
| `NEWSLETTER_PATH_PREFIX` | Carpeta de los permalinks dentro del repo de Pages | `newsletters` |
| `GITHUB_TOKEN` | PAT con permiso *Contents: Read and write* sobre el repo de Pages | — |
| `GITHUB_OWNER` / `GITHUB_REPO` | Propietario y repo de GitHub Pages | — |
| `GITHUB_BRANCH` | Rama servida por Pages | `gh-pages` |

> ⚠️ Si cambias `EMBEDDING_DIM`, regenera/migra la columna vectorial: la
> dimensión del vector en PostgreSQL es fija por migración.

---

## 🤖 Configurar el bot de Discord

1. Crea una aplicación y un bot en el [Discord Developer Portal](https://discord.com/developers/applications).
2. Copia el **token** del bot → `DISCORD_TOKEN`.
3. Invita el bot a tu servidor con permiso de **enviar mensajes** en el canal.
4. Activa el *Developer Mode* en Discord, clic derecho sobre el canal → *Copiar ID* → `DISCORD_CHANNEL_ID`.
5. (Opcional) Para publicar el boletín en otro canal, copia su ID en
   `NEWSLETTER_DISCORD_CHANNEL_ID`; el bot debe tener permiso de enviar mensajes en **ambos** canales.

---

## 🧪 Tests y calidad

```bash
pip install -e ".[dev]"

ruff check .          # linting
pytest                # tests + cobertura (falla si < 80%)
```

> Los tests de integración del adaptador deepagents se **saltan** si el extra no
> está instalado. Para ejercitarlos (sin red ni LLM real), instala también el
> extra: `pip install -e ".[dev,deepagents]"`. Es justo lo que hace el job
> `test-deepagents` del CI.

---

## 🧠 Motor deepagents (decisión editorial deliberativa)

El motor `deepagents` mantiene en código las fases **mecánicas y deterministas**
(recolectar, clasificar, deduplicar contra el histórico, publicar y persistir) y
delega únicamente la fase de **juicio editorial** en un agente deliberativo:

```
Collect → Classify → Rank → De-duplicate   (código determinista, testeable)
    → Deliberación editorial                (puerto EditorialBrain)
    → Publish → Save History                (código determinista, testeable)
```

El `EditorialBrain` (`app/interfaces/editorial.py`) recibe una *shortlist* de
candidatas únicas y decide cuál publicar. La implementación deepagents
(`app/infrastructure/editorial/deep_agent_brain.py`):

- **planifica** sus pasos (herramienta de tareas),
- delega en un subagente **editor-investigador** que lee la **fuente original**
  con la herramienta `fetch_url` antes de redactar (reduce alucinaciones),
- pasa el borrador por un subagente **verificador de hechos** adversarial,
- delega la pregunta de debate en un subagente **dinamizador**,
- elige con criterio de **diversidad** frente a los titulares ya publicados.

Ante cualquier error (límite de recursión, fallo de red, JSON inválido) **degrada
automáticamente** al `ClassicEditorialBrain` (los agentes de un solo disparo), de
modo que la publicación diaria nunca se bloquea.

### Activarlo

Con Docker el extra ya viene instalado: basta con poner `WORKFLOW_ENGINE=deepagents`
en `.env`. En **desarrollo local** instala además los paquetes opcionales:

```bash
pip install -e ".[deepagents]"   # extras: deepagents + langchain providers
# en .env:
WORKFLOW_ENGINE=deepagents
```

El cambio se selecciona en el único *composition root* (`app/core/container.py`):
no toca dominio, persistencia, API ni el resto de agentes y adapters. La elección
del motor está gobernada por `WORKFLOW_ENGINE` y la deliberación es totalmente
testeable inyectando un `EditorialBrain` falso.

---

## 🗞️ Boletín semanal

Además de la noticia diaria, el sistema genera un **boletín semanal en HTML**,
lo publica en **GitHub Pages** y lo anuncia en **Discord**, con el mismo estilo
editorial que la noticia diaria.

### Flujo

```
Collect → Classify → Rank → De-duplicate (semántico) → Selección por categoría
   → Editar cada noticia → Reflexión del conjunto → Render HTML
   → Publicar permalink (GitHub Pages) → Anunciar en Discord → Registrar → Índice
```

- **Selección**: elige **al menos una noticia de cada categoría** disponible y
  añade las extra **muy relevantes** (`NEWSLETTER_EXTRA_RELEVANCE`), deduplicando
  semánticamente dentro de la propia edición.
- **Reflexión de conjunto**: un agente redacta una breve síntesis de la semana
  (hilos comunes y tendencias) que encabeza el boletín y la descripción del
  anuncio de Discord.
- **Páginas**: una página por semana (`<base>/newsletters/AAAA-Wnn.html`) con
  botón «← Índice», y un `index.html` que **lista todas las ediciones**.
- **Idempotencia y robustez**: registro por semana ISO en PostgreSQL; un fallo de
  base de datos o de Discord **no impide** que el HTML quede publicado (se degrada
  y se anota en el reporte). Si faltan credenciales de GitHub, usa un publicador
  nulo y no bloquea el arranque.

### Configurar GitHub Pages

1. Crea (recomendado) un **repo público dedicado**, p. ej. `anfaia/newsletter`, y
   activa **GitHub Pages** sobre la rama elegida (*Settings → Pages*).
2. Genera un **PAT fine-grained** limitado a ese repo con permiso
   **Contents: Read and write** → `GITHUB_TOKEN`.
3. Rellena en `.env`:

```bash
NEWSLETTER_ENABLED=true
GITHUB_OWNER=anfaia
GITHUB_REPO=newsletter
GITHUB_BRANCH=gh-pages        # o main, según cómo configures Pages
NEWSLETTER_BASE_URL=https://anfaia.github.io/newsletter
# Opcional: canal de Discord propio para el boletín
NEWSLETTER_DISCORD_CHANNEL_ID=
```

> Un repo **aparte y público** evita exponer el código (Pages gratis requiere
> repo público), mantiene el historial limpio (un commit por semana) y permite un
> token de mínimo privilegio.

### Ejecutarlo a demanda

```bash
# Vía API (la app debe estar corriendo)
curl -X POST http://localhost:8000/newsletter/run

# Standalone (sin levantar la API), p. ej. en cron o contenedor
python scripts/run_newsletter.py
make newsletter                      # equivalente con make (local)

# Con Docker Compose
docker compose exec app python scripts/run_newsletter.py     # stack ya levantado
docker compose run --rm app python scripts/run_newsletter.py # ejecución puntual
```

Con `NEWSLETTER_ENABLED=true`, además se publica **solo el día configurado**
(`NEWSLETTER_DAY_OF_WEEK`, por defecto los lunes) vía el scheduler.

---

## 🛣️ Evolución futura

El mismo contrato `NewsWorkflow` (`app/workflows/base.py`) y el puerto `Agent`
(`app/interfaces/agent.py`) permiten añadir más motores (**LangGraph**, **CrewAI**,
**AutoGen**) reutilizando los mismos agentes y adapters, sin tocar dominio,
persistencia ni API:

1. Crear `app/workflows/<framework>_news_workflow.py` que implemente `NewsWorkflow`.
2. Envolver cada `Agent`/`EditorialBrain` existente como nodo/tarea del framework.
3. Añadir el valor al enum `WorkflowEngine` y la rama en el contenedor de DI.

---

## 📄 Licencia

MIT.
