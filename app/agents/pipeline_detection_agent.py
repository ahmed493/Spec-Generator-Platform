"""
PipelineDetectionAgent
Analyses merged repository metadata (code, SQL, YAML, notebooks, schemas)
and connected data-source schemas to detect the distinct data pipelines /
flux / modules present in the project.

Each detected pipeline carries a full architecture breakdown:
  - jobs:         individual processing units (DAG tasks, Spark jobs, functions, scripts)
  - triggers:     how the pipeline starts (cron, event, API call, sensor, manual, queue message)
  - listen_mode:  passive listening mechanisms (Kafka consumer, SQS listener, webhook, socket)
  - queues:       queues / topics / streams involved (Kafka, RabbitMQ, SQS, Pub/Sub, Azure SB)
  - sub_pipelines: child pipelines this pipeline launches or delegates work to
  - launcher:     the orchestrator or parent that fires this pipeline
  - execution_mode: batch | streaming | event_driven | trigger_based | scheduled | on_demand
  - data_flow:    {input: ..., transformations: [...], output: ...}
"""
import json
import logging
import re
from typing import Optional
from app.agents.llm_client import get_llm_client, BaseLLMClient

logger = logging.getLogger(__name__)

# Semantic queries used to retrieve pipeline-relevant code chunks from ChromaDB.
# Each query targets a different pipeline pattern so the retrieval covers the full
# spectrum (batch jobs, event consumers, schedulers, ETL flows, etc.).
PIPELINE_SEMANTIC_QUERIES = [
    "console command batch job data pipeline ETL processor",
    "message consumer handler queue listener subscriber",
    "scheduler cron job periodic task scheduled",
    "data flow extract transform load pipeline processor writer",
    "event listener webhook handler dispatcher",
    "kafka rabbitmq sqs pubsub redis stream consumer producer",
    "airflow prefect celery luigi dag task worker",
    "symfony messenger command consumer producer handler",
    "spring batch job step reader writer listener scheduled",
]

# Threshold above which detect() switches to multi-pass batched mode
BATCH_DETECTION_FILE_THRESHOLD = 40
# Number of code files fed to each individual LLM call in batched mode
# Keep small: each LLM call ~40-50s, and total timeout is 600s
BATCH_DETECTION_BATCH_SIZE = 20

# ---------------------------------------------------------------------------
# Path-pattern heuristics — detect pipelines from file names alone (no content)
# Each tuple: (compiled_regex, execution_mode, pipeline_type)
# Order matters: more specific patterns first.
# ---------------------------------------------------------------------------
_PATH_PIPELINE_PATTERNS: list[tuple] = [
    # PHP / Symfony — scheduled commands first (contain "Schedule")
    (re.compile(r"(?i).*/?(?:schedule[^/]*|[^/]*schedule)[^/]*command\.php$"), "scheduled", "command"),
    (re.compile(r"(?i).*command\.php$"), "on_demand", "command"),
    (re.compile(r"(?i).*consumer\.php$"), "event_driven", "consumer"),
    (re.compile(r"(?i).*producer\.php$"), "event_driven", "producer"),
    (re.compile(r"(?i).*listener\.php$"), "event_driven", "listener"),
    (re.compile(r"(?i).*subscriber\.php$"), "event_driven", "subscriber"),
    (re.compile(r"(?i).*handler\.php$"), "event_driven", "handler"),
    # Python / Airflow
    (re.compile(r"(?i).*/dag(?:s)?/[^/]+\.py$"), "scheduled", "dag"),
    (re.compile(r"(?i).*/task(?:s)?/[^/]+\.py$"), "on_demand", "task"),
    (re.compile(r"(?i).*/worker(?:s)?/[^/]+\.py$"), "event_driven", "worker"),
    (re.compile(r"(?i).*/job(?:s)?/[^/]+\.py$"), "on_demand", "batch"),
    (re.compile(r"(?i).*/consumer(?:s)?/[^/]+\.py$"), "event_driven", "consumer"),
    (re.compile(r"(?i).*_(?:task|worker|dag|consumer|producer|handler)\.py$"), "event_driven", "job"),
    # Java / Spring
    (re.compile(r"(?i).*listener\.java$"), "event_driven", "listener"),
    (re.compile(r"(?i).*consumer\.java$"), "event_driven", "consumer"),
    (re.compile(r"(?i).*producer\.java$"), "event_driven", "producer"),
    (re.compile(r"(?i).*scheduler\.java$"), "scheduled", "scheduler"),
    (re.compile(r"(?i).*processor\.java$"), "batch", "processor"),
    (re.compile(r"(?i).*handler\.java$"), "event_driven", "handler"),
    (re.compile(r"(?i).*batch[^/]*\.java$"), "batch", "batch"),
    # Node / TypeScript
    (re.compile(r"(?i).*worker\.(ts|js)$"), "event_driven", "worker"),
    (re.compile(r"(?i).*consumer\.(ts|js)$"), "event_driven", "consumer"),
    (re.compile(r"(?i).*producer\.(ts|js)$"), "event_driven", "producer"),
    (re.compile(r"(?i).*/job(?:s)?/[^/]+\.(ts|js)$"), "on_demand", "job"),
    # SQL / Shell
    (re.compile(r"(?i).*/etl/[^/]+\.sql$"), "batch", "etl"),
    (re.compile(r"(?i).*_etl\.sql$"), "batch", "etl"),
    (re.compile(r"(?i).*/script(?:s)?/[^/]+\.sh$"), "on_demand", "script"),
]

_PATH_CATEGORY_PATTERNS: list[tuple] = [
    (re.compile(r"(?i)accounting|invoice|billing|payment|sage|salvia|pis|sdtc|dunning|refund|irrecoverable"), "accounting"),
    (re.compile(r"(?i)crm|contract|subscription|customer|client|contrat"), "crm"),
    (re.compile(r"(?i)report|export|csv|stat|scoring|churn|partner"), "reporting"),
    (re.compile(r"(?i)grd|enedis|grdf|grid|pdl|load.shedding|linky"), "grd"),
    (re.compile(r"(?i)\blp2\b|site.?sync|attestation"), "lp2"),
    (re.compile(r"(?i)haulo|haulogy"), "haulogy"),
    (re.compile(r"(?i)sponsor|aklamio"), "sponsorship"),
    (re.compile(r"(?i)delco|mandate|gestpay"), "delco"),
    (re.compile(r"(?i)energy|energycomm|pce|plm"), "energy"),
    (re.compile(r"(?i)\bsync\b|integration|import|export"), "sync"),
    (re.compile(r"(?i)auth|security|token|oauth|sso"), "auth"),
    (re.compile(r"(?i)notif|email|sms|mail|push|alert"), "notification"),
    (re.compile(r"(?i)\bml\b|model|train|predict|inference"), "ml"),
    (re.compile(r"(?i)monitor|health|metric|log"), "monitoring"),
]


DETECTION_SYSTEM_PROMPT = """You are a senior data engineering architect and reverse-engineering expert.
You perform EXHAUSTIVE codebase analysis — you DO NOT stop at a summary; you enumerate EVERY
data pipeline, flux, job, handler, consumer, producer, scheduler, ETL script, and processing
unit found in the repository code and connected data sources.

Critical rules:
- NEVER merge separate pipelines/jobs/commands into one entry. Each file, class, method, or command
  that independently reads data → processes → writes/sends is its own pipeline entry.
- If a project has 40 PHP console commands, return 40 entries. If there are 15 Kafka consumers,
  return 15 entries. There is NO upper limit on the number of pipelines you can return.
- Detect pipelines in EVERY language and framework: PHP/Symfony, Python, Java/Spring, Node/TS,
  Go, .NET, Ruby, Rust, Shell, SQL stored procedures, Makefile ETL targets — ALL of them.
- Group each pipeline under a business domain `category` (e.g. accounting, crm, reporting,
  grd, lp2, haulogy, sponsorship, delco, energy, sync, auth, notification, other).
  Infer the category from folder names, class names, config keys, and table names.
- execution_mode MUST be inferred correctly:
    * Anything with a queue/topic consumer or event listener → "event_driven"
    * Anything with a cron/schedule → "scheduled"
    * Anything triggered by an API call or webhook → "trigger_based"
    * Anything run once on demand / CLI → "on_demand"
    * Continuous streaming pipeline → "streaming"
    * Default only to "batch" when NO other signal is present.
- Always respond with VALID JSON ONLY, no extra text, no markdown fences."""


DETECTION_PROMPT = """Analyse the following project metadata extracted from one or more repositories and connected data sources.

## Project metadata:
{metadata_summary}

## YOUR TASK — EXHAUSTIVE PIPELINE INVENTORY
Produce a COMPLETE inventory of EVERY pipeline, job, flux, handler, consumer, and processing
unit found in this project. Do NOT summarise, do NOT merge, do NOT stop early.
A "pipeline" is ANY process that: reads data from somewhere → does something → writes/sends it somewhere.

  MANDATORY RULES:
1. **One entry per executable unit** — each file, class, method, console command, queue consumer,
   scheduled task, event handler, or ETL script that independently processes data gets its OWN entry.
2. **No upper limit** — if the project has 50 commands and 20 consumers, return 70 entries.
3. **No CI/CD entries** — skip build/test/lint/deploy stages unless they perform real data processing
   (ETL export, DB migration with data load, report generation, data sync).
4. **Category is mandatory** — classify every pipeline under a business domain using folder names,
   class names, config keys, and table names as evidence.
5. **execution_mode is inferred, never defaulted**:
   - queue/topic consumer or event listener → "event_driven"
   - cron / @Scheduled / schedule_interval → "scheduled"
   - triggered by API call / webhook → "trigger_based"
   - CLI on-demand / manual run → "on_demand"
   - continuous stream processing → "streaming"
   - **only use "batch" when a pipeline explicitly processes data in bulk with no other signal**

## WHAT TO DETECT IN EVERY STACK
### Jobs & Processing units
- Python: Airflow DAG tasks, Prefect flows, Celery tasks, Luigi tasks, standalone scripts
- PHP/Symfony: ALL classes extending `Command` or `ContainerAwareCommand`, ALL Messenger handlers,
  ALL EventSubscriberInterface implementations, ALL services called by cron
- Java/Spring: ALL @Scheduled methods (one per method), ALL Spring Batch Job beans, ALL @JmsListener
  / @RabbitListener / @KafkaListener / @EventListener methods
- Node/TS: ALL Bull/BullMQ workers, ALL Agenda.define() jobs, ALL @Cron decorated methods
- SQL: stored procedures, views performing aggregation/transformation, migration scripts loading data
- Shell: bash/sh files loading, transforming, or exporting data, Makefile ETL targets

### Triggers
cron schedules, @Scheduled, Airflow schedule_interval, event triggers, API calls, file arrival,
queue messages, sensors, manual CLI, CI/CD hooks

### Listen mode (async consumers)
Symfony Messenger consumers, Kafka consumers, SQS pollers, RabbitMQ consumers,
Spring @JmsListener / @RabbitListener, webhook receivers, CDC (Debezium), socket listeners

### Queues / Streams / Topics
Kafka, RabbitMQ, SQS/SNS, Pub/Sub, Redis Streams, Celery queues,
Symfony Messenger transports (AMQP, Doctrine, Redis)

### Data flow
source (DB table / API / file / queue / FTP) → transformations → destination

## BUSINESS CATEGORY CLASSIFICATION
Assign each pipeline to one of these categories based on code evidence:
accounting, crm, reporting, grd, lp2, haulogy, sponsorship, delco, energy,
sync, auth, notification, ml, api, etl, monitoring, other

Respond ONLY with this exact JSON (no markdown fences, no narrative):
{{
  "pipelines": [
    {{
      "id": "snake_case_unique_id",
      "name": "Human-readable name",
      "description": "2-4 sentences referencing actual class names, file paths, table names found.",
      "type": "batch|streaming|api|ml|reporting|etl|event_driven|cdc|other",
      "execution_mode": "scheduled|streaming|event_driven|trigger_based|on_demand|batch",
      "category": "accounting|crm|reporting|grd|lp2|haulogy|sponsorship|delco|energy|sync|auth|notification|ml|api|etl|monitoring|other",
      "confidence": 0.0,
      "launcher": "Airflow|Prefect|cron|API|GitHub Actions|manual|parent_pipeline_id|unknown",
      "triggers": [
        {{"type": "cron|event|api_call|sensor|queue_message|file_arrival|manual|webhook", "detail": "exact cron expression or event name"}}
      ],
      "listen_mode": [
        {{"type": "kafka_consumer|sqs_listener|pubsub_subscription|rabbitmq_consumer|webhook|cdc|none", "detail": "queue/topic name and routing key"}}
      ],
      "queues": [
        {{"name": "exact_queue_or_topic_name", "technology": "Kafka|SQS|RabbitMQ|PubSub|Redis|Azure SB|other", "role": "input|output|both"}}
      ],
      "jobs": [
        {{"id": "job_id", "name": "Job name", "file": "path/to/file", "description": "what this job does", "order": 1}}
      ],
      "sub_pipelines": [],
      "parent_pipeline": null,
      "explainability": {{
        "keywords": ["class or method name"],
        "orchestration_clues": ["evidence of how it is triggered"],
        "evidence_files": ["exact/file/path.php"],
        "evidence_tables": ["schema.table_name"]
      }},
      "source_files": ["exact/file/path"],
      "source_tables": ["schema.table"],
      "technologies": ["PHP", "RabbitMQ", "MySQL"]
    }}
  ],
  "count": 0,
  "summary": "One paragraph describing the overall data architecture and number of pipelines/consumers/commands found."
}}
"""


SYMFONY_FLUX_SYSTEM_PROMPT = """You are a codebase analysis agent specialized in EXHAUSTIVE detection
of all data flows, integration pipelines, and processing flux in a Symfony PHP project.

Your task is to produce a COMPLETE structured inventory of EVERY flux/pipeline — no omissions.
A flux is any mechanism that moves, transforms, triggers, or reacts to data, sync or async.

Critical requirements:
- Return ONE entry per Console Command class, per consumer, per producer, per event listener.
  If a project has 45 Command classes, return 45 entries. There is NO upper limit.
- execution_mode MUST reflect actual behavior:
    * RabbitMQ / Messenger consumer → "event_driven"
    * @Scheduled / cron command → "scheduled"
    * API/webhook handler → "trigger_based"
    * CLI command run on demand → "on_demand"
    * NEVER default to "batch" unless the pipeline genuinely bulk-processes records.
- Assign a business `category` to every entry using folder paths, class names, config keys.
- Start from configuration files (config_rabbitmq.yml, services.yml, routing.yml) as source of truth.
- Do not skip any bundle, sub-config import, or annotated class.
- Always respond with VALID JSON ONLY, no markdown fences, no commentary.
"""


SYMFONY_FLUX_DETECTION_PROMPT = """Pipeline & Flux Detection Agent Prompt:
You are a codebase analysis agent specialized in detecting all data flows, integration pipelines,
and processing flux in a Symfony PHP project.

Your task is to scan the entire codebase and produce a structured inventory of every flux/pipeline found.
A "flux" is any mechanism that moves, transforms, triggers, or reacts to data, synchronously or asynchronously.

## Project metadata:
{metadata_summary}

## WHAT TO DETECT

### 1. Console Commands (Batch / CLI triggers)
- Scan all classes extending `Command` or `ContainerAwareCommand`
- Detect commands that import, export, sync, report, process files, send emails/SMS, or call external APIs
- Group by functional domain (e.g., Accounting, Reporting, GRD, LP2, Dunning, PIS/SDTC)
- Note: commands prefixed with `Schedule` are time-triggered pipelines

### 2. RabbitMQ Consumers (Listen mode / async triggers)
- Find all classes implementing `ConsumerInterface` or the `execute()` pattern used by OldSoundRabbitMqBundle
- Find all RabbitMQ consumer declarations in `config_rabbitmq.yml` (keys: `old_sound_rabbit_mq.consumers`)
- For each consumer: extract queue name, exchange, routing key, and callback class
- These represent inbound async flux (data arriving into this system)

### 3. RabbitMQ Producers (Outbound async triggers)
- Find all producer declarations in `config_rabbitmq.yml` (keys: `old_sound_rabbit_mq.producers`)
- Find all classes injecting a producer service and calling `->publish()`
- For each producer: extract exchange, routing key, and what triggers it
- These represent outbound async flux (data sent from this system)

### 4. Event Listeners & Subscribers (Reactive flux)
- Find all classes implementing `EventSubscriberInterface`
- Find all `kernel.event_listener` and `kernel.event_subscriber` tags in `services.yml` and sub-config files
- Find all Doctrine lifecycle listeners (`doctrine.event_listener` tag, `@ORM.HasLifecycleCallbacks`)
- For each: identify the listened event and the action triggered

### 5. Symfony Workflow / State Machine (State-driven flux)
- Find workflow definitions in config YAML (key: `framework.workflows`)
- Extract: entity, states, transitions, and which listeners hook into it
- This represents a state machine flux (data progressing through lifecycle stages)

### 6. REST Clients (Outbound synchronous flux)
- Find all classes in `Service/RestClient/` or `Client/` directories
- Find Guzzle or cURL-based HTTP callers
- For each: identify target system, endpoint pattern, and what data flows

### 7. File-based Integrations (FTP/SFTP/file flux)
- Find commands or services that read/write files from FTP/SFTP
- Look for `ftp_`, `sftp_`, `FileImport`, `FileExport`, `FileStream`, `FileTreatment` patterns
- For each: identify the source/destination system and file type

### 8. Scheduled / Cron Flux
- Identify commands with `Schedule` in their name
- Look for any cron annotations or `.sh` scripts
- Note any `JobQueue` or scheduler service usage

### 9. API Endpoints (Inbound synchronous flux)
- Scan `routing.yml` files for all imported route resources
- Find all controllers annotated with `@Route`
- Identify webhook/callback endpoints (look for `/callback`, `/webhook`, `/notify`, `/state`)

## KNOWN DOMAINS IN THIS PROJECT
Use these to fill the category field when evidence matches:
- accounting: Sage/Salvia invoices, payments, dunning, PIS/SDTC refunds, irrecoverable debts
- crm: Contratpdl subscription lifecycle, workflow state machine, B2B/B2C contracts
- grd: Enedis/GRDF grid operator file imports, load shedding, PDL management
- lp2: LP2 CRM site/invoice sync, attestation letters, mail campaigns
- reporting: CSV/file exports for partners, dunning reports, scoring, churn, subscriptions
- haulogy: Haulogy REST API (events, contracts, customers, EcoJoko PDL counters)
- sponsorship: Aklamio sponsorship validation
- delco: Core mandate management, Gestpay payments, status events, JWT auth
- energy: EnergyComm PDL/PCE/PLM searches
- frontend: Web UI, job queue rescheduling

## KNOWN INTEGRATION PATTERNS TO DETECT
- RabbitMQ consumers: LP2 site/invoice sync, Gestpay mandate/payment state, Salvia accounting
- RabbitMQ producers: Accounting payments, Gestpay mandate creation, StatusEvent fanout
- File imports via FTP: Enedis file streams, GRDF file streams, Enedis load shedding, dunning payment files
- REST outbound calls: SalviaClient, Haulogy APIs, LP2Client, AklamioClient, EnergyCommClient
- State machine: contratpdl workflow with multiple states and transitions
- Scheduled commands: DunningPayment, SubscriptionForPartner, Contratpdl extracts, StopRelance, weekly exports
- Event listeners: WorkflowSubscriber, ParcoursSouscriptionsStatusListener, ContractStatusListener

## SCANNING RULES
- Start with `config_rabbitmq.yml` when present; it is the source of truth for async flux
- Scan all `*Command.php`, `*Consumer.php`, `*Producer.php`, `*Listener.php`, `*Subscriber.php` files
- Scan `services.yml` for tagged services
- Scan `routing.yml` and imported routing files
- Scan `Service/RestClient/` and `Client/` directories
- Check shell scripts that call `php bin/console`
- Do NOT invent flux; only report what is verifiable in the code or config

## OUTPUT FORMAT
Return a JSON object with a `pipelines` array. One entry per flux unit — no merging.

Each entry MUST use this exact structure:
{{
    "id": "unique-slug-derived-from-class-or-file-name",
    "name": "Human-readable name (include class name or command name)",
    "category": "accounting|crm|grd|lp2|reporting|haulogy|sponsorship|delco|energy|sync|auth|notification|etl|other",
    "type": "command|consumer|producer|listener|workflow|rest-client|file-import|file-export|api-endpoint|cron|batch|other",
    "execution_mode": "scheduled|streaming|event_driven|trigger_based|on_demand|batch",
    "trigger": "cli|rabbitmq|http|cron|event|ftp|doctrine|manual",
    "direction": "inbound|outbound|internal",
    "source": "originating system or service name",
    "destination": "target system or service name",
    "class": "Fully\\Qualified\\ClassName",
    "config_key": "rabbitmq config key or route name (exact string from config file)",
    "queue_or_route": "exact queue name, exchange, routing key, or URL path",
    "description": "One sentence: what data moves, from where (exact source) to where (exact destination)",
    "confidence": 0.85,
    "dependencies": ["OtherClass", "ExternalSystem"],
    "jobs": [],
    "listen_mode": [],
    "queues": [],
    "triggers": [],
    "source_files": ["src/path/to/File.php"],
    "source_tables": [],
    "technologies": ["PHP", "Symfony", "RabbitMQ"]
}}

⚠️  Return ALL entries. If 60 flux units are found, return 60 entries.
"""


class PipelineDetectionAgent:
    """Detects distinct data pipelines / flux / modules from repo + source metadata."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm = llm_client or get_llm_client()

    def detect(self, repo_metadata: dict) -> dict:
        """
        Analyse merged repo metadata and return detected pipelines.
        repo_metadata: the same merged dict used by ExtractionAgent
                       (readme, sql_files, python_files, datasource_context, …)
        Returns:
          { pipelines: [...], count: int, summary: str }
        """
        all_code = self._iter_code_entries(repo_metadata)
        if len(all_code) > BATCH_DETECTION_FILE_THRESHOLD:
            logger.info(
                "PipelineDetectionAgent: large repo (%d code files) — switching to "
                "multi-pass batched detection (batch_size=%d)",
                len(all_code), BATCH_DETECTION_BATCH_SIZE,
            )
            return self._detect_batched(repo_metadata, all_code)

        summary = self._build_summary(repo_metadata)
        logger.info(
            "PipelineDetectionAgent — summary built: %d chars, "
            "py:%d sql:%d yaml:%d code:%d",
            len(summary),
            len(repo_metadata.get("python_files") or []),
            len(repo_metadata.get("sql_files") or []),
            len(repo_metadata.get("yaml_files") or []),
            len(repo_metadata.get("code_files") or []),
        )
        use_symfony_prompt = self._should_use_symfony_flux_prompt(repo_metadata)
        prompt_template = SYMFONY_FLUX_DETECTION_PROMPT if use_symfony_prompt else DETECTION_PROMPT
        system_prompt = SYMFONY_FLUX_SYSTEM_PROMPT if use_symfony_prompt else DETECTION_SYSTEM_PROMPT
        prompt = prompt_template.format(metadata_summary=summary)
        logger.info("PipelineDetectionAgent prompt mode: %s", "symfony-flux" if use_symfony_prompt else "generic")
        raw = self.llm.generate(
            prompt,
            system_prompt=system_prompt,
            response_format={"type": "json_object"},
            max_tokens=8192,
        )
        logger.info("LLM raw response (%d chars, first 800): %s", len(raw or ""), (raw or "")[:800])
        parsed = self._parse(raw)

        # Deterministic runtime extraction (jobs/listeners/queues/schedulers)
        # complements LLM output and keeps detection robust across stacks.
        heuristic = self._extract_runtime_pipelines_from_code(repo_metadata)
        if heuristic:
          llm_pipelines = parsed.get("pipelines", [])
          merged = self._merge_heuristic_and_llm(heuristic, llm_pipelines)
          logger.info(
            "Runtime heuristic pipelines:%d, llm pipelines:%d, merged:%d",
            len(heuristic),
            len(llm_pipelines),
            len(merged),
          )
          parsed["pipelines"] = merged
          parsed["count"] = len(merged)

        return parsed

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_summary(self, metadata: dict, batch_mode: bool = False) -> str:
        parts = []
        parts.append(f"Project: {metadata.get('repo_name', 'N/A')}")
        parts.append(f"Description: {metadata.get('description', 'N/A')}")
        parts.append(f"Languages: {metadata.get('languages', 'N/A')}")
        parts.append(f"Topics: {metadata.get('topics', 'N/A')}")

        if metadata.get("readme"):
            parts.append(f"\n## README:\n{metadata['readme'][:4000]}")

        # File tree — very useful for detecting pipeline/module boundaries
        if metadata.get("structure"):
            files = [f["path"] for f in metadata["structure"].get("files", [])]
            if files:
                parts.append(f"\n## File tree ({len(files)} files):\n" + "\n".join(files[:300]))

        # Code files — bucket by extension, include all languages
        _ext_labels = {
            ".sql": ("SQL", "sql"),
            ".py": ("Python", "python"),
            ".php": ("PHP", "php"),
            ".java": ("Java", "java"),
            ".kt": ("Kotlin", "kotlin"),
            ".js": ("JavaScript", "javascript"),
            ".ts": ("TypeScript", "typescript"),
            ".sh": ("Shell", "bash"),
            ".yaml": ("YAML", "yaml"),
            ".yml": ("YAML", "yaml"),
            ".xml": ("XML", "xml"),
            ".toml": ("TOML", "toml"),
            ".tf": ("Terraform", "hcl"),
            ".json": ("JSON", "json"),
        }
        # Collect all code files from *_files keys + generic code_files
        all_code: list[dict] = []
        for key in ("sql_files", "python_files", "yaml_files", "json_files",
                    "notebook_files", "code_files"):
            all_code.extend(metadata.get(key) or [])

        # Group by extension
        by_ext: dict[str, list[dict]] = {}
        for f in all_code:
            path = f.get("path", "")
            ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
            by_ext.setdefault(ext, []).append(f)

        for ext, (label, lang) in _ext_labels.items():
            files_for_ext = by_ext.get(ext, [])
            if not files_for_ext:
                continue
            parts.append(f"\n## {label} files ({len(files_for_ext)}):")
            # In batch mode show every file in the batch; normally cap per extension.
            limit = len(files_for_ext) if batch_mode else (15 if ext not in (".json",) else 5)
            for f in files_for_ext[:limit]:
                content = (f.get("content") or "")  # full content — already capped at 4000 chars when fetched
                parts.append(f"### {f['path']}:\n```{lang}\n{content}\n```")

        # External datasource context (DB tables, queues, etc.)
        if metadata.get("datasource_context"):
            parts.append(f"\n## Connected data sources:\n{metadata['datasource_context']}")

        return "\n".join(parts)

    def _should_use_symfony_flux_prompt(self, metadata: dict) -> bool:
        languages = " ".join(str(x) for x in (metadata.get("languages") or []))
        readme = str(metadata.get("readme") or "")
        files = "\n".join(f.get("path", "") for f in (metadata.get("structure", {}).get("files", []) or []))
        haystack = f"{languages}\n{readme}\n{files}".lower()
        markers = (
            "php", "symfony", "config_rabbitmq", "old_sound_rabbit_mq", "services.yml",
            "routing.yml", "bundles", "src/ve/", "consumer.php", "producer.php",
            "containerawarecommand", "eventsubscriberinterface",
        )
        return any(marker in haystack for marker in markers)

    def _iter_code_entries(self, metadata: dict) -> list[dict]:
        all_code: list[dict] = []
        for key in ("sql_files", "python_files", "yaml_files", "json_files", "notebook_files", "code_files"):
            all_code.extend(metadata.get(key) or [])
        return all_code

    def _detect_batched(self, repo_metadata: dict, all_code: list[dict]) -> dict:
        """
        Multi-pass detection for large repos.
        Splits all code files into batches of BATCH_DETECTION_BATCH_SIZE, runs a
        focused LLM call on each batch (no file-count cap applied), then merges
        all results together with path-only and content-heuristic supplementation.
        """
        use_symfony = self._should_use_symfony_flux_prompt(repo_metadata)

        # For Symfony/PHP repos the LLM responses are truncated mid-JSON due to the
        # volume of PHP namespace strings, causing every batch to return 0 pipelines.
        # The path-only heuristic recovers all pipelines from file names in <5s and
        # is the correct strategy for this stack — skip LLM batching entirely.
        all_paths = [
            f["path"]
            for f in (repo_metadata.get("structure", {}).get("files", []) or [])
        ]
        if use_symfony:
            logger.info(
                "PipelineDetectionAgent._detect_batched: Symfony/PHP repo detected — "
                "skipping LLM batching, using path heuristic + content heuristic only."
            )
            path_pipelines = self._detect_from_paths_only(all_paths)
            heuristic_pipelines = self._extract_runtime_pipelines_from_code(repo_metadata)
            merged = self._merge_batched_results([], heuristic_pipelines, path_pipelines)
            logger.info(
                "PipelineDetectionAgent._detect_batched (symfony fast): path=%d heuristic=%d merged=%d",
                len(path_pipelines), len(heuristic_pipelines), len(merged),
            )
            return {
                "pipelines": merged,
                "count": len(merged),
                "summary": (
                    f"Detected {len(merged)} pipelines via path + content heuristics "
                    f"({len(all_paths)} tree paths analysed)."
                ),
            }

        batches = [
            all_code[i: i + BATCH_DETECTION_BATCH_SIZE]
            for i in range(0, len(all_code), BATCH_DETECTION_BATCH_SIZE)
        ]
        logger.info("PipelineDetectionAgent._detect_batched: %d batches × up to %d files", len(batches), BATCH_DETECTION_BATCH_SIZE)

        prompt_template = DETECTION_PROMPT
        system_prompt = DETECTION_SYSTEM_PROMPT

        all_llm_pipelines: list[dict] = []
        for i, batch_files in enumerate(batches):
            try:
                batch_meta = dict(repo_metadata)
                batch_meta["sql_files"]      = [f for f in batch_files if f["path"].endswith(".sql")]
                batch_meta["python_files"]   = [f for f in batch_files if f["path"].endswith(".py")]
                batch_meta["yaml_files"]     = [f for f in batch_files if f["path"].endswith((".yaml", ".yml", ".toml", ".cfg", ".ini"))]
                batch_meta["code_files"]     = [f for f in batch_files
                                                 if not f["path"].endswith((".sql", ".py", ".yaml", ".yml", ".toml", ".cfg", ".ini"))]
                batch_meta["json_files"]     = []
                batch_meta["notebook_files"] = []

                summary = self._build_summary(batch_meta, batch_mode=True)
                prompt = prompt_template.format(metadata_summary=summary)
                raw = self.llm.generate(
                    prompt,
                    system_prompt=system_prompt,
                    response_format={"type": "json_object"},
                    max_tokens=16384,
                )
                parsed = self._parse(raw)
                batch_pipelines = parsed.get("pipelines") or []
                logger.info("Batch %d/%d → %d pipelines", i + 1, len(batches), len(batch_pipelines))
                all_llm_pipelines.extend(batch_pipelines)
            except Exception as exc:
                logger.warning("PipelineDetectionAgent batch %d/%d failed: %s", i + 1, len(batches), exc)

        path_pipelines = self._detect_from_paths_only(all_paths)
        heuristic_pipelines = self._extract_runtime_pipelines_from_code(repo_metadata)

        merged = self._merge_batched_results(all_llm_pipelines, heuristic_pipelines, path_pipelines)
        logger.info(
            "PipelineDetectionAgent._detect_batched: llm=%d path=%d heuristic=%d merged=%d",
            len(all_llm_pipelines), len(path_pipelines), len(heuristic_pipelines), len(merged),
        )
        return {
            "pipelines": merged,
            "count": len(merged),
            "summary": (
                f"Detected {len(merged)} pipelines across {len(batches)} LLM passes "
                f"({len(all_code)} fetched files + {len(all_paths)} tree paths analysed)."
            ),
        }

    def _detect_from_paths_only(self, file_paths: list[str]) -> list[dict]:
        """
        Fast heuristic: infer pipeline candidates purely from file-path patterns.
        No content fetching required — works on the full git tree output instantly.
        Confidence is lower (0.72) than LLM or content-based detection; these entries
        are used as supplements when the LLM missed a file or detection timed out.
        """
        _lang_map = {
            ".php": "PHP", ".py": "Python", ".java": "Java", ".kt": "Kotlin",
            ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go", ".cs": "C#",
            ".rb": "Ruby", ".rs": "Rust", ".sh": "Shell", ".sql": "SQL",
        }
        pipelines: list[dict] = []
        seen_ids: set[str] = set()

        for path in file_paths:
            for pattern, exec_mode, ptype in _PATH_PIPELINE_PATTERNS:
                if not pattern.match(path):
                    continue

                # Infer business category from path tokens
                category = "other"
                for cat_pat, cat in _PATH_CATEGORY_PATTERNS:
                    if cat_pat.search(path):
                        category = cat
                        break

                stem = re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_")[-80:]
                pid = f"path_{stem}"
                if pid in seen_ids:
                    break
                seen_ids.add(pid)

                filename = path.split("/")[-1]
                raw_name = filename.rsplit(".", 1)[0]
                # CamelCase → spaced
                name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw_name)
                name = name.replace("_", " ").replace("-", " ").strip()

                ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
                lang = _lang_map.get(ext, "Unknown")

                trigger_type = (
                    "cron" if exec_mode == "scheduled"
                    else "queue_message" if exec_mode == "event_driven"
                    else "manual"
                )
                listen_mode: list[dict] = []
                if ptype in ("consumer", "listener", "subscriber"):
                    listen_mode = [{"type": "rabbitmq_consumer", "detail": f"Pattern match: {filename}"}]

                pipelines.append({
                    "id": pid,
                    "name": name,
                    "description": f"{ptype.title()} detected via path pattern in {path}.",
                    "type": ptype,
                    "execution_mode": exec_mode,
                    "category": category,
                    "confidence": 0.72,
                    "launcher": "application_runtime",
                    "triggers": [{"type": trigger_type, "detail": f"Inferred from path: {path}"}],
                    "listen_mode": listen_mode,
                    "queues": [],
                    "jobs": [{
                        "id": f"job_{stem[-30:]}",
                        "name": name,
                        "file": path,
                        "description": f"{ptype.title()} in {filename}",
                        "order": 1,
                    }],
                    "sub_pipelines": [],
                    "parent_pipeline": None,
                    "explainability": {
                        "keywords": [ptype, exec_mode],
                        "orchestration_clues": [f"path_pattern:{ptype}"],
                        "evidence_files": [path],
                        "evidence_tables": [],
                    },
                    "source_files": [path],
                    "source_tables": [],
                    "technologies": [lang],
                })
                break  # one match per file

        return pipelines

    def _merge_batched_results(
        self,
        llm_pipelines: list[dict],
        heuristic_pipelines: list[dict],
        path_pipelines: list[dict],
    ) -> list[dict]:
        """
        Merge results from multi-pass LLM, content heuristic, and path heuristic.
        Priority: LLM > content heuristic > path heuristic.
        A path/heuristic entry is suppressed if any of its source files is already
        covered by an LLM entry.
        """
        seen_paths: set[str] = set()
        merged: list[dict] = []

        for p in llm_pipelines:
            for f in (p.get("source_files") or []):
                seen_paths.add(str(f))
            merged.append(p)

        for p in heuristic_pipelines:
            paths = [str(f) for f in (p.get("source_files") or [])]
            if paths and all(path in seen_paths for path in paths):
                continue
            for path in paths:
                seen_paths.add(path)
            merged.append(p)

        for p in path_pipelines:
            paths = [str(f) for f in (p.get("source_files") or [])]
            if paths and all(path in seen_paths for path in paths):
                continue
            for path in paths:
                seen_paths.add(path)
            merged.append(p)

        return merged

    def _extract_runtime_pipelines_from_code(self, metadata: dict) -> list[dict]:
        runtime_exts = {".py", ".php", ".java", ".kt", ".scala", ".js", ".ts", ".go", ".cs", ".rb", ".rs", ".sh", ".sql"}
        runtime_path_markers = ("/src/", "/app/", "/bin/", "/jobs/", "/workers/", "/commands/", "/handlers/")
        ci_cd_markers = (
            ".gitlab-ci.yml", ".github/workflows/", "jenkinsfile", ".circleci/",
            "bitbucket-pipelines", ".azure-pipelines/", ".drone.yml",
        )
        queue_patterns = {
            "Kafka": r"\bkafka\b|confluent|topic[s]?|consumer group",
            "RabbitMQ": r"\brabbitmq\b|\bamqp\b|@rabbitlistener|queue_bind",
            "SQS": r"\bsqs\b|aws_sqs|receive_message|send_message",
            "PubSub": r"pubsub|subscription|google\.cloud\.pubsub",
            "Redis": r"redis queue|redis\.from_url|bullmq|\bbull\b|sidekiq",
            "Celery": r"\bcelery\b|@shared_task|apply_async|delay\(",
            "Symfony Messenger": r"messenger|messagebusinterface|messagehandlerinterface",
            "JMS": r"@jmslistener|javax\.jms|jakarta\.jms",
        }
        scheduler_re = re.compile(r"@scheduled|schedule_interval|cron\(|crontab|agenda\.define|@cron|hangfire|scheduler", re.I)
        listener_re = re.compile(r"listener|subscriber|consumer|webhook|eventhandler|@eventlistener|@rabbitlistener|@jmslistener", re.I)
        job_re = re.compile(
            r"extends\s+command|class\s+\w+command|class\s+\w+handler|"
            r"@bean\s*\(.*job|commandlinerunner|applicationrunner|"
            r"def\s+run\(|def\s+process\(|function\s+handle\(|function\s+execute\(|"
            r"\bworker\b|\bconsumer\b|\bhandler\b",
            re.I,
        )

        pipelines: list[dict] = []
        seen_ids: set[str] = set()

        for entry in self._iter_code_entries(metadata):
            path = str(entry.get("path", ""))
            if not path:
                continue
            path_lower = path.lower()
            if any(marker in path_lower for marker in ci_cd_markers):
                continue

            filename = path.split("/")[-1]
            ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
            is_runtime_file = ext in runtime_exts or any(marker in path_lower for marker in runtime_path_markers)
            if not is_runtime_file:
                continue

            content = str(entry.get("content", ""))
            if not content:
                continue

            queue_hits = [tech for tech, pat in queue_patterns.items() if re.search(pat, content, re.I)]
            has_schedule = bool(scheduler_re.search(content) or scheduler_re.search(path))
            has_listener = bool(listener_re.search(content) or listener_re.search(path))
            has_job = bool(job_re.search(content) or job_re.search(path))

            # Require at least one executable/runtime signal.
            if not (has_job or has_schedule or has_listener or queue_hits):
                continue

            signal_score = int(has_job) + int(has_schedule) + int(has_listener) + (1 if queue_hits else 0)
            if signal_score < 1:
                continue

            stem = re.sub(r"[^a-z0-9]+", "_", path_lower).strip("_")[-80:] or "pipeline"
            pid = f"code_{stem}"
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            name_hint = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip().title() or "Runtime Pipeline"

            queues = [{"name": tech.lower().replace(" ", "_"), "technology": tech, "role": "input"} for tech in queue_hits]
            listen_mode = []
            if has_listener:
                listen_mode.append({
                    "type": "rabbitmq_consumer" if "RabbitMQ" in queue_hits else "kafka_consumer" if "Kafka" in queue_hits else "webhook",
                    "detail": f"Listener/consumer pattern found in {filename}",
                })

            triggers = []
            if has_schedule:
                triggers.append({"type": "cron", "detail": f"Scheduling pattern found in {filename}"})
            if not triggers and not has_listener:
                triggers.append({"type": "manual", "detail": f"Runnable job/command detected in {filename}"})

            lang_map = {
                ".py": "Python", ".php": "PHP", ".java": "Java", ".kt": "Kotlin", ".js": "JavaScript",
                ".ts": "TypeScript", ".go": "Go", ".cs": "C#", ".rb": "Ruby", ".rs": "Rust", ".sh": "Shell", ".sql": "SQL",
            }
            techs = [lang_map[ext]] if ext in lang_map else []
            for q in queue_hits:
                if q not in techs:
                    techs.append(q)

            execution_mode = "event_driven" if has_listener or queue_hits else "scheduled" if has_schedule else "on_demand"
            ptype = "event_driven" if has_listener or queue_hits else "batch"

            pipelines.append({
                "id": pid,
                "name": name_hint,
                "description": f"Runtime pipeline inferred from source code signals in {path}: jobs/handlers/listeners/scheduling/queues.",
                "type": ptype,
                "execution_mode": execution_mode,
                "confidence": 0.78,
                "launcher": "application_runtime",
                "triggers": triggers,
                "listen_mode": listen_mode,
                "queues": queues,
                "jobs": [{
                    "id": f"job_{stem[-40:]}",
                    "name": f"{name_hint} job",
                    "file": path,
                    "description": f"Detected runtime processing unit in {filename}",
                    "order": 1,
                }],
                "sub_pipelines": [],
                "parent_pipeline": None,
                "explainability": {
                    "keywords": [k for k, v in (("job", has_job), ("scheduled", has_schedule), ("listener", has_listener)) if v],
                    "orchestration_clues": ["queue_processing" if queue_hits else "runtime_code"],
                    "evidence_files": [path],
                    "evidence_tables": [],
                },
                "source_files": [path],
                "source_tables": [],
                "technologies": techs,
            })

        return pipelines

    def _merge_heuristic_and_llm(self, heuristic: list[dict], llm_pipelines: list[dict]) -> list[dict]:
        seen_paths = set()
        merged: list[dict] = []

        for p in heuristic:
            for sp in p.get("source_files", []):
                seen_paths.add(str(sp))
            merged.append(p)

        for p in llm_pipelines:
            llm_paths = [str(sp) for sp in (p.get("source_files") or [])]
            if llm_paths and any(path in seen_paths for path in llm_paths):
                continue
            merged.append(p)

        return merged

    # ── Vectorstore-augmented detection ─────────────────────────────────────

    def detect_with_vectorstore(
        self, repo_metadata: dict, project_id: str, vector_manager
    ) -> dict:
        """
        Like detect() but first chunks & stores all repo files into ChromaDB,
        then uses semantic retrieval to prioritise the most pipeline-relevant
        code before building the LLM prompt.  Falls back to plain detect() if
        the vectorstore is unavailable or empty.
        """
        repo_name = repo_metadata.get("repo_name", "unknown")

        # Flatten all code files from the metadata dict
        all_files: list[dict] = []
        for key in ("sql_files", "python_files", "yaml_files", "json_files",
                    "notebook_files", "code_files"):
            for f in (repo_metadata.get(key) or []):
                if f.get("content") and f.get("path"):
                    ext = f["path"].rsplit(".", 1)[-1].lower() if "." in f["path"] else "txt"
                    all_files.append({"content": f["content"], "path": f["path"], "type": ext})

        # Try to retrieve pipeline-relevant chunks from what is already stored
        retrieved = self._query_vectorstore_for_pipelines(vector_manager, project_id)

        # If nothing is stored yet, index the fetched files and retry
        if not retrieved and all_files:
            try:
                logger.info(
                    "PipelineDetectionAgent: no content in vectorstore for project %s "
                    "— indexing %d files",
                    project_id, len(all_files),
                )
                vector_manager.add_multiple_repository_files(all_files, project_id, repo_name)
                retrieved = self._query_vectorstore_for_pipelines(vector_manager, project_id)
            except Exception as exc:
                logger.warning("PipelineDetectionAgent: vectorstore index/search failed: %s", exc)

        if retrieved:
            augmented = self._augment_metadata_with_retrieved_chunks(
                repo_metadata, all_files, retrieved
            )
            logger.info(
                "PipelineDetectionAgent: vectorstore augmentation — %d unique chunks "
                "retrieved, context prioritised before LLM call",
                len(retrieved),
            )
            return self.detect(augmented)

        # Fallback: vectorstore unavailable or returned nothing
        logger.info("PipelineDetectionAgent: vectorstore unavailable, falling back to plain detect()")
        return self.detect(repo_metadata)

    def _query_vectorstore_for_pipelines(
        self, vector_manager, project_id: str
    ) -> list[dict]:
        """
        Run all PIPELINE_SEMANTIC_QUERIES against the vectorstore and return
        deduplicated chunk hits ordered by query relevance.
        """
        results: list[dict] = []
        seen: set[str] = set()
        for query in PIPELINE_SEMANTIC_QUERIES:
            try:
                hits = vector_manager.search_repository_content(query, project_id, top_k=6)
                for hit in hits:
                    meta = hit.get("metadata", {})
                    # Deduplicate by file_path + chunk_index
                    uid = f"{meta.get('file_path', '')}:{meta.get('chunk_index', '')}"
                    if uid not in seen:
                        seen.add(uid)
                        results.append(hit)
            except Exception:
                pass
        return results

    def _augment_metadata_with_retrieved_chunks(
        self,
        repo_metadata: dict,
        all_files: list[dict],
        retrieved: list[dict],
    ) -> dict:
        """
        Rebuild the metadata dict so that semantically-retrieved (pipeline-relevant)
        files appear first in each bucket, then fill the remainder with the original
        files up to the same cap.  This focuses the LLM prompt without losing coverage.
        """
        files_by_path = {f["path"]: f for f in all_files}

        # Build synthetic file entries from retrieved chunks so we can leverage
        # vectorstore hits even when that file was not part of the initially fetched subset.
        retrieved_content_by_path: dict[str, str] = {}
        for chunk in retrieved:
            path = str(chunk.get("metadata", {}).get("file_path", "") or "")
            content = str(chunk.get("content", "") or "")
            if not path or not content:
                continue
            if path not in retrieved_content_by_path:
                retrieved_content_by_path[path] = content
            elif content not in retrieved_content_by_path[path]:
                retrieved_content_by_path[path] += "\n\n" + content

        # Collect unique paths in retrieval order (most relevant first)
        prioritised_paths: list[str] = []
        seen: set[str] = set()
        for chunk in retrieved:
            path = chunk.get("metadata", {}).get("file_path", "")
            if path and path not in seen:
                seen.add(path)
                prioritised_paths.append(path)

        aug_sql: list[dict] = []
        aug_py: list[dict] = []
        aug_yaml: list[dict] = []
        aug_code: list[dict] = []

        for path in prioritised_paths:
            raw = files_by_path.get(path)
            if raw:
                content = raw.get("content", "")
            else:
                content = retrieved_content_by_path.get(path, "")
            if not content:
                continue
            d = {"path": path, "name": path.split("/")[-1], "content": content}
            ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path else ""
            if ext == ".sql":
                aug_sql.append(d)
            elif ext == ".py":
                aug_py.append(d)
            elif ext in (".yaml", ".yml"):
                aug_yaml.append(d)
            else:
                aug_code.append(d)

        def _merge(priority: list[dict], original: list, cap: int = 120) -> list:
            p_paths = {f["path"] for f in priority}
            extra = [f for f in original if f.get("path") not in p_paths]
            return priority + extra[:max(0, cap - len(priority))]

        augmented = dict(repo_metadata)
        augmented["sql_files"] = _merge(aug_sql, repo_metadata.get("sql_files") or [])
        augmented["python_files"] = _merge(aug_py, repo_metadata.get("python_files") or [])
        augmented["yaml_files"] = _merge(aug_yaml, repo_metadata.get("yaml_files") or [])
        augmented["code_files"] = _merge(aug_code, repo_metadata.get("code_files") or [])
        return augmented

    @staticmethod
    def _repair_json(text: str) -> str:
        """
        Fix common LLM JSON errors before parsing:
        1. Invalid backslash escapes — PHP/Java namespaces like Ve\\Bundle become Ve\\\\Bundle
           Only characters that ARE valid JSON escapes are left alone: " \\ / b f n r t u
        2. Trailing commas before } or ]
        """
        # Fix invalid escape sequences: replace \X where X is not a valid JSON escape char
        # Valid: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
        def fix_escapes(m: re.Match) -> str:
            ch = m.group(1)
            if ch in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                return m.group(0)  # valid — keep as-is
            return '\\\\' + ch    # double-escape it
        text = re.sub(r'\\([^"\\\//bfnrtu])', fix_escapes, text)
        # Fix trailing commas
        text = re.sub(r',\s*([}\]])', r'\1', text)
        return text

    def _parse(self, raw: str) -> dict:
        raw = (raw or "").strip()
        # Strip ALL markdown code fences (not just at start/end)
        cleaned = re.sub(r"```[a-z]*\n?", "", raw)
        cleaned = re.sub(r"\n?```", "", cleaned)
        cleaned = cleaned.strip()

        # Try parsing in order: full cleaned string → extracted JSON object → extracted JSON array
        # Each candidate is tried raw first, then with JSON repair applied.
        base_candidates: list[str] = [cleaned]
        m_obj = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m_obj:
            base_candidates.append(m_obj.group(0))
        m_arr = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if m_arr:
            base_candidates.append(m_arr.group(0))

        # Build attempt list: try each candidate as-is, then repaired
        candidates: list[str] = []
        for c in base_candidates:
            candidates.append(c)
            repaired = self._repair_json(c)
            if repaired != c:
                candidates.append(repaired)

        data = None
        for attempt in candidates:
            try:
                data = json.loads(attempt)
                break
            except json.JSONDecodeError:
                continue

        if data is None:
            logger.error("_parse: all JSON extraction attempts failed. raw (first 500): %s", raw[:500])
            return {"pipelines": [], "count": 0, "summary": "Could not parse pipeline detection response."}

        if isinstance(data, list):
            pipelines = data
            summary = ""
        else:
            pipelines = data.get("pipelines", [])
            summary = data.get("summary", "")

        for p in pipelines:
                p.setdefault("id", "pipeline_" + str(pipelines.index(p) + 1))
                p.setdefault("name", p["id"])
                p.setdefault("description", "")
                p.setdefault("type", "other")
                p.setdefault("launcher", "unknown")
                p.setdefault("confidence", 0.5)
                p.setdefault("category", "other")
                p.setdefault("direction", "internal")
                p.setdefault("source", "")
                p.setdefault("destination", "")
                if "class" in p and "class_name" not in p:
                    p["class_name"] = p.get("class")
                p.setdefault("class_name", "")
                p.setdefault("config_key", "")
                p.setdefault("queue_or_route", "")
                p.setdefault("dependencies", [])
                try:
                    p["confidence"] = max(0.0, min(1.0, float(p.get("confidence", 0.5))))
                except Exception:
                    p["confidence"] = 0.5
                if p.get("trigger") and not p.get("triggers"):
                    trigger_type = str(p.get("trigger") or "manual")
                    p["triggers"] = [{"type": trigger_type, "detail": p.get("queue_or_route") or trigger_type}]
                if p.get("queue_or_route") and not p.get("queues") and p.get("type") in ("consumer", "producer"):
                    role = "input" if p.get("direction") == "inbound" else "output" if p.get("direction") == "outbound" else "both"
                    p["queues"] = [{
                        "name": p.get("queue_or_route"),
                        "technology": "RabbitMQ" if str(p.get("trigger", "")).lower() == "rabbitmq" else "other",
                        "role": role,
                    }]
                if p.get("type") == "consumer" and not p.get("listen_mode"):
                    p["listen_mode"] = [{"type": "rabbitmq_consumer", "detail": p.get("queue_or_route") or p.get("name", "consumer")}]
                if p.get("class_name") and not p.get("source_files"):
                    p["source_files"] = [p.get("class_name")]
                # ── Infer execution_mode from actual signals — never blindly default to "batch" ──
                listen_mode_val = p.get("listen_mode") or []
                queues_val = p.get("queues") or []
                triggers_val = p.get("triggers") or []
                trigger_val = str(p.get("trigger") or "").lower()
                ptype = str(p.get("type") or "").lower()
                has_queue_signal = bool(listen_mode_val or queues_val or
                    trigger_val in ("rabbitmq", "kafka", "sqs", "pubsub", "amqp") or
                    ptype in ("consumer", "producer", "listener"))
                has_cron_signal = any(
                    str(t.get("type", "")).lower() in ("cron", "scheduled")
                    for t in triggers_val
                ) or trigger_val in ("cron", "scheduled")
                has_webhook_signal = any(
                    str(t.get("type", "")).lower() in ("webhook", "api_call", "http")
                    for t in triggers_val
                ) or trigger_val in ("http", "webhook")
                if not p.get("execution_mode") or p.get("execution_mode") == "batch":
                    if has_queue_signal:
                        p["execution_mode"] = "event_driven"
                    elif has_cron_signal:
                        p["execution_mode"] = "scheduled"
                    elif has_webhook_signal:
                        p["execution_mode"] = "trigger_based"
                    elif trigger_val in ("cli", "manual") or ptype in ("command",):
                        p["execution_mode"] = "on_demand"
                    else:
                        p["execution_mode"] = "batch"
                # Architecture fields — default to empty lists
                p.setdefault("triggers", [])
                p.setdefault("listen_mode", [])
                p.setdefault("queues", [])
                p.setdefault("jobs", [])
                p.setdefault("sub_pipelines", [])
                p.setdefault("parent_pipeline", None)
                # Explainability
                p.setdefault("explainability", {})
                p["explainability"].setdefault("keywords", [])
                p["explainability"].setdefault("orchestration_clues", [])
                p["explainability"].setdefault("evidence_files", p.get("source_files", [])[:5])
                p["explainability"].setdefault("evidence_tables", p.get("source_tables", [])[:5])
                # Core lists
                p.setdefault("source_files", [])
                p.setdefault("source_tables", [])
                p.setdefault("technologies", [])

        return {
            "pipelines": pipelines,
            "count": len(pipelines),
            "summary": summary,
        }
