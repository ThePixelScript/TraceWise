# TraceWise Software Maintenance & Code Investigation Task Catalogue

**Catalogue Version:** 1.0.0  
**Release Date:** October 20, 2026  
**Auditor / Task Architect:** TraceWise Research & Evaluation Team  
**Base Commit Reference:** `102721a6a5fd280132d6647316041a14f3ac6031`  
**Target Branch:** `research/dataset_audit`  
**Intended Consumers:** Evaluation Protocol Team (`research/evaluation_protocol`), Instrumentation Team (`feature/evaluation_instrumentation`)

---

## 1. Introduction & Methodological Framework

### 1.1 Objective & Human-in-the-Loop Context
While offline Information Retrieval metrics (MAP, MRR, P@k, R@k) measure ranking quality over static datasets, they do not directly evaluate developer productivity, verification latency, cognitive load, or maintenance accuracy. Under the TraceWise evaluation roadmap, **Milestone B6** conducts controlled empirical user studies with software developers performing realistic software engineering tasks using the TraceWise Dashboard.

This catalogue defines **nine source-verified software maintenance and code investigation tasks** across three independent datasets:
1. **Synthetic `sample_project`** (Python microservice architecture)
2. **`iTrust`** (Java Enterprise EHR healthcare management)
3. **`eTour`** (Java distributed client-server tourist guide)

### 1.2 Dashboard Integration & Server-Side Ground-Truth Isolation
Tasks are designed to be performed within the TraceWise web dashboard (`python -m tracewise.dashboard`). To prevent evaluation leakage and maintain ecological validity:
1. **Server-Side Developer-Only Mode (`--developer-only`):**
   - When launched with `--developer-only`, `TraceWiseService` strictly withholds ground-truth links (`num_ground_truth_links = None`), match indicators (`is_gold_link = None`), and gold-standard annotations from all API responses (`/api/projects`, `/api/projects/{id}/requirements`, `/api/projects/{id}/requirements/{req_id}/candidates`).
   - Participants see candidate source code chunks ordered by the selected retrieval method (B0–B5), complete with lexical/semantic transparency telemetry, but must evaluate hypotheses independently.
2. **Review Persistence & Audit Instrumentation (`src/tracewise/dashboard/reviews.py`):**
   - As participants inspect candidates, their decisions (`accepted`, `rejected`, `needs_review`) and accompanying rationale strings are recorded persistently in SQLite (`data/reviews/reviews.db`).
   - The instrumentation layer logs timestamps, revision counts, and navigation telemetry to evaluate participant speed and accuracy against the source-verified answer keys defined below.

---

## 2. Task Taxonomy & Catalogue Summary

The catalogue spans three core software engineering maintenance categories:
- **Category A: Link Recovery & Verification** — Evaluating whether candidate code artifacts implement a target functional requirement and rejecting lexical/semantic distractors.
- **Category B: Requirement Change Impact Analysis (CIA)** — Tracing how a proposed requirement modification propagates downstream to implementing classes, helper DAOs, and automated tests.
- **Category C: Defect & Security Investigation** — Diagnosing security vulnerabilities, access control bypasses, or race conditions by identifying all participating artifacts.

### 2.1 Master Task Matrix

| Task ID | Dataset | Category | Difficulty | Target Duration | Target Requirement(s) | Primary Code Artifacts |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **`TW-TASK-01`** | `sample_project` | Link Recovery & Verification | Easy | 10 min | `REQ-001`, `REQ-002` | `src/auth/service.py`, `src/auth/password.py` |
| **`TW-TASK-02`** | `sample_project` | Change Impact Analysis | Medium | 12 min | `REQ-003` (CHANGE-001) | `src/auth/service.py`, `tests/test_authentication.py` |
| **`TW-TASK-03`** | `sample_project` | Defect/Security Investigation | Hard | 15 min | `REQ-010` (Rate Limiting) | `src/security/rate_limiter.py`, `src/auth/service.py` |
| **`TW-TASK-04`** | `iTrust` | Link Recovery & Verification | Easy | 10 min | `UC13` (Patient Representative) | `EditRepresentativesAction`, `AuthDAO`, `PatientDAO` |
| **`TW-TASK-05`** | `iTrust` | Change Impact Analysis | Medium | 12 min | `UC11S1`, `UC11S2` (Prescription) | `EditOfficeVisitAction`, `OfficeVisitDAO`, `AllergyDAO` |
| **`TW-TASK-06`** | `iTrust` | Defect/Security Investigation | Hard | 15 min | `UC10S1`, `UC10E1` (PHR Access) | `AuthDAO`, `EditPHRAction`, `HealthRecordsDAO`, `PersonnelDAO` |
| **`TW-TASK-07`** | `eTour` | Link Recovery & Verification | Easy | 10 min | `UC1` (Delete Cultural Site) | `CulturalHeritage`, `CulturalHeritageAgencyManager`, `DBCulturalHeritage` |
| **`TW-TASK-08`** | `eTour` | Change Impact Analysis | Medium | 12 min | `UC13`, `UC16` (Tourist Account) | `TouristAgencyManager`, `DBTourist`, `BeanTourist` |
| **`TW-TASK-09`** | `eTour` | Defect/Security Investigation | Hard | 15 min | `UC17`, `UC18` (Banner Security) | `AdvertisementAgencyManager`, `AdvertisementManager`, `DBBanner`, `BeanBanner` |

---

## 3. Comprehensive Task Specifications & Source-Verified Answer Keys

### Task 1: `TW-TASK-01` (Synthetic Baseline)
* **Dataset:** `sample_project`
* **Category:** Link Recovery & Verification
* **Difficulty:** Easy | **Target Duration:** 10 minutes
* **Target Requirements:** `REQ-001` (User authentication via email and password) and `REQ-002` (Reject invalid credentials)

#### 1. Participant Scenario & Prompt
> *"A new backend developer has joined the team and needs to locate where user credential verification is implemented. Using the TraceWise Dashboard, inspect the candidate artifacts retrieved for requirements REQ-001 and REQ-002. Identify which source-code methods directly implement email/password verification and which candidate artifacts are irrelevant distractors. Record your verification decisions ('accepted' vs. 'rejected') with technical rationales in the dashboard."*

#### 2. Required Participant Outputs
1. Identify all primary implementing source code functions and classes.
2. Formally accept true positive candidates and reject false positive distractors.
3. Distinguish authentication verification logic from user profile lookup utilities.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Artifacts:**
  - `src/auth/service.py#AuthenticationService.authenticate_user` (Lines 43–93): Performs credential verification against user store and manages audit/lockout flows (ground-truth link for `REQ-001` and `REQ-002`).
  - `src/auth/password.py#verify_password` (Lines 20–30): Cryptographically verifies plaintext password against stored SHA-256 hash (ground-truth link for `REQ-002`).
* **Supporting Data Model Note (`AuthenticationResult`):**
  - `src/auth/service.py#AuthenticationResult` (Lines 13–27): Encapsulates authentication outcome, status code, and token.  
  *(Evaluator Clarification: In `data/fixtures/sample_project/trace_links.json`, only `AuthenticationService.authenticate_user` [REQ-001, REQ-002] and `verify_password` [REQ-002] are formal gold-standard trace links. `AuthenticationResult` is the return dataclass for `authenticate_user`. While identifying it indicates comprehensive code comprehension, it is technically excluded from the formal gold-standard link count in automated IR metrics.)*
* **Source Code Evidence:**
  - `src/auth/service.py:61-62`: Retrieves user dictionary by email key (`user = self._user_store.get(email)`).
  - `src/auth/service.py:74`: Invocates `verify_password(password, stored_hash)` to validate credentials.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `src/users/service.py#UserService.find_user_by_email`: Overlaps lexically on "user" and "email", but only returns profile dictionary without credential verification.
  - `src/users/service.py#UserService.list_user_ids`: High lexical overlap on "user", but is an administrative reporting helper.

---

### Task 2: `TW-TASK-02` (Synthetic Baseline)
* **Dataset:** `sample_project`
* **Category:** Requirement Change Impact Analysis (CIA)
* **Difficulty:** Medium | **Target Duration:** 12 minutes
* **Target Scenario:** Change Scenario `CHANGE-001` (Modifying REQ-003)

#### 1. Participant Scenario & Prompt
> *"Security governance requires standardizing API error codes. Under Change Scenario CHANGE-001, authentication failure responses must transition from HTTP 401 Unauthorized to HTTP 403 Forbidden. Using TraceWise, investigate requirement REQ-003 and determine: (1) every source code file and constant requiring code changes, and (2) every downstream test function impacted that will fail if the change is applied."*

#### 2. Required Participant Outputs
1. Exact constant definitions and return expressions requiring modification in `src/`.
2. Exact test function names and file locations requiring test assertion updates in `tests/`.
3. Impacted requirement IDs that must be revised in documentation.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Direct Modification Points:**
  - `src/auth/service.py:10`: Constant `HTTP_401_UNAUTHORIZED = 401` must be changed or replaced with `HTTP_403_FORBIDDEN = 403`.
  - `src/auth/service.py:56, 68, 80`: Return statements in `authenticate_user` constructing `AuthenticationResult(..., status_code=HTTP_401_UNAUTHORIZED)`.
* **Verified Downstream Impacted Test Artifacts:**
  - `tests/test_authentication.py#test_invalid_password_returns_401`: Asserts `result.status_code == 401`.
  - `tests/test_authentication.py#test_unknown_user_returns_401`: Asserts `result.status_code == 401`.
  - `tests/test_authentication.py#test_rate_limited_user_is_blocked`: Asserts `result.status_code == 401` upon account lockout.
* **Impacted Requirements:**
  - `REQ-003.md`: Specification titled *"HTTP 401 for failed authentication"* must be re-titled and updated to HTTP 403.
* **Common Retrieval Distractors (False Positives):**
  - `src/users/service.py#UserService.get_user_profile`: Returns `None` on missing user; does not use HTTP status codes.
  - `src/auth/token.py#is_token_expired`: Returns boolean; does not participate in HTTP response status generation.

---

### Task 3: `TW-TASK-03` (Synthetic Baseline)
* **Dataset:** `sample_project`
* **Category:** Defect & Security Investigation
* **Difficulty:** Hard | **Target Duration:** 15 minutes
* **Target Requirement:** `REQ-010` (Rate limiting failed login attempts)

#### 1. Participant Scenario & Prompt
> *"Security operations reports that an attacker was able to brute-force a user account without triggering a permanent lockout. Inspect the candidate artifacts linked to REQ-010 in TraceWise. Trace the interaction between the authentication service and the rate limiter. Identify the architectural defect in how lockout expiration is handled and determine all participating methods."*

#### 2. Required Participant Outputs
1. Identify all source code artifacts participating in rate limiting.
2. Pinpoint the exact line and method where lockout state is conditionally reset.
3. Formulate the concrete security vulnerability (automatic state reset on query vs. enforced administrative cooldown).

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Participating Artifacts:**
  - `src/security/rate_limiter.py#RateLimiter.is_blocked` (Lines 43–60)
  - `src/security/rate_limiter.py#RateLimiter.record_failure` (Lines 32–42)
  - `src/security/rate_limiter.py#RateLimiter.reset` (Lines 61–67)
  - `src/auth/service.py#AuthenticationService.authenticate_user` (Lines 51–58, 64–65, 76–77, 90–91)
* **Source Code Evidence & Root Cause:**
  - `src/security/rate_limiter.py:54-58`: In `is_blocked()`, when `elapsed >= self._lockout_seconds`, the method invokes `self.reset(email)` and returns `False`.
  - *Vulnerability Root Cause:* Calling `reset(email)` completely clears the failure count (`self._attempts.pop(email, None)`). After the 300-second lockout expires, the attacker receives a fresh quota of 5 attempts rather than locking out on the very next failure.
* **Common Retrieval Distractors:**
  - `src/auth/token.py#DEFAULT_EXPIRY_SECONDS`: Controls access token lifetime (3600s), unrelated to rate limit lockout (300s).
  - `src/auth/password.py#hash_password`: Generates salt and hash, contains no attempt tracking.

---

### Task 4: `TW-TASK-04` (iTrust EHR Benchmark)
* **Dataset:** `iTrust`
* **Category:** Link Recovery & Verification
* **Difficulty:** Easy | **Target Duration:** 10 minutes
* **Target Requirement:** `UC13` (A patient's DLHCP chooses to add or delete a patient's personal representative)

#### 1. Participant Scenario & Prompt
> *"In the iTrust EHR system, clinical healthcare professionals must designate patient representatives. Use TraceWise to inspect candidate classes retrieved for use case UC13. Determine which Java classes implement representative designation, and reject classes that represent general hospital staff or generic patient demographic editing."*

#### 2. Required Participant Outputs
1. Identify all primary Java classes implementing representative declaration.
2. Accept true positive classes in the TraceWise dashboard with supporting rationale.
3. Reject false positive classes with specific justification of their actual functional roles.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (True Positives):**
  - `EditRepresentativesAction` (`data/benchmarks/itrust/CC/EditRepresentativesAction.java`, 104 lines): Action controller handling `addRepresentative(String pidString)` and `removeRepresentative(String input)`.
  - `AuthDAO` (`data/benchmarks/itrust/CC/AuthDAO.java`): Validates user role to ensure the representee is a valid registered patient (`authDAO.getUserRole(representee) != Role.PATIENT`).
  - `PatientDAO` (`data/benchmarks/itrust/CC/PatientDAO.java`): Executes database mutations `patientDAO.addRepresentative(pid, representee)` and `patientDAO.removeRepresentative(pid, representee)`.
* **Source Code Evidence:**
  - `EditRepresentativesAction.java:65-73`: Verifies role via `AuthDAO`, delegates persistence to `PatientDAO`, and logs audit trail via `TransactionDAO`.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `PersonnelDAO`: High lexical match on "personnel" and "representative", but manages clinical personnel (doctors, nurses), not patient personal representatives.
  - `EditPersonnelAction`: Modifies staff credentials, completely unrelated to patient representatives.

---

### Task 5: `TW-TASK-05` (iTrust EHR Benchmark)
* **Dataset:** `iTrust`
* **Category:** Requirement Change Impact Analysis (CIA)
* **Difficulty:** Medium | **Target Duration:** 12 minutes
* **Target Requirements:** `UC11S1` and `UC11S2` (Office Visit Documentation, Prescriptions & Allergy Detection)

#### 1. Participant Scenario & Prompt
> *"Hospital safety protocols require that prescribing a medication to which a patient is allergic must require an explicit physician override note and immediate notification. Trace requirements UC11S1 and UC11S2 in TraceWise. Identify all Java action classes, DAOs, and validation routines that participate in allergy checking and prescription creation."*

#### 2. Required Participant Outputs
1. Identify all classes involved in checking drug allergies and creating prescriptions during office visits.
2. Specify the exact methods where allergy verification occurs.
3. List candidate classes that handle office visit data but are NOT involved in drug prescriptions.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (True Positives):**
  - `EditOfficeVisitAction` (`data/benchmarks/itrust/CC/EditOfficeVisitAction.java`): Implements `isAllergyOnList(String patMID, String ndcode)` (lines 233–253) and `checkAddPrescription(EditOfficeVisitForm form, long ovID)` (lines 288–304).
  - `AllergyDAO` (`data/benchmarks/itrust/CC/AllergyDAO.java`): Queries patient allergies (`allergyDAO.getAllergies(Long.parseLong(patMID))`).
  - `OfficeVisitDAO` (`data/benchmarks/itrust/CC/OfficeVisitDAO.java`): Stores prescription record (`ovDAO.addPrescription(pres)`).
* **Source Code Evidence:**
  - `EditOfficeVisitAction.java:236-247`: Loops through `allergyList`, matches medication description against active patient allergy beans, and builds allergy warning string.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `LabProcedureDAO`: Retrieved due to presence in office visit subactions, but handles laboratory tests, not medication allergies.
  - `HospitalsDAO`: Manages hospital facilities visited by patient.

---

### Task 6: `TW-TASK-06` (iTrust EHR Benchmark)
* **Dataset:** `iTrust`
* **Category:** Defect & Security Investigation
* **Difficulty:** Hard | **Target Duration:** 15 minutes
* **Target Requirements:** `UC10S1` (View Patient Health Records) and `UC10E1` (Invalid Medical ID Access)

#### 1. Participant Scenario & Prompt
> *"A compliance audit revealed potential unauthorized access to Patient Health Records (PHR) when navigating between patient records. Using TraceWise, investigate candidate classes retrieved for both UC10S1 (View Patient Health Records) and UC10E1 (Invalid Medical ID Access). Identify all classes participating in PHR retrieval, patient authorization, and error handling for invalid patient identifiers, and explain how role verification prevents healthcare personnel from accessing unassigned patients."*

#### 2. Required Participant Outputs
1. Identify all ground-truth classes implementing PHR access and invalid medical ID exception handling across UC10S1 and UC10E1.
2. Explain the role of `AuthDAO` and session verification.
3. Identify which DAOs access patient family history vs. personal medical history.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (8 Distinct Classes in Union):**
  - `AuthDAO` (`data/benchmarks/itrust/CC/AuthDAO.java`): Enforces session timeout (`LOGIN_TIMEOUT = 15 * 60 * 1000`) and validates user roles (linked in both `UC10S1` and `UC10E1`).
  - `EditPHRAction` (`data/benchmarks/itrust/CC/EditPHRAction.java`): Main action controller for viewing and editing PHR (`UC10S1`).
  - `HealthRecordsDAO` (`data/benchmarks/itrust/CC/HealthRecordsDAO.java`): Fetches clinical history, height, weight, and blood pressure records (`UC10S1`).
  - `FamilyDAO` (`data/benchmarks/itrust/CC/FamilyDAO.java`): Retrieves family medical history and hereditary conditions (`UC10S1`).
  - `OfficeVisitDAO` (`data/benchmarks/itrust/CC/OfficeVisitDAO.java`): Provides chronological visit history (`UC10S1`).
  - `PersonnelDAO` (`data/benchmarks/itrust/CC/PersonnelDAO.java`): Validates HCP authorization and specialty (`UC10S1`).
  - `EditHealthHistoryAction` (`data/benchmarks/itrust/CC/EditHealthHistoryAction.java`): Manages health history subflows (`UC10S1`).
  - `GetUserNameAction` (`data/benchmarks/itrust/CC/GetUserNameAction.java`): Resolves username for error logging and exception handling (`UC10E1`).

* **Per-Requirement Ground-Truth Breakdown:**
  - **`UC10S1` (7 classes):** `AuthDAO`, `EditHealthHistoryAction`, `EditPHRAction`, `FamilyDAO`, `HealthRecordsDAO`, `OfficeVisitDAO`, `PersonnelDAO`.
  - **`UC10E1` (2 classes):** `AuthDAO`, `GetUserNameAction`.
  - **Union across Task (`UC10S1` $\cup$ `UC10E1`):** 8 distinct classes.

* **Evaluator Clarification on `GetUserNameAction`:**
  - In `UC2JAVA.csv`, `GetUserNameAction` is a verified true positive link for exception flow `UC10E1` (error reporting on invalid medical ID).
  - However, for queries targeting the primary health record viewing scenario `UC10S1`, `GetUserNameAction` is an unlinked distractor. Evaluators must assess `GetUserNameAction` based on whether the participant is inspecting `UC10S1` (where it should be rejected) or `UC10E1` / full task scope (where it is a true positive).

* **Common Retrieval Distractors (False Positives to Reject):**
  - `TransactionDAO`: Logs audit entries, but does not participate in authorization or clinical data extraction.
  - `PatientDAO`: Retrieved via high lexical overlap on "patient", but PHR clinical records are delegated to `HealthRecordsDAO` and `OfficeVisitDAO`.

---

### Task 7: `TW-TASK-07` (eTour Tourism Benchmark)
* **Dataset:** `eTour`
* **Category:** Link Recovery & Verification
* **Difficulty:** Easy | **Target Duration:** 10 minutes
* **Target Requirement:** `UC1` (Delete a cultural object in the system)

#### 1. Participant Scenario & Prompt
> *"The tourism agency requires removing decommissioned cultural heritage sites. Use TraceWise to inspect candidate Java classes for requirement UC1 ('DeleteCulturalHeritage'). Identify the client manager, remote interface, and database persistence classes responsible for deleting a cultural heritage object."*

#### 2. Required Participant Outputs
1. Identify all classes forming the complete vertical deletion slice.
2. Formally accept true positives and reject data transfer objects (DTOs) or tag managers.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (4 True Positives):**
  - `CulturalHeritage` (`data/benchmarks/etour/CC/CulturalHeritage.java`): Client-side presentation and controller.
  - `CulturalHeritageAgencyManager` (`data/benchmarks/etour/CC/CulturalHeritageAgencyManager.java`): Implements `clearCulturalHeritage(int pCulturalHeritageID)` (lines 30–41).
  - `DBCulturalHeritage` (`data/benchmarks/etour/CC/DBCulturalHeritage.java`): Implements SQL deletion query `clearCulturalHeritage(int pIdBene)` (lines 17–28).
  - `IDBCulturalHeritage` (`data/benchmarks/etour/CC/IDBCulturalHeritage.java`): Database access interface.
* **Source Code Evidence:**
  - `CulturalHeritageAgencyManager.java:31-36`: Validates ID via `CulturalHeritageChecker.checkIdCulturalHeritage`, then delegates to `dbbc.clearCulturalHeritage(pCulturalHeritageID)`.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `BeanCulturalHeritage`: Data bean DTO representing attributes; does not implement deletion logic.
  - `TagAgencyManager`: Manages site categorization tags, not site lifecycle deletion.

---

### Task 8: `TW-TASK-08` (eTour Tourism Benchmark)
* **Dataset:** `eTour`
* **Category:** Requirement Change Impact Analysis (CIA)
* **Difficulty:** Medium | **Target Duration:** 12 minutes
* **Target Requirements:** `UC13` (Enable or disable tourist account) and `UC16` (Delete tourist account)

#### 1. Participant Scenario & Prompt
> *"To comply with privacy regulations, tourist account deletion (UC16) must be changed from a hard database DELETE to a soft-deactivation flag transition (aligning with UC13). Using TraceWise, investigate candidate classes for UC13 and UC16. Determine which database repository and manager classes must be modified to unify account disabling and deletion."*

#### 2. Required Participant Outputs
1. Identify all classes participating in tourist activation, deactivation, and deletion.
2. Identify the exact SQL method in the database layer performing hard deletion.
3. Specify the change required in the manager class to redirect deletion to deactivation.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (6 True Positives across UC13 & UC16):**
  - `TouristAgencyManager` (`data/benchmarks/etour/CC/TouristAgencyManager.java`): Implements `activeTourist(int)` (lines 99–134), `disactiveTourist(int)` (lines 137–172), and `delete(int)` (lines 175–196).
  - `DBTourist` (`data/benchmarks/etour/CC/DBTourist.java`): Implements `delete(int pIdTourist)` (lines 20–22) and `modifyTourist(BeanTourist)` (lines 36–38).
  - `IDBTourist` (`data/benchmarks/etour/CC/IDBTourist.java`): Interface defining tourist persistence contracts.
  - `ITouristAgencyManager` (`data/benchmarks/etour/CC/ITouristAgencyManager.java`): Interface defining agency remote methods.
  - `Tourist` (`data/benchmarks/etour/CC/Tourist.java`): Client management facade.
  - `BeanTourist` (`data/benchmarks/etour/CC/BeanTourist.java`): Data model entity representing tourist accounts and account activation status attributes.
* **Per-Requirement Ground-Truth Mapping:**
  - **`UC13` (5 classes):** `ITouristAgencyManager`, `Tourist`, `DBTourist`, `IDBTourist`, `BeanTourist`
  - **`UC16` (4 classes):** `IDBTourist`, `TouristAgencyManager`, `ITouristAgencyManager`, `BeanTourist`
  - **Union (6 unique classes):** `BeanTourist`, `DBTourist`, `IDBTourist`, `ITouristAgencyManager`, `Tourist`, `TouristAgencyManager`
* **Source Code Evidence:**
  - `TouristAgencyManager.java:181`: Currently calls `tourist.delete(pIdTourist)`. Under soft deletion, this must be updated to call `tourist.modifyTourist(toChange)` with `active = false`.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `TouristCommonManager`: Handles profile searches and common lookups; contains no administrative activation/deletion logic.
  - `TouristTableModel`: Swing GUI table model for desktop rendering.

---

### Task 9: `TW-TASK-09` (eTour Tourism Benchmark)
* **Dataset:** `eTour`
* **Category:** Defect & Security Investigation
* **Difficulty:** Hard | **Target Duration:** 15 minutes
* **Target Requirements:** `UC17` (Modify banner ad image) and `UC18` (Check maximum banner quota)

#### 1. Participant Scenario & Prompt
> *"An agency reported that refreshment points are displaying more advertising banners than their contractual maximum quota allows. Use TraceWise to investigate candidate classes for UC17 and UC18. Trace the quota enforcement logic and identify all classes participating in banner count verification and banner image updates."*

#### 2. Required Participant Outputs
1. Identify all ground-truth classes implementing banner modification and quota checks.
2. Pinpoint where banner count validation occurs.
3. Reject distractors that manage physical refreshment points rather than banner advertisements.

#### 3. Source-Verified Answer Key (Evaluator Only)
* **Verified Ground-Truth Classes (13 True Positives across UC17 & UC18):**
  - `AdvertisementAgencyManager` (`data/benchmarks/etour/CC/AdvertisementAgencyManager.java`): Agency-side banner management facade.
  - `AdvertisementManager` (`data/benchmarks/etour/CC/AdvertisementManager.java`): Core advertisement business logic, banner file storage, and quota verification (lines 153–170).
  - `Banner` (`data/benchmarks/etour/CC/Banner.java`): Client-side presentation controller.
  - `BannerNode` (`data/benchmarks/etour/CC/BannerNode.java`): UI tree node representation for banner listings.
  - `BeanBanner` (`data/benchmarks/etour/CC/BeanBanner.java`): Encapsulates banner image path, refreshment point ID, and metadata.
  - `ControlData` (`data/benchmarks/etour/CC/ControlData.java`): Image file and data verification controller (`checkImmagine`).
  - `ControllDataAdvertisement` (`data/benchmarks/etour/CC/ControllDataAdvertisement.java`): Form and input validation controller for advertisements.
  - `DBBanner` (`data/benchmarks/etour/CC/DBBanner.java`): Persistence stub implementing `clearBanner` (lines 13–19), `insertBanner` (lines 21–27), `modifyBanner` (lines 29–31), and `getBanner` (lines 33–51).
  - `ErrorMessage` (`data/benchmarks/etour/CC/ErrorMessage.java`): Quota violation error constants (`ERROR_NUM_BANNER`).
  - `GlobalConstants` (`data/benchmarks/etour/CC/GlobalConstants.java`): System configuration constants (`SERVER_IMAGE_PATH`).
  - `IAdvertisementAgencyManager` (`data/benchmarks/etour/CC/IAdvertisementAgencyManager.java`): Agency remote banner manager interface.
  - `IAdvertisementManager` (`data/benchmarks/etour/CC/IAdvertisementManager.java`): Core advertisement manager interface.
  - `IDBBanner` (`data/benchmarks/etour/CC/IDBBanner.java`): Database persistence contract interface.
* **Per-Requirement Ground-Truth Mapping:**
  - **`UC17` (12 classes):** `AdvertisementAgencyManager`, `AdvertisementManager`, `Banner`, `BannerNode`, `BeanBanner`, `ControlData`, `ControllDataAdvertisement`, `DBBanner`, `GlobalConstants`, `IAdvertisementAgencyManager`, `IAdvertisementManager`, `IDBBanner`
  - **`UC18` (5 classes):** `BeanBanner`, `DBBanner`, `ErrorMessage`, `IAdvertisementManager`, `IDBBanner`
  - **Union (13 unique classes):** `AdvertisementAgencyManager`, `AdvertisementManager`, `Banner`, `BannerNode`, `BeanBanner`, `ControlData`, `ControllDataAdvertisement`, `DBBanner`, `ErrorMessage`, `GlobalConstants`, `IAdvertisementAgencyManager`, `IAdvertisementManager`, `IDBBanner`
* **Source Code Evidence:**
  - In `UC18` (*CheckBannerNumber*, `data/benchmarks/etour/UC/UC18.txt`), banner quota enforcement occurs in `AdvertisementManager.insertBanner(int, ImageIcon)` (`AdvertisementManager.java:163-170`): it queries `dbBanner.getBanner(pIdRefreshmentPoint).size()`, compares against `convention.getMaxBanner()`, and raises `Exception(ErrorMessage.ERROR_NUM_BANNER)` if the quota is exceeded.
* **Common Retrieval Distractors (False Positives to Reject):**
  - `DBRefreshmentPoint`: Manages refreshment point coordinates and opening hours, but does not manage advertisement banners.
  - `RefreshmentPointAgencyManager`: Manages food venue operations, not banner contracts.

---

## 4. Scoring Criteria & Evaluation Rubric

To provide objective, reproducible evaluations aligned with the evaluation protocol and instrumentation specifications, participant performance is evaluated using three complementary dimensions:

### 4.1 Information Retrieval Performance (Candidate Verification Accuracy)
Participant review decisions (`accepted` vs. `rejected`) are mapped against the verified ground-truth answer key:
- **True Positive (TP):** Participant accepted an artifact that belongs to the verified answer key.
- **False Positive (FP):** Participant accepted an artifact that is a distractor (not in the answer key).
- **False Negative (FN):** Participant rejected or omitted an artifact that belongs to the answer key.
- **True Negative (TN):** Participant rejected a candidate distractor.

From these counts, standard IR accuracy metrics are logged:
$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}, \quad \text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}, \quad F_1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$$

### 4.2 Verification Effort & Latency Compatibility
Logged via `ReviewStore` (`src/tracewise/dashboard/reviews.py`) and browser telemetry:
- **Time to First Decision ($T_{\text{first}}$):** Time from task opening to recording the first candidate decision.
- **Total Task Completion Time ($T_{\text{total}}$):** Elapsed time until task submission.
- **Revision Count ($N_{\text{rev}}$):** Number of times decisions were revised (`ReviewDecision.revision_count`).
- **Rationale Quality:** Length and technical precision of the recorded rationale text.

### 4.3 Qualitative Maintenance Completeness Rubric (0–5 Graded Scale)

| Score | Rating | Operational Criteria |
| :---: | :---: | :--- |
| **5** | **Exemplary** | Successfully identified 100% of ground-truth artifacts ($Recall = 1.0$), rejected 100% of distractors ($Precision = 1.0$), correctly identified all downstream test/code modification points, and provided technically rigorous rationale citing exact methods or state changes. |
| **4** | **Strong** | Identified all primary implementing classes ($Recall \ge 0.80$), accepted at most 1 distractor ($Precision \ge 0.75$), correctly identified core downstream change impact, and provided sound rationale. |
| **3** | **Adequate** | Identified the central implementing class but omitted secondary DAOs or helper interfaces ($0.50 \le Recall < 0.80$), or accepted 2 distractors ($0.50 \le Precision < 0.75$). Identified primary change point but missed test impact. |
| **2** | **Partial** | Identified partial keywords but conflated utility classes with core business logic ($Recall < 0.50$, high false positive rate). Failed to locate downstream impact. |
| **1** | **Marginal** | Accepted candidate distractors indiscriminately based on superficial token matches; failed to identify primary implementing files. |
| **0** | **Unsatisfactory** | No meaningful progress made; unreviewed or completely erroneous selections. |

---

## 5. Summary & Hand-Off Checklist

- [x] **Catalogue Balance:** Exactly 9 tasks spanning 3 datasets (`sample_project`, `iTrust`, `eTour`) and 3 maintenance categories.
- [x] **Difficulty Distribution:** 3 Easy (10 min), 3 Medium (12 min), 3 Hard (15 min).
- [x] **Source-Grounded Verification:** Every file path, class stem, method signature, and distractor verified directly against repository source files.
- [x] **Blinding & Privacy Compliance:** Prompts reference requirements and change requests without leaking ground-truth source code paths.
- [x] **Instrumentation Compatibility:** Scored decisions align directly with `ReviewStore` schema (`data/reviews/reviews.db`).
