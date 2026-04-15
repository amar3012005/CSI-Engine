# MiroFish - Technical Architecture Reference

## Architecture Overview

```
Frontend (Vue 3)                    Backend (Flask)
├── Views (6 pages)                 ├── API Routes (4 blueprints)
├── Components (8 UI parts)         ├── Services (15 modules)
├── API Clients (5 modules)         ├── Models (2 managers)
├── Router + Store                  ├── Utils (5 helpers)
└── D3 Graph Visualization          └── Scripts (4 simulation runners)
```

**5-Step Workflow:**
1. **Graph Build** — Upload docs, extract ontology, build knowledge graph
2. **Environment Setup** — Generate agent profiles, configure simulation
3. **Simulation** — Run CSI research rounds (deepresearch) or social sim (OASIS)
4. **Report** — Generate report from CSI claims/trials via ReACT agent
5. **Interaction** — Chat with report agent, explore findings

---

## Frontend (`frontend/src/`)

### Entry & Config

| File | Purpose | Key Exports |
|------|---------|-------------|
| `main.js` | App entry point | Creates Vue app, mounts router |
| `App.vue` | Root component | `<router-view />`, global styles |
| `router/index.js` | Route definitions | 6 routes: `/`, `/process/:id`, `/simulation/:id`, `/simulation/:id/start`, `/report/:id`, `/interaction/:id` |
| `store/pendingUpload.js` | Upload state store | `setPendingUpload()`, `getPendingUpload()`, `clearPendingUpload()` |

### API Clients (`frontend/src/api/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `index.js` | Axios instance with interceptors | `service` (base URL: `localhost:5001`), `requestWithRetry(fn, retries, delay)` |
| `graph.js` | Graph/project APIs | `generateOntology(formData)`, `buildGraph(data)`, `getTaskStatus(taskId)`, `getGraphData(graphId)`, `getProject(projectId)` |
| `simulation.js` | Simulation lifecycle | `createSimulation()`, `prepareSimulation()`, `getPrepareStatus()`, `startSimulation()`, `stopSimulation()`, `getRunStatus()`, `getRunStatusDetail()`, `getSimulationConfig()`, `getSimulationProfiles()` |
| `report.js` | Report generation | `generateReport(data)`, `getReportStatus(reportId)`, `getReport(reportId)`, `getAgentLog(reportId, fromLine)`, `getConsoleLog(reportId, fromLine)`, `chatWithReport(data)` |
| `csi.js` | CSI artifact queries | `getSimulationCsiState(simId)`, `getSimulationCsiArtifacts(simId, params)`, `getSimulationCsiGraph(simId)` |

### Views (`frontend/src/views/`)

| File | Step | Purpose | Key Props/Data |
|------|------|---------|----------------|
| `Home.vue` | — | Landing page with file upload, requirement input, project history | `files`, `simulationRequirement`, `startSimulation()` |
| `MainView.vue` | 1-2 | Graph build + env setup with split-view layout | `projectId`, `currentStep`, `viewMode`, `graphData`, `ontologyProgress` |
| `SimulationView.vue` | 2 | Environment setup detailed view | `simulationId`, config mode selector (Social vs DeepResearch) |
| `SimulationRunView.vue` | 3 | Simulation execution with real-time progress | `simulationId`, `maxRounds`, `isSimulating`, `csiShouldAutoRefresh` |
| `ReportView.vue` | 4 | Report generation with section streaming | `reportId`, section list, markdown rendering |
| `InteractionView.vue` | 5 | Chat with report agent, explore findings | `reportId`, `chatMessages`, deep research toggle |

### Components (`frontend/src/components/`)

| File | Purpose | Key Features |
|------|---------|--------------|
| `GraphPanel.vue` | D3 force-directed graph visualization | SVG rendering, node/edge detail panel, CSI layer toggle (`showCsiLayer`), edge label toggle, zoom/pan, CSI auto-refresh, entity type legend with CSI colors (Claim=#7B2D8E, Trial=#FF8A34, Recall=#2196F3) |
| `Step1GraphBuild.vue` | Ontology generation + graph build progress | Phase tracking (ontology->building->complete), entity/relation display, progress spinners |
| `Step2EnvSetup.vue` | Simulation creation + environment preparation | Mode selector, agent profile generation, configuration polling, CSI artifact preview |
| `Step3Simulation.vue` | Dual-platform simulation execution | Platform status cards (Plaza/Community), round/time/action counters, timeline feed with action cards, **Swarm Intelligence Artifacts** review panel (shown on completion), CsiArtifactList integration |
| `Step4Report.vue` | Report section-by-section generation | Outline navigation, section progress indicators, markdown content rendering, workflow timeline |
| `Step5Interaction.vue` | Agent chat + report browsing | Report outline panel, chat interface, deep research mode |
| `CsiArtifactList.vue` | CSI artifacts display (Claims, Trials, Recalls, Actions, Relations) | Stat chips (6 metrics), expandable sections with confidence/verdict badges, "Show all" toggle, auto-refresh support |
| `HistoryDatabase.vue` | Project history cards | Project grid, expand/collapse animation, simulation ID display |

---

## Backend (`backend/`)

### Entry & Config

| File | Purpose | Key Exports |
|------|---------|-------------|
| `run.py` | Flask server entry point | `main()` — validates config, creates app, starts server |
| `app/__init__.py` | Flask app factory | `create_app(config_class)` — registers blueprints, CORS, logging, cleanup |
| `app/config.py` | Environment configuration | `Config` — `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME`, `GRAPH_PROVIDER`, `zep_enabled()`, `validate()` |

### API Routes (`backend/app/api/`)

| File | Blueprint | Key Endpoints |
|------|-----------|---------------|
| `graph.py` | `graph_bp` | `POST /api/graph/ontology/generate` — upload docs, generate ontology via LLM; `POST /api/graph/build` — async graph construction; `GET /api/graph/task/<id>` — poll build progress; `GET /api/graph/data/<graph_id>` — fetch nodes/edges; `GET /api/graph/project/<id>` — project info |
| `simulation.py` | `simulation_bp` | `POST /api/simulation/create` — init simulation; `POST /api/simulation/prepare` — async env setup (profiles, config, CSI); `POST /api/simulation/<id>/start` — launch simulation; `GET /api/simulation/<id>/run-status` — poll progress; `GET /api/simulation/<id>/csi/state` — CSI artifacts summary; `GET /api/simulation/<id>/csi/graph` — CSI nodes/edges for D3; `GET /api/simulation/<id>/csi/artifacts` — filtered artifact queries |
| `report.py` | `report_bp` | `POST /api/report/generate` — async report generation; `GET /api/report/<id>` — fetch report; `GET /api/report/<id>/sections` — incremental sections; `GET /api/report/<id>/agent-log` — agent execution trace; `POST /api/report/chat` — chat with report agent |
| `csi.py` | `csi_bp` | `POST /api/csi/ingest-sources` — ingest sources; `POST /api/csi/extract-claims` — extract claims |

### Services (`backend/app/services/`)

| File | Class | Purpose | Key Methods |
|------|-------|---------|-------------|
| `ontology_generator.py` | `OntologyGenerator` | LLM-powered ontology design from documents | `generate(document_texts, simulation_requirement)` — analyzes docs, returns entity/edge type definitions |
| `graph_builder.py` | `GraphBuilderService` | Knowledge graph construction via Zep/HIVEMIND | `create_graph(name)`, `set_ontology(graph_id, ontology)`, `add_text_batches(graph_id, chunks)`, `get_graph_data(graph_id)`, `build_graph_async()` |
| `text_processor.py` | `TextProcessor` | Text preprocessing and chunking | `extract_from_files(paths)`, `split_text(text, chunk_size, overlap)`, `preprocess_text(text)` |
| `zep_entity_reader.py` | `ZepEntityReader` | Read entities from Zep graph | `read_entities(graph_id, entity_types)`, `enrich_entity_with_neighbors(node, graph_id)`. Dataclasses: `EntityNode`, `FilteredEntities` |
| `oasis_profile_generator.py` | `OasisProfileGenerator` | Convert graph entities to agent profiles | `generate(entities, graph_id, requirement)`. Dataclass: `OasisAgentProfile` with `to_reddit_format()`, `to_twitter_format()` |
| `simulation_config_generator.py` | `SimulationConfigGenerator` | LLM-generated simulation parameters | `generate_config()`. Dataclasses: `AgentActivityConfig`, `TimeSimulationConfig`, `EventConfig`, `SimulationParameters`, `ResearchAgentAssignment`, `ResearchWorkflowConfig` (claim_policy, debate_policy, verdict_policy, gate_policy) |
| `simulation_manager.py` | `SimulationManager` | Simulation lifecycle management | `create_simulation()`, `prepare_simulation()`, `get_simulation()`. Dataclass: `SimulationState` with `SimulationStatus` enum |
| `simulation_runner.py` | `SimulationRunner` | Execute simulations (OASIS subprocess or CSI research) | `start_simulation(sim_id, platform, max_rounds)` — branches on `config_mode`: `social` -> OASIS subprocess, `deepresearch` -> CSI research engine directly; `_monitor_simulation()` — background thread reading action logs; `_run_csi_research_phase(state)` — runs LLM-powered research rounds; `_load_agent_roster(sim_id)` — merges profiles with research assignments. Dataclasses: `SimulationRunState`, `AgentAction`, `RoundSummary` |
| `simulation_csi_local.py` | `SimulationCSILocalStore` | Local file-based CSI artifact storage (JSONL) | `initialize_from_prepare()` — builds sources index, sets up CSI directory; `record_claim()`, `record_trial()`, `record_recall()`, `record_relation()`, `record_agent_action()` — append to JSONL files; `record_runtime_action(payload)` — converts social/research actions into claims/trials with `_extract_best_text()`, `_is_interaction_action()`, `_infer_verdict_from_action()`; `get_snapshot()` — returns all artifacts; `advance_round_count()` |
| `csi_research_engine.py` | `CSIResearchEngine` | LLM-powered CSI research rounds | `run_research_rounds(num_rounds, requirement)` — orchestrates 5 phases per round: **Investigation** (source selection), **Proposal** (LLM claim synthesis), **Peer Review** (LLM verdict), **Revision** (LLM claim update), **Synthesis** (consolidate findings). Enforces policies: `claim_policy`, `debate_policy`, `verdict_policy`, `gate_policy`. Falls back to template methods on LLM failure |
| `report_agent.py` | `ReportAgent` | ReACT-based report generation agent | `generate_report(progress_callback, report_id)` — plans outline then generates sections via tool-calling loop; `plan_outline()` — LLM plans report structure using CSI summary; `_generate_section_react()` — per-section ReACT loop with max 5 tool calls; `_define_tools()` — CSI tools (query_claims, query_trials, query_consensus, query_contradictions, trace_provenance) + graph tools (insight_forge, panorama_search, quick_search, interview_agents); `chat(message, history)` — conversational follow-up. Helper classes: `ReportLogger`, `ReportConsoleLogger`, `ReportManager` |
| `zep_tools.py` | `ZepToolsService` | Graph search + CSI query tools for report agent | Graph tools: `insight_forge()`, `panorama_search()`, `quick_search()`, `interview_agents()`, `get_simulation_context()`. CSI tools: `query_csi_claims(sim_id, status, min_confidence)`, `query_csi_trials(sim_id, verdict)`, `query_csi_consensus(sim_id, min_supporting)`, `query_csi_contradictions(sim_id)`, `trace_csi_provenance(sim_id, claim_id)`, `get_csi_summary(sim_id)` |
| `zep_graph_memory_updater.py` | `ZepGraphMemoryUpdater` | Sync agent activities to Zep graph memory | `add_activity(activity)`, `add_activity_from_dict(action_data, platform)`, `start()`, `stop()`. Dataclass: `AgentActivity` with `to_episode_text()`. Manager: `ZepGraphMemoryManager.create_updater()` |
| `simulation_ipc.py` | `SimulationIPCClient` / `SimulationIPCServer` | File-based IPC between Flask and simulation subprocess | Client: `send_command(cmd)`, `wait_response(id, timeout)`. Server: `listen()`, `handle_command()`. Commands: `INTERVIEW`, `BATCH_INTERVIEW`, `CLOSE_ENV` |
| `csi_adapter.py` | `CSIAdapter` | Unified CSI persistence (HIVEMIND API or local) | `ingest_sources()`, `extract_claims()`, `verdict_trial()`, `agent_action()`, `blueprint()` |

### Models (`backend/app/models/`)

| File | Class | Purpose | Key Methods |
|------|-------|---------|-------------|
| `project.py` | `ProjectManager` | Project lifecycle and file management | `create_project(name)`, `get_project(id)`, `save_project()`, `delete_project()`, `save_file_to_project()`, `get_extracted_text()`. Dataclass: `Project` with `ProjectStatus` enum |
| `task.py` | `TaskManager` | Long-running task tracking (singleton) | `create_task(type, metadata)`, `get_task(id)`, `update_task(id, status, progress)`. Dataclass: `Task` with `TaskStatus` enum |

### Utilities (`backend/app/utils/`)

| File | Class/Function | Purpose |
|------|---------------|---------|
| `llm_client.py` | `LLMClient` | OpenAI-compatible LLM client. `chat(messages, temperature, max_tokens)` — handles Groq `tool_use_failed` / `output_parse_failed` by extracting `failed_generation` and unwrapping nested tool calls; `chat_json()` — returns parsed JSON |
| `file_parser.py` | `FileParser` | Text extraction from PDF/MD/TXT. `extract_text(path)`, `extract_from_multiple(paths)`, `split_text_into_chunks()` |
| `logger.py` | `get_logger(name)` | Centralized UTF-8 logging. `setup_logger()`, `get_logger()` |
| `retry.py` | `RetryableAPIClient` | Exponential backoff retry. `call_with_retry()`, `@retry_with_backoff()` decorator |
| `zep_paging.py` | `fetch_all_nodes()` / `fetch_all_edges()` | Zep API auto-pagination for large graphs |

### Scripts (`backend/scripts/`)

| File | Purpose | Key Features |
|------|---------|--------------|
| `run_parallel_simulation.py` | Execute Twitter + Reddit OASIS simulation in parallel | Dual-platform concurrent execution, action enrichment (`_enrich_action_context` adds `original_content`, `post_author_name`, `quote_content`), IPC interview support |
| `run_twitter_simulation.py` | Twitter-only OASIS simulation | `_fetch_new_actions_from_db()` reads SQLite trace table, action logging to JSONL |
| `run_reddit_simulation.py` | Reddit-only OASIS simulation | Same as Twitter with karma-based reputation |
| `action_logger.py` | JSONL action logging | `PlatformActionLogger` — `log_action()`, `log_round_start()`, `log_round_end()`, `log_simulation_start()`, `log_simulation_end()` |

---

## Data Flow

```
Step 1: Upload docs -> TextProcessor -> OntologyGenerator (LLM) -> GraphBuilder (Zep/local)
                                                                        |
Step 2: ZepEntityReader -> OasisProfileGenerator (LLM) -> SimulationConfigGenerator (LLM)
         |                                                    |
    Agent Profiles                              ResearchWorkflowConfig
    (profiles_snapshot.json)                    (claim/debate/verdict/gate policies)
                                                        |
Step 3: SimulationRunner.start_simulation()
         |-- config_mode="social"        -> OASIS subprocess (tweets/likes/comments)
         |                                  | actions -> record_runtime_action() -> CSI store
         +-- config_mode="deepresearch"  -> CSIResearchEngine directly
                                            | investigate -> propose -> peer_review -> revise -> synthesize
                                            | all artifacts written to CSI JSONL files
                                                        |
Step 4: ReportAgent.generate_report()
         |-- plan_outline() -- uses CSI summary + graph context
         +-- _generate_section_react() -- ReACT loop calling:
              |-- query_claims()         -> CSI claims by status/confidence
              |-- query_consensus()      -> high-agreement findings
              |-- query_contradictions() -> contested claim pairs
              |-- query_trials()         -> peer review verdicts
              |-- trace_provenance()     -> claim -> source -> trial chain
              +-- insight_forge()        -> supplementary graph search (if Zep enabled)
                                                        |
Step 5: ReportAgent.chat() -- conversational follow-up with report context
```

## File Storage Structure

```
backend/uploads/
|-- projects/<project_id>/
|   |-- project.json              # Project metadata
|   |-- uploads/                  # Uploaded documents
|   +-- extracted_text.txt        # Processed document text
|-- graphs/<graph_id>.json        # Local graph data (nodes/edges)
|-- simulations/<simulation_id>/
|   |-- simulation_config.json    # Full simulation parameters
|   |-- twitter/actions.jsonl     # Twitter platform action log
|   |-- reddit/actions.jsonl      # Reddit platform action log
|   |-- simulation.log            # Process stdout/stderr
|   |-- run_state.json            # Runner status and progress
|   +-- csi/
|       |-- state.json            # CSI round counts, artifact counts
|       |-- sources_index.json    # Indexed source documents
|       |-- claims.jsonl          # Agent-proposed claims (append-only)
|       |-- trials.jsonl          # Peer review verdicts (append-only)
|       |-- recalls.jsonl         # Memory recall queries (append-only)
|       |-- agent_actions.jsonl   # All agent actions (append-only)
|       |-- relations.jsonl       # Entity relationships (append-only)
|       |-- profiles_snapshot.json # Agent profile data
|       +-- manifest.json         # File versions
+-- reports/<report_id>/
    |-- meta.json                 # Report metadata
    |-- outline.json              # Report structure
    |-- progress.json             # Generation progress
    |-- section_01.md             # Generated sections
    |-- section_02.md
    |-- full_report.md            # Assembled report
    |-- agent_log.jsonl           # Agent execution trace
    +-- console_log.txt           # Runtime logs
```
