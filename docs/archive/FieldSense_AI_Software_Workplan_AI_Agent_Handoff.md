# FieldSense AI --- Software Engineering Workplan & AI Agent Handoff Specification

**Document Type:** Master Software Workplan / Engineering Playbook\
**Project:** FieldSense AI\
**Current Phase:** Phase 1 complete --- Phase 2 hardware integration
next\
**Current Release Status:** `PHASE_1_RELEASE_READY`\
**Current Regression Baseline:** `105 passed`\
**Target Platform:** Arduino UNO Q (4 GB / 32 GB variant)\
**Primary Runtime:** Debian Linux on Qualcomm QRB2210\
**Real-Time / Peripheral Boundary:** STM32U585\
**Project Context:** Arduino Physical AI Challenge India 2026 +
university-funded research prototype, Mahindra University

------------------------------------------------------------------------

## 0. Purpose of This Document

This document is the **long-term engineering handoff manual** for
FieldSense AI software.

Its purpose is bigger than documenting what has already been built.

It defines:

1.  **What FieldSense is**
2.  **Why the architecture exists**
3.  **How the software is developed**
4.  **How work is divided into sprints**
5.  **How AI coding agents such as Antigravity/Gemini are instructed**
6.  **How completed work is reviewed**
7.  **How contracts are frozen**
8.  **How future engineers or AI agents can continue the project without
    reconstructing the project history from old chats**
9.  **How hardware integration must occur without rewriting the
    deterministic software pipeline**

A future engineer or AI agent should be able to read this document
together with the repository and immediately understand:

> what the system does, what must never change casually, how to
> implement the next sprint, how to test it, and how to report
> completion.

This document is therefore treated as a **project control document**,
not merely a README.

------------------------------------------------------------------------

# 1. Project Mission

FieldSense AI is an offline, portable edge-intelligence platform for
multi-point soil assessment and Carbon Readiness.

The core problem is spatial variation.

A field may contain substantially different soil conditions at different
locations, while conventional testing may rely on only a few samples.
FieldSense collects multiple GPS-tagged soil measurements and converts
them into:

-   a Field Intelligence Map
-   parameter-wise spatial layers
-   management zones
-   structured decision-support recommendations
-   optional AI-generated explanations

The system is designed to work **offline** and must remain usable
without cloud infrastructure.

------------------------------------------------------------------------

# 2. Core Software Pipeline

The canonical pipeline is:

``` text
Raw Sensor Data
      ↓
FieldSample
      ↓
Validation
      ↓
Normalization
      ↓
Deterministic Intelligence
      ↓
Spatial Processing / Interpolation
      ↓
Zone Detection
      ↓
Recommendations
      ↓
UI Data Model
      ↓
Offline UI
      ↓
Optional AI Explanation
```

The critical architectural principle is:

``` text
Virtual Sensor ──────┐
                     │
                     ▼
                 FieldSample
                     │
Hardware Sensor ─────┘
                     │
                     ▼
               SAME PIPELINE
```

The rest of the software must not care whether a sample came from a
simulator or physical hardware.

------------------------------------------------------------------------

# 3. Non-Negotiable Architecture Principles

## 3.1 Deterministic Core

The deterministic software layer owns:

-   sensor validation
-   data cleaning
-   normalization
-   parameter scoring
-   soil-health calculations
-   Carbon Readiness calculations
-   spatial processing
-   map generation
-   zone detection
-   recommendation rules

The deterministic layer must not depend on an LLM.

------------------------------------------------------------------------

## 3.2 AI Is Not the Calculator

The future AI layer consumes already-computed structured results.

It may:

-   explain a zone
-   simplify technical results
-   explain why a recommendation exists
-   answer farmer-facing questions using deterministic results

It must not independently invent:

-   soil measurements
-   scores
-   interpolation results
-   zones
-   fertilizer quantities
-   irrigation quantities
-   carbon-credit claims

Conceptually:

``` text
Deterministic Engine
        ↓
Structured Results
        ↓
Optional AI Explanation
```

Never:

``` text
Raw Sensor
    ↓
LLM
    ↓
Agricultural Truth
```

------------------------------------------------------------------------

## 3.3 Hardware Isolation

The rest of the system must not know that the JXBS sensor communicates
through RS485/Modbus.

The hardware-specific layer converts physical readings into the
canonical domain object:

``` text
Physical Hardware
      ↓
Hardware Adapter
      ↓
FieldSample
      ↓
Common Pipeline
```

------------------------------------------------------------------------

## 3.4 UI Is Passive

The UI must not calculate intelligence.

It receives already-processed results:

``` text
Backend
   ↓
UI Data Contract
   ↓
Renderer
```

No score calculation, interpolation, zone detection, or recommendation
logic belongs in the UI.

------------------------------------------------------------------------

## 3.5 Offline First

Core operation must not depend on:

-   cloud APIs
-   remote map APIs
-   external web services
-   LLM APIs
-   heavy ML frameworks

The target runtime is Debian Linux on Arduino UNO Q.

------------------------------------------------------------------------

## 3.6 No Guessing Hardware Specifications

Unknown physical specifications must be explicitly represented as:

``` text
HARDWARE_SPEC_REQUIRED
```

Do not guess:

-   Modbus register addresses
-   slave address
-   baud rate
-   parity
-   stop bits
-   UART device path
-   GPIO assignments
-   MPU/MCU ownership
-   RS485 DE/RE behavior

Hardware Engineering must provide those values.

------------------------------------------------------------------------

# 4. Canonical Domain Object

## FieldSample

`FieldSample` is the most important object in the software.

Everything downstream consumes it.

Canonical conceptual fields:

``` text
sample_id
timestamp
latitude
longitude
nitrogen
phosphorus
potassium
ph
ec
moisture
temperature
measurement_quality
source
validation_state
```

Sources:

``` text
VIRTUAL
HARDWARE
```

Validation states:

``` text
VALID
VALID_WITH_WARNING
REJECTED
```

`FieldSample` is immutable.

Raw observations must not be silently changed by downstream processing.

------------------------------------------------------------------------

# 5. FieldSession

A `FieldSession` represents a complete sampling session.

Conceptually:

``` text
FieldSession
 ├── metadata
 ├── raw samples[]
 ├── field result
 ├── spatial result
 ├── zones[]
 └── recommendations[]
```

Important rule:

``` text
raw samples = source of truth
```

Rejected samples remain stored for auditability.

Derived intelligence must never mutate the raw samples.

`sample_count` is derived from the actual sample collection.

------------------------------------------------------------------------

# 6. Frozen Module Boundaries

The project is divided into bounded modules.

Conceptually:

``` text
domain
input / sensor
hardware
intelligence.validation
intelligence.normalization
intelligence.scoring
spatial
zones
recommendations
presentation
testing
demo
```

Dependency direction:

``` text
Acquisition
    ↓
Domain
    ↓
Validation / Normalization
    ↓
Deterministic Intelligence
    ↓
Spatial
    ↓
Zones
    ↓
Recommendations
    ↓
Presentation
```

Reverse dependencies should be treated as architecture defects.

Examples:

``` text
UI → scoring                  WRONG
Hardware → recommendations    WRONG
Spatial → UI                   WRONG
Domain → presentation         WRONG
LLM → deterministic scoring   WRONG
```

------------------------------------------------------------------------

# 7. Development Methodology

FieldSense is developed using a **contract-first, sprint-based,
AI-assisted engineering workflow**.

The human engineer owns:

-   architecture
-   requirements
-   contracts
-   scientific boundaries
-   hardware decisions
-   sprint scope
-   approval decisions

The AI coding agent owns:

-   bounded implementation
-   test creation
-   refactoring within scope
-   static checks
-   regression testing
-   implementation reporting

The AI agent does **not** own architecture.

The governing workflow is:

``` text
Human Architecture
        ↓
Sprint Contract
        ↓
AI Agent Implementation
        ↓
Automated Tests
        ↓
Human / Architecture Review
        ↓
Sprint Report
        ↓
Freeze
        ↓
Next Sprint
```

------------------------------------------------------------------------

# 8. The Sprint Philosophy

A sprint should accomplish **one coherent engineering objective**.

A sprint should not be:

> "Build the whole system."

A sprint should be:

> "Implement the Validation Engine contract and prove its behavior."

Each sprint must have:

-   objective
-   inputs
-   allowed modules
-   contract
-   constraints
-   implementation tasks
-   tests
-   definition of done
-   expected report

------------------------------------------------------------------------

# 9. Standard Sprint Contract

Every future sprint should be sent to the AI coding agent using this
structure.

``` text
# Sprint X — <Name>

## Objective

<One clear engineering objective>

## Context

<Why this sprint exists>

## Inputs

<Existing models, interfaces, modules, specifications>

## Allowed Files / Modules

<List exact directories or files the agent may modify>

## Contract

<Exact interface and behavioral requirements>

## Constraints

<Things the agent must not do>

## Implementation Tasks

1. ...
2. ...
3. ...

## Tests Required

1. ...
2. ...
3. ...

## Integration Requirements

<How this sprint connects to existing pipeline>

## Definition of Done

- [ ] ...
- [ ] ...
- [ ] ...

## Forbidden Changes

- Do not redesign ...
- Do not modify frozen ...
- Do not introduce ...
- Do not guess ...

## Final Report Required

Return:

1. Files created/modified
2. Implementation summary
3. Tests added
4. Full regression result
5. Architectural decisions
6. Issues/ambiguities
7. Remaining work
```

This template is mandatory for future AI-agent implementation work.

------------------------------------------------------------------------

# 10. AI Agent Operating Rules

The coding agent must follow these rules.

## Rule 1 --- Inspect Before Editing

Before writing code:

-   inspect the repository
-   inspect relevant contracts
-   inspect existing tests
-   inspect current implementation

Do not assume a file does not exist.

------------------------------------------------------------------------

## Rule 2 --- Do Not Rewrite Unrelated Modules

If implementing validation, do not casually rewrite:

-   spatial processing
-   UI
-   recommendations
-   hardware
-   AI

------------------------------------------------------------------------

## Rule 3 --- Preserve Frozen Contracts

If an existing contract must change, report it before changing it.

Use:

``` text
CONTRACT_CHANGE_REQUIRED
```

with:

-   current contract
-   proposed change
-   reason
-   affected modules
-   migration impact
-   tests affected

------------------------------------------------------------------------

## Rule 4 --- Test Every Change

Every sprint must add or update tests where behavior is introduced.

Then run the entire regression suite.

A sprint is not complete because its local tests pass.

The full suite must pass.

------------------------------------------------------------------------

## Rule 5 --- Never Hide Failure

Do not introduce silent exception handling such as:

``` python
except Exception:
    pass
```

unless there is an explicitly documented reason.

------------------------------------------------------------------------

## Rule 6 --- Do Not Invent Science

If a scientific/agronomic value is not approved:

``` text
METHODOLOGY_TBD
```

or:

``` text
PROTOTYPE_ONLY
AGRONOMIC_VALIDATION_REQUIRED
```

must be used.

------------------------------------------------------------------------

## Rule 7 --- Do Not Guess Hardware

Use:

``` text
HARDWARE_SPEC_REQUIRED
```

until Hardware Engineering confirms the value.

------------------------------------------------------------------------

## Rule 8 --- Prefer Standard Library

The current architecture intentionally avoids heavy dependencies.

Do not introduce:

-   NumPy
-   SciPy
-   Pandas
-   PyTorch
-   TensorFlow
-   cloud SDKs

without explicit architectural approval.

------------------------------------------------------------------------

# 11. Sprint Lifecycle

Every sprint follows these stages.

## Stage A --- Define

Human creates the sprint contract.

``` text
Goal
Scope
Interfaces
Constraints
Tests
Definition of Done
```

------------------------------------------------------------------------

## Stage B --- Agent Briefing

The sprint contract is given to Antigravity or another coding agent.

The agent must first inspect the repository.

------------------------------------------------------------------------

## Stage C --- Implementation

The agent implements only the bounded scope.

------------------------------------------------------------------------

## Stage D --- Verification

Agent runs:

``` text
unit tests
integration tests
full regression tests
```

where applicable.

------------------------------------------------------------------------

## Stage E --- Report

The agent produces an implementation report.

------------------------------------------------------------------------

## Stage F --- Human Review

Human checks:

-   architecture
-   assumptions
-   scientific boundaries
-   hardware assumptions
-   test quality
-   unintended scope expansion

------------------------------------------------------------------------

## Stage G --- Freeze

Once accepted:

``` text
SPRINT_X_FROZEN
```

The sprint's contract becomes part of the architecture baseline.

------------------------------------------------------------------------

# 12. Phase 0 --- Architecture Freeze

Phase 0 existed to define contracts before implementation.

The required contracts were:

1.  FieldSample
2.  Sensor Adapter
3.  Validation
4.  Scoring
5.  Spatial
6.  Zone
7.  Recommendation
8.  Storage
9.  UI
10. Hardware Boundary

The rule was:

> No implementation sprint should be allowed to redefine these casually.

Phase 0 definition of done:

``` text
Architecture v0.1
+
FieldSample contract
+
Module boundaries
+
Data flow
+
Validation states
+
Interfaces
+
Test strategy
```

------------------------------------------------------------------------

# 13. Phase 1 Sprint History

## Sprint 1 --- Core Domain Models

Implemented:

-   project foundation
-   FieldSample
-   FieldSession
-   enums
-   serialization
-   tests

Key architectural decision:

`FieldSample` is immutable.

Initial regression:

``` text
15 passed
```

------------------------------------------------------------------------

## Sprint 2 --- Sensor Abstraction & Virtual Field

Implemented:

-   SensorAdapter
-   VirtualSensorAdapter
-   virtual field generator
-   spatial variation
-   repeatable seeds
-   outlier scenario
-   unstable scenario

Key principle:

The simulator produces raw measurements, not final intelligence.

Regression:

``` text
24 passed
```

------------------------------------------------------------------------

## Sprint 3 --- Validation Engine

Implemented:

-   ValidationEngine
-   ValidationResult
-   validation reasons
-   centralized sanity thresholds
-   eligibility gate

Precedence:

``` text
REJECTED
    >
VALID_WITH_WARNING
    >
VALID
```

Rejected samples remain stored but cannot enter downstream intelligence.

Regression:

``` text
34 passed
```

------------------------------------------------------------------------

## Sprint 4A --- Intelligence Contracts

Defined:

-   NormalizedSample
-   ParameterScore
-   SoilHealthResult
-   NitrogenResult
-   MoistureResult
-   CarbonReadinessResult
-   FieldIntelligenceResult
-   IntelligenceConfig
-   engine boundary

Scientific formulas were intentionally not invented in this sprint.

Regression:

``` text
44 passed
```

------------------------------------------------------------------------

## Sprint 4B --- Deterministic Methodology

Implemented:

-   normalization
-   deterministic scoring
-   prototype reference bands
-   Soil Health weighted calculation
-   Carbon Readiness proxy

Safety boundary:

``` text
PROTOTYPE_ONLY
AGRONOMIC_VALIDATION_REQUIRED
```

Carbon Readiness:

``` text
decision_support_only = True
evidence_level = LIMITED
```

No SOC measurement or carbon-credit certification claims.

Regression:

``` text
49 passed
```

------------------------------------------------------------------------

## Sprint 5 --- Spatial Intelligence

Implemented:

-   field bounds
-   local Cartesian conversion
-   regular grid
-   IDW interpolation
-   spatial layers
-   coverage metrics

Configuration:

``` text
grid spacing = 10 m
IDW power = 2
minimum samples = 3
maximum support distance = 100 m
```

Sparse data must not create fabricated surfaces.

Regression:

``` text
56 passed
```

------------------------------------------------------------------------

## Sprint 6 --- Zone Detection

Implemented:

-   connected components
-   4-neighbor connectivity
-   minimum-zone merging
-   parameter enrichment
-   primary issue selection
-   confidence
-   centroid
-   area estimate

Regression:

``` text
62 passed
```

------------------------------------------------------------------------

## Sprint 7 --- Recommendation Engine

Implemented:

-   rule abstraction
-   nutrient rule
-   moisture rule
-   salinity rule
-   soil-condition rule
-   carbon rule
-   monitoring rule
-   structured recommendations
-   priority
-   evidence
-   deduplication
-   recommendation limits

No fertilizer dosages or irrigation volumes.

Regression:

``` text
71 passed
```

------------------------------------------------------------------------

## Sprint 8 --- Offline UI

Implemented:

-   UIFieldView
-   passive backend-to-UI adapter
-   offline HTML/CSS/SVG renderer
-   Field Intelligence Map
-   layer switching
-   zones
-   recommendations
-   diagnostics

UI performs no intelligence calculations.

Regression:

``` text
75 passed
```

------------------------------------------------------------------------

## Sprint 9 --- Hardware Integration Boundary

Implemented:

-   SensorTransport
-   GPSAdapter
-   HardwareSensorAdapter
-   mock hardware transport
-   hardware error model
-   source factory
-   hardware configuration placeholders

Physical specifications were intentionally left as:

``` text
HARDWARE_SPEC_REQUIRED
```

Regression:

``` text
83 passed
```

------------------------------------------------------------------------

## Sprint 10 --- System Validation & Demonstration

Implemented:

-   golden scenarios
-   fault injection
-   benchmark suite
-   demo runner
-   limitations documentation
-   end-to-end demonstration

Validated:

-   healthy field
-   nutrient deficiency
-   moisture deficiency
-   mixed field
-   spatial gradient
-   outlier
-   unstable measurement
-   sparse sampling

Regression:

``` text
98 passed
```

------------------------------------------------------------------------

## Sprint 11 --- Competition Demo

Implemented:

-   competition demo dataset
-   showcase dashboard
-   demonstration guide
-   competition demo tests

Competition scenario:

``` text
25 samples
24 valid
1 rejected
67% soil health
100% coverage
4 zones
10 recommendations
```

Regression:

``` text
102 passed
```

------------------------------------------------------------------------

## Sprint 12 --- Final Audit & Hardening

Purpose:

> Audit everything before physical hardware integration.

The audit checked:

-   architecture
-   serialization
-   dependencies
-   contracts
-   methodology boundaries
-   Carbon Readiness safety
-   spatial behavior
-   zones
-   recommendations
-   UI
-   hardware boundary
-   proposal alignment
-   test quality
-   documentation

Issues found and fixed included:

-   FieldSample timestamp serialization defect
-   FieldSession deserialization gap
-   hardware model serialization gaps
-   intelligence model deserialization gaps

Final regression:

``` text
105 passed
```

Final status:

``` text
PHASE_1_RELEASE_READY
```

The final audit also produced/verified:

``` text
SPECIFICATION_REGISTER.md
PROPOSAL_ALIGNMENT.md
```

------------------------------------------------------------------------

# 14. Phase 1 Final State

The current deterministic pipeline is:

``` text
VirtualSensorAdapter / HardwareSensorAdapter
                    ↓
               FieldSample
                    ↓
              Validation
                    ↓
             Normalization
                    ↓
        Deterministic Intelligence
                    ↓
            Spatial Engine
                    ↓
            Zone Detection
                    ↓
       Recommendation Engine
                    ↓
             UIViewAdapter
                    ↓
          Offline UI Renderer
```

Current release baseline:

``` text
105 tests passed
0 failures
PHASE_1_RELEASE_READY
```

------------------------------------------------------------------------

# 15. Current Known Specification Register

The following are intentionally unresolved and must not be guessed.

## Hardware

### HW-01

JXBS 7-in-1 Modbus RTU register map.

### HW-02

JXBS RS485 baud rate and parity settings.

### HW-03

NEO-M8N GPS UART device path on Debian Linux.

### HW-04

Arduino UNO Q MPU vs MCU peripheral ownership.

## Agronomic

### AG-01

Agronomic optimum bands and weighting vectors require validation using
regional soil data.

## Platform

### PF-01

Physical Arduino UNO Q benchmark is pending physical hardware.

------------------------------------------------------------------------

# 16. Phase 2 --- Physical Hardware Integration

Phase 2 begins only after Phase 1 is frozen.

Primary hardware:

``` text
JXBS 7-in-1 soil sensor
NEO-M8N GPS
Arduino UNO Q
RS485 transceiver / interface
```

The goal is NOT to rewrite the pipeline.

The goal is:

``` text
Replace:
VirtualSensorAdapter

With:
HardwareSensorAdapter

while preserving:
FieldSample
Validation
Normalization
Intelligence
Spatial
Zones
Recommendations
UI
```

------------------------------------------------------------------------

# 17. Hardware Integration Workflow

## Step 1 --- Hardware Specification Collection

Hardware Engineering provides:

### JXBS

-   register addresses
-   units
-   slave address
-   baud rate
-   parity
-   stop bits
-   measurement timing

### GPS

-   UART path
-   baud rate
-   NMEA configuration
-   update rate

### UNO Q

-   MPU/MCU ownership
-   UART mapping
-   RS485 mapping
-   DE/RE control
-   bridge protocol

------------------------------------------------------------------------

## Step 2 --- Freeze Hardware Interface Contract

Before implementation:

``` text
Hardware Specification
        ↓
Hardware Adapter Contract
        ↓
Implementation
```

Do not code from assumptions.

------------------------------------------------------------------------

## Step 3 --- Implement Transport

Only the transport layer should know about:

-   serial communication
-   Modbus frames
-   registers
-   UART
-   GPIO direction control

------------------------------------------------------------------------

## Step 4 --- Convert to Canonical Models

Hardware transport output becomes:

``` text
RawSensorReading
GPSPosition
        ↓
HardwareSensorAdapter
        ↓
FieldSample
```

------------------------------------------------------------------------

## Step 5 --- Run Existing Pipeline

Use exactly the existing downstream pipeline.

------------------------------------------------------------------------

## Step 6 --- Compare Virtual and Hardware Behavior

Run both:

``` text
Virtual dataset
Hardware dataset
```

through:

``` text
Validation
Normalization
Intelligence
Spatial
Zones
Recommendations
UI
```

No source-specific downstream branch should be necessary.

------------------------------------------------------------------------

# 18. Future AI Explanation Layer

The AI layer should be introduced only after the deterministic pipeline
and hardware integration are stable.

Input:

``` text
FieldSession
+
FieldIntelligenceResult
+
SpatialFieldResult
+
ZoneDetectionResult
+
RecommendationResult
```

Output:

``` text
Human-readable explanation
```

The AI should not modify deterministic results.

Example:

``` text
Deterministic:
Zone Z03
Status: POOR
Primary issue: nitrogen
Confidence: HIGH
Recommendation:
REVIEW_NITROGEN_MANAGEMENT

AI:
"This part of the field shows lower nitrogen-related soil scores than the
other zones. The system recommends reviewing nitrogen management here."
```

The AI explanation must remain traceable to structured backend data.

------------------------------------------------------------------------

# 19. Future Storage Layer

Storage is intentionally separated from the domain.

Conceptual representation:

``` text
FieldSession
 ├── metadata
 ├── samples[]
 ├── processed result
 ├── spatial result
 ├── zones[]
 └── recommendations[]
```

Future storage should support:

-   save
-   load
-   resume
-   export
-   audit

Storage must not become the owner of intelligence logic.

------------------------------------------------------------------------

# 20. Future UI Evolution

Current UI is an offline HTML/SVG prototype.

Future device UI may use another rendering technology.

The contract remains:

``` text
Backend Results
      ↓
UIFieldView
      ↓
Renderer
```

The renderer may change.

The UI data contract should remain stable unless a deliberate
architecture change is approved.

------------------------------------------------------------------------

# 21. AI Agent Handoff Procedure

When a new AI agent joins the project:

## Give it these documents first

1.  This document
2.  `README.md`
3.  `PROPOSAL_ALIGNMENT.md`
4.  `SPECIFICATION_REGISTER.md`
5.  current architecture/contract documentation
6.  latest sprint report
7.  relevant test files

Then instruct the agent:

``` text
You are joining an existing engineering project.

Do not redesign the architecture.

First inspect the repository and the FieldSense AI Software Workplan & AI Agent Handoff Specification.

Treat frozen contracts as authoritative.

Identify the current phase and sprint.

Do not implement anything until the current task, allowed files, constraints,
tests, and definition of done are understood.

If a requirement is missing or ambiguous, report it instead of guessing.
```

------------------------------------------------------------------------

# 22. How to Start a New Sprint With Any AI Agent

Use this exact sequence:

``` text
1. Upload the master workplan.
2. Upload the latest sprint report.
3. Tell the agent the target sprint.
4. Give the sprint contract.
5. Ask the agent to inspect the repository first.
6. Let the agent implement.
7. Require tests.
8. Require full regression.
9. Require an implementation report.
10. Human reviews.
11. Freeze the sprint.
```

------------------------------------------------------------------------

# 23. Generic Future Sprint Prompt

Use this template with Antigravity, Gemini, Claude, GPT, or another
coding agent.

``` text
You are the implementation agent for FieldSense AI.

Read the attached FieldSense AI Software Workplan & AI Agent Handoff Specification
before modifying the repository.

You are implementing:

SPRINT: <number>
NAME: <name>

OBJECTIVE:
<single objective>

CONTEXT:
<why this sprint exists>

ALLOWED FILES/MODULES:
<list>

FROZEN CONTRACTS:
<list>

INPUTS:
<existing interfaces/models>

REQUIRED BEHAVIOR:
<exact behavior>

CONSTRAINTS:
- Do not redesign architecture.
- Do not modify unrelated modules.
- Do not invent hardware specifications.
- Do not invent agronomic methodology.
- Do not add cloud dependencies.
- Do not add heavy dependencies without approval.
- Do not introduce LLM logic into deterministic calculations.
- Preserve backward compatibility unless explicitly instructed.

TEST REQUIREMENTS:
<tests>

INTEGRATION REQUIREMENTS:
<requirements>

DEFINITION OF DONE:
<checklist>

Before coding:
1. Inspect the repository.
2. Inspect existing tests.
3. Inspect relevant contracts.
4. Identify conflicts or ambiguities.

If a contract must change, STOP and report:
CONTRACT_CHANGE_REQUIRED

After implementation:
1. Run targeted tests.
2. Run the complete regression suite.
3. Report exact test count.
4. Report files created/modified.
5. Report architectural decisions.
6. Report unresolved issues.
7. Report any assumptions.

Do not claim completion without passing tests.
```

------------------------------------------------------------------------

# 24. Sprint Completion Report Template

Every implementation agent should return:

``` text
# FieldSense AI — Phase X / Sprint Y Implementation Report

## 1. Files Created / Modified

...

## 2. What Was Implemented

...

## 3. Architectural Decisions

...

## 4. Tests Added

...

## 5. Targeted Test Result

...

## 6. Full Regression Result

...

## 7. Integration Verification

...

## 8. Issues Found

...

## 9. Ambiguities / Human Approval Required

...

## 10. Hardware Dependencies

...

## 11. Definition of Done

- [x]
- [x]
- [x]

## 12. Recommended Next Sprint

...
```

------------------------------------------------------------------------

# 25. Rules for Scientific / Agronomic Changes

Any change involving:

-   soil-health thresholds
-   nutrient reference bands
-   scoring weights
-   Carbon Readiness methodology
-   agronomic recommendations

must be treated differently from ordinary software changes.

The AI agent must distinguish:

``` text
SOFTWARE IMPLEMENTATION
```

from:

``` text
SCIENTIFIC METHODOLOGY DECISION
```

A coding agent may implement an approved formula.

It must not independently decide that the formula is scientifically
valid.

Use:

``` text
PROTOTYPE_ONLY
AGRONOMIC_VALIDATION_REQUIRED
```

until validated.

------------------------------------------------------------------------

# 26. Rules for Hardware Changes

Hardware changes require coordination with Hardware Engineering.

The software agent must never infer physical details from generic
internet examples when project-specific hardware details are unknown.

Required process:

``` text
Hardware Team
     ↓
Confirmed Specification
     ↓
Software Contract
     ↓
Implementation
     ↓
Hardware Test
```

------------------------------------------------------------------------

# 27. Release Gates

A phase cannot be declared complete merely because code exists.

## Sprint Release Gate

Required:

``` text
Contract implemented
+
Targeted tests passing
+
Full regression passing
+
No unresolved critical defects
+
Architecture review complete
```

## Phase Release Gate

Required:

``` text
All sprint gates passed
+
End-to-end pipeline verified
+
Known limitations documented
+
Hardware dependencies documented
+
Proposal alignment checked
+
Regression suite passing
+
Release decision recorded
```

------------------------------------------------------------------------

# 28. What Must Never Be Lost During Handover

A future engineer must preserve these principles:

### 1. FieldSample is the canonical boundary.

### 2. Virtual and hardware sources use the same downstream pipeline.

### 3. Deterministic intelligence owns calculations.

### 4. AI does not invent deterministic results.

### 5. UI does not calculate intelligence.

### 6. Rejected samples are preserved for auditability but excluded from downstream intelligence.

### 7. Prototype agronomic methodology must not be presented as validated truth.

### 8. Carbon Readiness is decision-support only with limited evidence.

### 9. Hardware specifications must never be guessed.

### 10. Offline operation is a core requirement.

### 11. Heavy dependencies require explicit approval.

### 12. Every sprint is bounded, tested, reviewed, and frozen.

------------------------------------------------------------------------

# 29. Project Continuation Checklist

When taking over FieldSense AI:

``` text
[ ] Read this workplan
[ ] Read project proposal
[ ] Inspect repository
[ ] Run full test suite
[ ] Verify current regression count
[ ] Read latest sprint report
[ ] Inspect SPECIFICATION_REGISTER.md
[ ] Inspect PROPOSAL_ALIGNMENT.md
[ ] Identify current phase
[ ] Identify current sprint
[ ] Confirm frozen contracts
[ ] Confirm unresolved hardware specifications
[ ] Do not modify architecture without review
```

Then continue using the sprint workflow.

------------------------------------------------------------------------

# 30. Current Handoff State

At the time this document was created:

``` text
PROJECT
FieldSense AI

PHASE
Phase 1 — Software Architecture & Intelligence

STATUS
PHASE_1_RELEASE_READY

TESTS
105 passed

ARCHITECTURE
v0.1 frozen

DATA SOURCE
Virtual + hardware abstraction ready

HARDWARE
Pending physical integration

AGRONOMIC VALIDATION
Pending regional validation

UNO Q PHYSICAL BENCHMARK
Pending hardware

NEXT MAJOR PHASE
Phase 2 — Physical Hardware Integration
```

------------------------------------------------------------------------

# 31. Final Engineering Principle

FieldSense should be developed as a system of **stable contracts**, not
as a collection of AI-generated files.

The development philosophy is:

``` text
Understand
   ↓
Define Contract
   ↓
Bound the Sprint
   ↓
Implement
   ↓
Test
   ↓
Audit
   ↓
Freeze
   ↓
Continue
```

The AI coding agent is an implementation tool.

The architecture remains human-controlled.

The software should be understandable by a new engineer even if the
original developers and AI agents are no longer available.

That is the standard this workplan is designed to preserve.

------------------------------------------------------------------------

## Appendix A --- One-Page Mental Model

``` text
                         FIELDSENSE AI
                              │
                              ▼
                     ┌─────────────────┐
                     │  Sensor Source  │
                     └────────┬────────┘
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
             Virtual Sensor          Real Hardware
                  │                       │
                  └───────────┬───────────┘
                              ▼
                         FieldSample
                              │
                              ▼
                         Validation
                              │
                              ▼
                        Normalization
                              │
                              ▼
                  Deterministic Intelligence
                              │
                              ▼
                      Spatial Processing
                              │
                              ▼
                       Zone Detection
                              │
                              ▼
                    Recommendation Rules
                              │
                              ▼
                         UI Contract
                              │
                              ▼
                       Offline UI
                              │
                              ▼
                    Optional AI Explanation
```

The single most important idea:

> **Different sensors, same FieldSample, same deterministic pipeline.**

------------------------------------------------------------------------

## Appendix B --- Agent Safety Summary

Before every implementation, ask:

``` text
WHAT IS THE CONTRACT?
WHAT FILES MAY I CHANGE?
WHAT MUST I NOT CHANGE?
WHAT INPUT DO I RECEIVE?
WHAT OUTPUT MUST I PRODUCE?
HOW WILL I TEST IT?
WHAT PROVES I AM DONE?
```

If the agent cannot answer those questions, the sprint is not
sufficiently specified.

------------------------------------------------------------------------

## Appendix C --- Change Control

Any change to a frozen contract must include:

``` text
Change ID
Current behavior
Proposed behavior
Reason
Affected modules
Backward compatibility impact
Migration requirement
Tests affected
Human approval
Decision
```

Architecture changes must never be hidden inside an ordinary
implementation sprint.

------------------------------------------------------------------------

**End of FieldSense AI Software Workplan & AI Agent Handoff
Specification**
