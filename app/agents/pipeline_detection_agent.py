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


DETECTION_SYSTEM_PROMPT = """You are a senior data engineering architect and reverse-engineering expert.
You deeply analyse repository code, DAG files, YAML configs, SQL scripts, Python scripts, PHP code,
Java/Spring classes, JavaScript/TypeScript files, shell scripts, docker-compose files, and connected
data-source schemas to detect EVERY distinct data pipeline, flux, module, job, or data flow in the project.

Rules:
- Be GRANULAR. Do NOT group unrelated jobs into one pipeline.
- Detect individual jobs, queue listeners, scheduled tasks, console commands, batch processors,
  event handlers, webhook handlers, event consumers, cron scripts — each is potentially its own pipeline.
- Prioritise application/data pipelines implemented in source code (PHP/Python/Java/TS).
  CI/CD files are secondary context and should not dominate the result.
- Be language-agnostic: this applies to any stack/framework, not only listed examples.
- Recognise pipelines in ANY technology stack:
    * Python: Airflow DAGs, Prefect flows, Celery tasks, Luigi pipelines, scripts
    * PHP/Symfony: Console Commands (Command classes), Messenger handlers/consumers, event
      subscribers/listeners, cron-triggered services, Doctrine migrations that load data
    * Java/Spring: @Scheduled methods, Spring Batch jobs (Job/Step/ItemReader/Writer), JMS/AMQP
      message listeners, @EventListener classes
    * Node/TS: Bull/BullMQ workers, Agenda jobs, NestJS @Cron, EventEmitter listeners
    * Shell/Makefile: cron jobs, ETL shell scripts, data load scripts
    * Any service that reads from one place and writes to another IS a pipeline.
- Always respond with VALID JSON ONLY, no extra text, no markdown fences."""


DETECTION_PROMPT = """Analyse the following project metadata extracted from one or more repositories and connected data sources.

## Project metadata:
{metadata_summary}

## Your Task:
Detect ALL distinct data pipelines / flux / modules / jobs in this project.
Be as GRANULAR as possible — do not merge unrelated jobs or flows into one pipeline.
A "pipeline" is ANY process that: reads data from somewhere → does something → writes/sends somewhere.

## What to look for in ANY tech stack:
0. **Any language / framework**
  - Treat business/runtime data flows as first-class pipelines regardless of language
  - Examples: Go workers, .NET hosted services, Rust consumers, Ruby Sidekiq jobs,
    Scala Spark jobs, Elixir consumers, C# Hangfire jobs, etc.
1. **Jobs / Processing units**
   - Python: Airflow DAG tasks, Prefect flows, Celery tasks, standalone scripts, Luigi tasks
   - PHP/Symfony: Console Command classes (extends Command), Symfony Messenger message handlers,
     event subscribers (EventSubscriberInterface), services called from cron
   - Java/Spring: @Scheduled methods, Spring Batch Job/Step, @JmsListener, @RabbitListener,
     @EventListener, CommandLineRunner, ApplicationRunner
   - Node/TS: Bull/BullMQ process() workers, Agenda.define() jobs, @Cron decorators
   - SQL: stored procedures, views that aggregate, migration scripts that transform data
   - Shell: bash scripts loading/transforming files, Makefile ETL targets
2. **Triggers** — cron schedules (crontab, @Scheduled, Airflow schedule_interval), event triggers,
   API calls, sensors, manual execution, CI/CD hooks, file arrival
3. **Listen mode** — Symfony Messenger consumers, Kafka consumers, SQS pollers, RabbitMQ consumers,
   Spring @JmsListener, webhook receivers, CDC (Debezium), socket listeners
4. **Queues / Streams / Topics** — Kafka, RabbitMQ, SQS/SNS, Pub/Sub, Redis Streams, Symfony Messenger
   transports (AMQP, Doctrine, Redis), Celery queues
5. **Sub-pipelines** — pipelines launched by another pipeline (child DAGs, dispatched messages,
   chained jobs, commands calling other commands)
6. **Launchers** — Airflow, Prefect, cron, Symfony Scheduler, @Scheduled, GitHub Actions, Jenkins
7. **Execution mode** — scheduled batch, real-time streaming, event-driven, on-demand, cron
8. **Data flow** — source (DB table / API / file / queue) → transformation → destination

## Important priority rule:
- Prefer pipelines discovered in runtime application code (services, workers, handlers, schedulers,
  ETL jobs, SQL transforms) over CI/CD pipeline definitions.
- Do NOT output generic CI/CD stages (build/test/lint/deploy) as primary pipelines unless they clearly
  perform real business/data processing tasks (for example ETL export/import, DB migration with data load,
  report generation, or data sync jobs).
- If both code pipelines and CI/CD pipelines exist, return code pipelines first and keep CI/CD entries minimal.

## Output rules:
- Each pipeline / job / command / handler MUST have its own entry — do not combine.
- If a Symfony application has 6 Console Commands that each process different data, that is 6 pipelines.
- If a Spring app has 4 @Scheduled methods + 2 @RabbitListener handlers, that is 6 pipelines.
- Use evidence from actual class names, method names, file paths, config keys found in the code.

Respond ONLY with this exact JSON:
{{
  "pipelines": [
    {{
      "id": "snake_case_id",
      "name": "Human-readable pipeline name",
      "description": "What this pipeline does — 2-4 concrete sentences referencing actual code/tables found.",
      "type": "batch|streaming|api|ml|reporting|etl|event_driven|cdc|other",
      "execution_mode": "scheduled|streaming|event_driven|trigger_based|on_demand|manual",
      "confidence": 0.0,
      "launcher": "Airflow|Prefect|cron|API|GitHub Actions|manual|parent_pipeline_id|unknown",
      "triggers": [
        {{"type": "cron|event|api_call|sensor|queue_message|file_arrival|manual|webhook", "detail": "0 2 * * * (daily at 2am)"}}
      ],
      "listen_mode": [
        {{"type": "kafka_consumer|sqs_listener|pubsub_subscription|rabbitmq_consumer|webhook|cdc|none", "detail": "topic: orders.created, group: order_processor"}}
      ],
      "queues": [
        {{"name": "topic_or_queue_name", "technology": "Kafka|SQS|RabbitMQ|PubSub|Redis|Azure SB|other", "role": "input|output|both"}}
      ],
      "jobs": [
        {{"id": "job_snake_id", "name": "Job name", "file": "path/to/file.py", "description": "What this job does", "order": 1}}
      ],
      "sub_pipelines": ["child_pipeline_id_1", "child_pipeline_id_2"],
      "parent_pipeline": null,
      "explainability": {{
        "keywords": ["keyword"],
        "orchestration_clues": ["airflow dag", "cron"],
        "evidence_files": ["dags/ingest_orders.py"],
        "evidence_tables": ["raw.orders"]
      }},
      "source_files": ["path/to/file.py"],
      "source_tables": ["schema.table"],
      "technologies": ["Python", "Airflow", "Kafka", "BigQuery"]
    }}
  ],
  "count": 0,
  "summary": "One or two sentences describing the overall project data architecture."
}}
"""


SYMFONY_FLUX_SYSTEM_PROMPT = """You are a codebase analysis agent specialized in detecting all data flows,
integration pipelines, and processing flux in a Symfony PHP project.

Your task is to scan the entire codebase and produce a structured inventory of every flux/pipeline found.
A flux is any mechanism that moves, transforms, triggers, or reacts to data, synchronously or asynchronously.

Requirements:
- Start from configuration and runtime evidence, not assumptions.
- Prefer verifiable code and config evidence over README descriptions.
- Detect commands, consumers, producers, listeners, subscribers, workflows, REST clients,
    file integrations, scheduled jobs, and inbound API endpoints.
- Do not skip bundles or config imports.
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
Return either:
1. a JSON array of flux entries, OR
2. a JSON object with a `pipelines` array.

Each entry should use this structure when possible:
{{
    "id": "unique-slug",
    "name": "Human-readable name",
    "category": "accounting|crm|grd|lp2|reporting|haulogy|sponsorship|delco|energy|frontend|other",
    "type": "command|consumer|producer|listener|workflow|rest-client|file-import|file-export|api-endpoint|cron|other",
    "trigger": "cli|rabbitmq|http|cron|event|ftp|doctrine|manual",
    "direction": "inbound|outbound|internal",
    "source": "originating system or service",
    "destination": "target system or service",
    "class": "Fully\\Qualified\\ClassName",
    "config_key": "rabbitmq config key or route name if applicable",
    "queue_or_route": "queue name, exchange, routing key, or URL path if applicable",
    "description": "One sentence: what data moves, from where to where, and why",
    "dependencies": ["OtherClass", "ExternalSystem"],
    "jobs": [],
    "listen_mode": [],
    "queues": [],
    "triggers": [],
    "source_files": [],
    "technologies": []
}}
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
        raw = self.llm.generate(prompt, system_prompt=system_prompt)
        logger.info("LLM raw response (first 800 chars): %s", raw[:800])
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

    def _build_summary(self, metadata: dict) -> str:
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
            limit = 15 if ext not in (".json",) else 5
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

            # Require at least one strong executable/runtime signal; queue text alone is not enough.
            if not (has_job or has_schedule or has_listener):
                continue

            signal_score = int(has_job) + int(has_schedule) + int(has_listener) + (1 if queue_hits else 0)
            if signal_score < 2:
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

    def _parse(self, raw: str) -> dict:
        raw = raw.strip()
        # Strip markdown code fences
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()
        try:
            data = json.loads(raw)
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
                p.setdefault("execution_mode", "batch")
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
        except json.JSONDecodeError:
            return {"pipelines": [], "count": 0, "summary": "Could not parse pipeline detection response."}
