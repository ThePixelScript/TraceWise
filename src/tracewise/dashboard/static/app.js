/* TraceWise Dashboard V0 Client Application
   Human-centred, accessible, calm interface for requirement traceability inspection.
*/

(function () {
  "use strict";

  // Application State
  const state = {
    activeProjectId: null,
    activeRequirementId: null,
    activeMethodId: "b1_bm25",
    activeTopK: 20,
    mode: "evaluation", // "evaluation" | "developer"
    requirements: [],
    searchQuery: "",
    requirementFilter: "all", // "all" | "evaluable" | "zero"
    isLoadingReqs: false,
    isLoadingCandidates: false,
    isCandidatesRevealed: false, // Progressive disclosure (> 5)
  };

  // DOM Elements Cache
  const elements = {
    modeSelect: document.getElementById("mode-select"),
    projectSelect: document.getElementById("project-select"),
    methodSelect: document.getElementById("method-select"),
    topkSelect: document.getElementById("topk-select"),
    refreshBtn: document.getElementById("refresh-btn"),
    activeModeLabel: document.getElementById("active-mode-label"),

    // Error Alert
    errorBanner: document.getElementById("error-banner"),
    errorTitle: document.getElementById("error-title"),
    errorMessage: document.getElementById("error-message"),
    errorDismissBtn: document.getElementById("error-dismiss-btn"),

    // Sidebar: Requirements
    reqCountBadge: document.getElementById("req-count-badge"),
    reqSearchInput: document.getElementById("req-search-input"),
    clearSearchBtn: document.getElementById("clear-search-btn"),
    filterTabsContainer: document.getElementById("filter-tabs-container"),
    filterTabs: document.querySelectorAll(".filter-tab"),
    reqLoadingIndicator: document.getElementById("req-loading-indicator"),
    reqEmptyState: document.getElementById("req-empty-state"),
    reqEmptyMessage: document.getElementById("req-empty-message"),
    requirementsList: document.getElementById("requirements-list"),

    // Area 2: Requirement Details Card
    requirementDetailCard: document.getElementById("requirement-detail-card"),
    detailReqId: document.getElementById("detail-req-id"),
    detailReqTitle: document.getElementById("detail-req-title"),
    detailReqText: document.getElementById("detail-req-text"),
    detailEvaluableBadge: document.getElementById("detail-evaluable-badge"),
    detailGoldCountBadge: document.getElementById("detail-gold-count-badge"),
    detailGoldLinksSection: document.getElementById("detail-gold-links-section"),
    detailGoldLinksList: document.getElementById("detail-gold-links-list"),

    // Notice Banner
    verificationNotice: document.getElementById("verification-notice"),
    noticeHeading: document.getElementById("notice-heading"),
    noticeBody: document.getElementById("notice-body"),

    // Area 3: Candidates
    candidatesContainer: document.getElementById("candidates-container"),
    candidatesCountSubtitle: document.getElementById("candidates-count-subtitle"),
    telemetryMatched: document.getElementById("telemetry-matched"),
    telemetryTime: document.getElementById("telemetry-time"),
    telemetryCached: document.getElementById("telemetry-cached"),
    methodSummaryNote: document.getElementById("method-summary-note"),
    candidatesLoading: document.getElementById("candidates-loading"),
    candidatesEmpty: document.getElementById("candidates-empty"),
    candidatesList: document.getElementById("candidates-list"),
    revealContainer: document.getElementById("reveal-container"),
    btnRevealCandidates: document.getElementById("btn-reveal-candidates"),
    revealBtnText: document.getElementById("reveal-btn-text"),

    // Welcome State
    welcomeState: document.getElementById("welcome-state"),
  };

  // --- Utility Functions ---

  function showError(title, message) {
    if (!elements.errorBanner) return;
    elements.errorTitle.textContent = title || "Error";
    elements.errorMessage.textContent = message || "An unexpected error occurred.";
    elements.errorBanner.style.display = "flex";
  }

  function hideError() {
    if (elements.errorBanner) {
      elements.errorBanner.style.display = "none";
    }
  }

  async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) {
      let errMsg = `Request failed: ${res.status} ${res.statusText}`;
      try {
        const errJson = await res.json();
        if (errJson && errJson.error) {
          errMsg = errJson.error;
        }
      } catch (_) {
        // Fall back to HTTP status
      }
      throw new Error(errMsg);
    }
    return res.json();
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatTimestamp(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return isoStr;
      return d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch (_) {
      return isoStr;
    }
  }

  // --- Application Initialization ---

  async function init() {
    setupEventListeners();

    try {
      await loadRetrievalMethods();
      await loadProjects();
    } catch (err) {
      showError("Initialization Error", err.message);
    }
  }

  function setupEventListeners() {
    if (elements.errorDismissBtn) {
      elements.errorDismissBtn.addEventListener("click", hideError);
    }

    // Mode Selector change (Evaluation vs Developer Workflow)
    if (elements.modeSelect) {
      elements.modeSelect.addEventListener("change", (e) => {
        hideError();
        state.mode = e.target.value;
        updateModeDisplay();
        loadRequirements();
        if (state.activeRequirementId) {
          loadRequirementDetail(state.activeRequirementId);
          loadCandidates(state.activeRequirementId);
        }
      });
    }

    if (elements.projectSelect) {
      elements.projectSelect.addEventListener("change", (e) => {
        hideError();
        state.activeProjectId = e.target.value;
        state.activeRequirementId = null;
        loadRequirements();
      });
    }

    if (elements.methodSelect) {
      elements.methodSelect.addEventListener("change", (e) => {
        hideError();
        state.activeMethodId = e.target.value;
        if (state.activeRequirementId) {
          loadCandidates(state.activeRequirementId);
        }
      });
    }

    if (elements.topkSelect) {
      elements.topkSelect.addEventListener("change", (e) => {
        hideError();
        state.activeTopK = parseInt(e.target.value, 10) || 20;
        if (state.activeRequirementId) {
          loadCandidates(state.activeRequirementId);
        }
      });
    }

    if (elements.refreshBtn) {
      elements.refreshBtn.addEventListener("click", () => {
        hideError();
        loadRequirements();
        if (state.activeRequirementId) {
          loadRequirementDetail(state.activeRequirementId);
          loadCandidates(state.activeRequirementId);
        }
      });
    }

    if (elements.reqSearchInput) {
      elements.reqSearchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value.trim().toLowerCase();
        if (elements.clearSearchBtn) {
          elements.clearSearchBtn.style.display = state.searchQuery ? "block" : "none";
        }
        renderRequirementsList();
      });
    }

    if (elements.clearSearchBtn) {
      elements.clearSearchBtn.addEventListener("click", () => {
        elements.reqSearchInput.value = "";
        state.searchQuery = "";
        elements.clearSearchBtn.style.display = "none";
        renderRequirementsList();
      });
    }

    if (elements.filterTabs) {
      elements.filterTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
          elements.filterTabs.forEach((t) => {
            t.classList.remove("active");
            t.setAttribute("aria-selected", "false");
          });
          tab.classList.add("active");
          tab.setAttribute("aria-selected", "true");
          state.requirementFilter = tab.getAttribute("data-filter");
          renderRequirementsList();
        });
      });
    }

    // Progressive disclosure button for extra candidates
    if (elements.btnRevealCandidates) {
      elements.btnRevealCandidates.addEventListener("click", () => {
        state.isCandidatesRevealed = !state.isCandidatesRevealed;
        elements.btnRevealCandidates.setAttribute(
          "aria-expanded",
          state.isCandidatesRevealed ? "true" : "false"
        );

        const extraCards = document.querySelectorAll(".candidate-card-extra");
        extraCards.forEach((card) => {
          card.style.display = state.isCandidatesRevealed ? "block" : "none";
        });

        const totalCands = document.querySelectorAll(".candidate-card").length;
        if (state.isCandidatesRevealed) {
          elements.revealBtnText.textContent = "Show fewer candidates (Top 5) ▴";
          if (elements.candidatesCountSubtitle) {
            elements.candidatesCountSubtitle.textContent = `Showing all ${totalCands} candidates retrieved`;
          }
        } else {
          elements.revealBtnText.textContent = `Show ${totalCands - 5} more candidates (5 of ${totalCands} shown) ▾`;
          if (elements.candidatesCountSubtitle) {
            elements.candidatesCountSubtitle.textContent = `Showing top 5 of ${totalCands} candidates retrieved`;
          }
        }
      });
    }
  }

  function updateModeDisplay() {
    const isDev = state.mode === "developer";

    if (elements.activeModeLabel) {
      elements.activeModeLabel.textContent = isDev
        ? "💼 Developer Mode (Blinded)"
        : "🔬 Research Mode";
    }

    // In developer mode, strictly blind filter tabs because ground truth is isolated
    if (elements.filterTabsContainer) {
      if (isDev) {
        elements.filterTabsContainer.style.display = "none";
        state.requirementFilter = "all";
      } else {
        elements.filterTabsContainer.style.display = "flex";
      }
    }

    // Ground-truth isolation: immediately hide ground-truth details in Developer Mode
    if (isDev) {
      if (elements.detailGoldLinksSection) {
        elements.detailGoldLinksSection.style.display = "none";
      }
      if (elements.detailEvaluableBadge) {
        elements.detailEvaluableBadge.style.display = "none";
      }
      if (elements.detailGoldCountBadge) {
        elements.detailGoldCountBadge.style.display = "none";
      }
      if (elements.telemetryMatched) {
        elements.telemetryMatched.style.display = "none";
      }
      // Immediately remove gold badges from DOM upon mode switch
      document.querySelectorAll(".badge-gold-link").forEach((el) => el.remove());
      document.querySelectorAll(".badge-gold-match").forEach((el) => el.remove());
      document.querySelectorAll(".badge-unlinked").forEach((el) => el.remove());
    } else {
      // In Research/Evaluation mode, remove any developer review controls
      document
        .querySelectorAll(
          ".review-action-bar, .review-form-panel, .review-history-panel, .review-confirmed-banner"
        )
        .forEach((el) => el.remove());
    }

    // Informative, calm notice banner update
    if (elements.verificationNotice) {
      if (elements.noticeHeading) {
        elements.noticeHeading.textContent = isDev
          ? "Developer Workflow Mode (Blinded Evaluation)"
          : "Research Mode: Benchmark Ground Truth Comparison";
      }
      if (elements.noticeBody) {
        elements.noticeBody.textContent = isDev
          ? "Showing algorithmic candidates for human audit. Ground-truth benchmark labels are strictly blinded to simulate real-world developer verification."
          : "Comparing algorithmic candidate hypotheses against official benchmark gold-standard trace links.";
      }
    }
  }

  // --- Data Loading Functions ---

  async function loadRetrievalMethods() {
    try {
      const methods = await fetchJson("/api/retrieval-methods");
      if (elements.methodSelect) {
        elements.methodSelect.innerHTML = "";
        methods.forEach((m) => {
          const opt = document.createElement("option");
          opt.value = m.id;
          opt.textContent = `${m.name} (${m.retriever_type})`;
          if (m.id === state.activeMethodId) {
            opt.selected = true;
          }
          elements.methodSelect.appendChild(opt);
        });
      }
    } catch (err) {
      showError("Failed to load retrieval baselines", err.message);
    }
  }

  async function loadProjects() {
    try {
      const projects = await fetchJson("/api/projects");
      if (!projects || projects.length === 0) {
        showError("No Projects", "No benchmark projects found in repository.");
        return;
      }

      if (elements.projectSelect) {
        elements.projectSelect.innerHTML = "";
        projects.forEach((p) => {
          const opt = document.createElement("option");
          opt.value = p.project_id;
          opt.textContent = `${p.project_name} (${p.num_requirements} reqs, ${p.num_source_chunks} chunks)`;
          elements.projectSelect.appendChild(opt);
        });

        // Default to sample_project or first
        const defaultProj =
          projects.find((p) => p.project_id === "sample_project") || projects[0];
        state.activeProjectId = defaultProj.project_id;
        elements.projectSelect.value = state.activeProjectId;
      }

      await loadRequirements();
    } catch (err) {
      showError("Failed to load projects", err.message);
    }
  }

  async function loadRequirements() {
    if (!state.activeProjectId) return;

    state.isLoadingReqs = true;
    if (elements.reqLoadingIndicator) {
      elements.reqLoadingIndicator.style.display = "flex";
    }

    try {
      const reqs = await fetchJson(
        `/api/projects/${state.activeProjectId}/requirements?mode=${encodeURIComponent(state.mode)}`
      );
      state.requirements = reqs;

      renderRequirementsList();

      // Automatically select the first requirement if none active
      if (
        !state.activeRequirementId ||
        !reqs.some((r) => r.requirement_id === state.activeRequirementId)
      ) {
        const firstReq =
          state.mode === "developer"
            ? reqs[0]
            : reqs.find((r) => r.is_evaluable) || reqs[0];
        if (firstReq) {
          selectRequirement(firstReq.requirement_id);
        }
      }
    } catch (err) {
      showError("Failed to load requirements", err.message);
    } finally {
      state.isLoadingReqs = false;
      if (elements.reqLoadingIndicator) {
        elements.reqLoadingIndicator.style.display = "none";
      }
    }
  }

  function renderRequirementsList() {
    if (!elements.requirementsList) return;
    elements.requirementsList.innerHTML = "";
    const isDev = state.mode === "developer";

    const filtered = state.requirements.filter((req) => {
      // In developer mode, ignore gold-based filter tabs
      if (!isDev) {
        if (state.requirementFilter === "evaluable" && !req.is_evaluable) {
          return false;
        }
        if (state.requirementFilter === "zero" && req.is_evaluable) {
          return false;
        }
      }

      // Filter by search query
      if (state.searchQuery) {
        const idMatch = req.requirement_id.toLowerCase().includes(state.searchQuery);
        const titleMatch = (req.title || "").toLowerCase().includes(state.searchQuery);
        if (!idMatch && !titleMatch) return false;
      }

      return true;
    });

    if (elements.reqCountBadge) {
      elements.reqCountBadge.textContent = filtered.length;
    }

    if (filtered.length === 0) {
      if (elements.reqEmptyState) {
        elements.reqEmptyState.style.display = "flex";
      }
      if (elements.reqEmptyMessage && state.searchQuery) {
        elements.reqEmptyMessage.textContent = `No requirements match "${state.searchQuery}". Try a different keyword or clear the search.`;
      }
      return;
    }

    if (elements.reqEmptyState) {
      elements.reqEmptyState.style.display = "none";
    }

    filtered.forEach((req) => {
      const li = document.createElement("li");
      const isActive = req.requirement_id === state.activeRequirementId;
      li.className = `req-item ${isActive ? "active" : ""}`;
      li.setAttribute("data-id", req.requirement_id);
      li.setAttribute("role", "option");
      li.setAttribute("tabindex", "0");
      li.setAttribute("aria-selected", isActive ? "true" : "false");

      const headerDiv = document.createElement("div");
      headerDiv.className = "req-item-header";

      const idPill = document.createElement("span");
      idPill.className = "req-item-id";
      idPill.textContent = req.requirement_id;
      headerDiv.appendChild(idPill);

      // In Research Mode ONLY: Show subtle badge for evaluable vs zero-link
      if (!isDev && req.is_evaluable !== null && req.is_evaluable !== undefined) {
        const goldBadge = document.createElement("span");
        if (req.is_evaluable) {
          goldBadge.className = "badge badge-subtle badge-success badge-gold-link";
          goldBadge.textContent = `${req.gold_link_count} Gold`;
        } else {
          goldBadge.className = "badge badge-subtle badge-muted";
          goldBadge.textContent = "0 Gold";
        }
        headerDiv.appendChild(goldBadge);
      }

      li.appendChild(headerDiv);

      const titleDiv = document.createElement("div");
      titleDiv.className = "req-item-title";
      titleDiv.textContent = req.title || req.requirement_id;
      titleDiv.title = req.title || req.requirement_id;
      li.appendChild(titleDiv);

      // Mouse & Keyboard Selection
      li.addEventListener("click", () => {
        selectRequirement(req.requirement_id);
      });

      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectRequirement(req.requirement_id);
        }
      });

      elements.requirementsList.appendChild(li);
    });
  }

  async function selectRequirement(requirementId) {
    state.activeRequirementId = requirementId;

    document.querySelectorAll(".req-item").forEach((item) => {
      if (item.getAttribute("data-id") === requirementId) {
        item.classList.add("active");
        item.setAttribute("aria-selected", "true");
        item.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else {
        item.classList.remove("active");
        item.setAttribute("aria-selected", "false");
      }
    });

    if (elements.welcomeState) {
      elements.welcomeState.style.display = "none";
    }
    if (elements.requirementDetailCard) {
      elements.requirementDetailCard.style.display = "block";
    }
    if (elements.verificationNotice) {
      elements.verificationNotice.style.display = "flex";
    }
    if (elements.candidatesContainer) {
      elements.candidatesContainer.style.display = "flex";
    }

    await Promise.all([
      loadRequirementDetail(requirementId),
      loadCandidates(requirementId),
    ]);
  }

  async function loadRequirementDetail(requirementId) {
    try {
      const detail = await fetchJson(
        `/api/projects/${state.activeProjectId}/requirements/${encodeURIComponent(requirementId)}?mode=${encodeURIComponent(state.mode)}`
      );

      // Discard response if another requirement became active in the meantime
      if (state.activeRequirementId !== requirementId) {
        return;
      }

      elements.detailReqId.textContent = detail.requirement_id;
      elements.detailReqTitle.textContent = detail.title || detail.requirement_id;
      elements.detailReqText.textContent = detail.text;

      const isDev = state.mode === "developer";

      if (isDev || detail.gold_links === null) {
        // Ground truth strictly blinded in Developer Mode
        if (elements.detailEvaluableBadge) {
          elements.detailEvaluableBadge.style.display = "none";
        }
        if (elements.detailGoldCountBadge) {
          elements.detailGoldCountBadge.style.display = "none";
        }
        if (elements.detailGoldLinksSection) {
          elements.detailGoldLinksSection.style.display = "none";
        }
      } else {
        // Research/Evaluation mode
        if (elements.detailEvaluableBadge) {
          elements.detailEvaluableBadge.style.display = "inline-block";
          if (detail.is_evaluable) {
            elements.detailEvaluableBadge.className = "badge badge-subtle badge-success";
            elements.detailEvaluableBadge.textContent = "Evaluable Query";
          } else {
            elements.detailEvaluableBadge.className = "badge badge-subtle badge-muted";
            elements.detailEvaluableBadge.textContent = "Zero-Link Query";
          }
        }

        if (elements.detailGoldCountBadge) {
          elements.detailGoldCountBadge.style.display = "inline-block";
          elements.detailGoldCountBadge.textContent = `${detail.gold_link_count} Gold Links`;
        }

        if (elements.detailGoldLinksList) {
          elements.detailGoldLinksList.innerHTML = "";
          if (detail.gold_links && detail.gold_links.length > 0) {
            elements.detailGoldLinksSection.style.display = "block";
            detail.gold_links.forEach((goldTarget) => {
              const chip = document.createElement("span");
              chip.className = "gold-link-chip";
              chip.textContent = goldTarget;
              elements.detailGoldLinksList.appendChild(chip);
            });
          } else {
            elements.detailGoldLinksSection.style.display = "none";
          }
        }
      }
    } catch (err) {
      showError("Failed to load requirement details", err.message);
    }
  }

  // --- Candidate Hypotheses Logic (Progressive Disclosure & Collapsed Previews) ---

  async function loadCandidates(requirementId) {
    state.isLoadingCandidates = true;
    state.isCandidatesRevealed = false; // Reset disclosure state on new query
    if (elements.candidatesLoading) {
      elements.candidatesLoading.style.display = "flex";
    }
    if (elements.candidatesList) {
      elements.candidatesList.innerHTML = "";
    }
    if (elements.candidatesEmpty) {
      elements.candidatesEmpty.style.display = "none";
    }
    if (elements.revealContainer) {
      elements.revealContainer.style.display = "none";
    }

    try {
      const url = `/api/projects/${state.activeProjectId}/requirements/${encodeURIComponent(requirementId)}/candidates?method=${encodeURIComponent(state.activeMethodId)}&top_k=${state.activeTopK}&mode=${encodeURIComponent(state.mode)}`;
      const data = await fetchJson(url);

      // Discard responses from stale/superseded queries if user switched requirement
      if (state.activeRequirementId !== requirementId) {
        return;
      }

      const isDev = state.mode === "developer";

      // Telemetry indicators
      if (isDev || data.gold_links_retrieved === null) {
        if (elements.telemetryMatched) {
          elements.telemetryMatched.style.display = "none";
        }
      } else {
        if (elements.telemetryMatched) {
          elements.telemetryMatched.style.display = "inline-block";
          elements.telemetryMatched.textContent = `${data.gold_links_retrieved} / ${data.total_gold_links} Gold Retrieved`;
        }
      }

      const timeMs = (data.retrieval_time_sec * 1000).toFixed(1);
      if (elements.telemetryTime) {
        elements.telemetryTime.textContent = `${timeMs} ms`;
      }

      if (elements.telemetryCached) {
        elements.telemetryCached.style.display = data.is_cached ? "inline-block" : "none";
      }

      if (elements.methodSummaryNote) {
        elements.methodSummaryNote.textContent = `Active Retrieval Method: ${data.method_name}`;
      }

      renderCandidatesList(data.candidates);
    } catch (err) {
      showError("Failed to retrieve candidate hypotheses", err.message);
      if (elements.candidatesEmpty) {
        elements.candidatesEmpty.style.display = "flex";
      }
    } finally {
      state.isLoadingCandidates = false;
      if (elements.candidatesLoading) {
        elements.candidatesLoading.style.display = "none";
      }
    }
  }

  function renderCandidatesList(candidates) {
    if (!elements.candidatesList) return;
    elements.candidatesList.innerHTML = "";
    const isDev = state.mode === "developer";

    if (!candidates || candidates.length === 0) {
      if (elements.candidatesEmpty) {
        elements.candidatesEmpty.style.display = "flex";
      }
      if (elements.candidatesCountSubtitle) {
        elements.candidatesCountSubtitle.textContent = "0 candidates found";
      }
      return;
    }

    if (elements.candidatesEmpty) {
      elements.candidatesEmpty.style.display = "none";
    }

    // Subtitle indicator
    if (elements.candidatesCountSubtitle) {
      if (candidates.length > 5) {
        elements.candidatesCountSubtitle.textContent = `Showing top 5 of ${candidates.length} candidates retrieved`;
      } else {
        elements.candidatesCountSubtitle.textContent = `Showing all ${candidates.length} candidates retrieved`;
      }
    }

    candidates.forEach((cand, idx) => {
      const card = document.createElement("article");
      const isGoldMatch = !isDev && cand.is_gold_link === true;
      const isExtra = idx >= 5;

      card.className = `candidate-card ${isGoldMatch ? "matched-gold" : ""} ${isExtra ? "candidate-card-extra" : ""}`;
      card.setAttribute("data-rank", cand.rank);

      // Extra candidates are collapsed initially (Requirement 4)
      if (isExtra && !state.isCandidatesRevealed) {
        card.style.display = "none";
      }

      // Card Header
      const header = document.createElement("div");
      header.className = "candidate-card-header";

      const idGroup = document.createElement("div");
      idGroup.className = "candidate-id-group";

      const rankPill = document.createElement("div");
      rankPill.className = "rank-pill";
      rankPill.textContent = `#${cand.rank}`;

      const targetIdSpan = document.createElement("div");
      targetIdSpan.className = "candidate-target-id";
      targetIdSpan.textContent = cand.target_id;
      targetIdSpan.title = cand.target_id;

      idGroup.appendChild(rankPill);
      idGroup.appendChild(targetIdSpan);

      const badgeGroup = document.createElement("div");
      badgeGroup.className = "candidate-badge-group";

      // Score badge
      const scoreBadge = document.createElement("span");
      scoreBadge.className = "score-badge";
      const scoreFormatted =
        typeof cand.score === "number" ? cand.score.toFixed(3) : cand.score;
      scoreBadge.textContent = `Score: ${scoreFormatted}`;
      badgeGroup.appendChild(scoreBadge);

      // In Research/Evaluation Mode ONLY: Render benchmark ground-truth status
      if (!isDev && cand.is_gold_link !== null && cand.is_gold_link !== undefined) {
        const goldBadge = document.createElement("span");
        if (cand.is_gold_link) {
          goldBadge.className = "badge-gold-match";
          goldBadge.textContent = "✓ Benchmark Gold Link";
        } else {
          goldBadge.className = "badge-unlinked";
          goldBadge.textContent = "Retrieved Candidate";
        }
        badgeGroup.appendChild(goldBadge);
      }

      // Verification Status Badge
      const verifBadge = document.createElement("span");
      verifBadge.className = "badge-verification-status";
      if (isDev) {
        const devStatus = cand.developer_verification_status || "unverified";
        if (devStatus === "accepted") {
          verifBadge.className = "badge-verification-status status-accepted";
          verifBadge.textContent = "✓ Accepted";
        } else if (devStatus === "rejected") {
          verifBadge.className = "badge-verification-status status-rejected";
          verifBadge.textContent = "✗ Rejected";
        } else if (devStatus === "needs_review") {
          verifBadge.className = "badge-verification-status status-needs-review";
          verifBadge.textContent = "⏳ Needs Review";
        } else {
          verifBadge.className = "badge-verification-status status-pending";
          verifBadge.textContent = "⏳ Pending Review";
        }
      } else {
        verifBadge.textContent = "⏳ Unverified (Milestone B6)";
      }
      badgeGroup.appendChild(verifBadge);

      header.appendChild(idGroup);
      header.appendChild(badgeGroup);
      card.appendChild(header);

      // Metadata Row
      const metaRow = document.createElement("div");
      metaRow.className = "candidate-meta-row";

      if (
        cand.metadata &&
        (cand.metadata.llm_score !== undefined || cand.metadata.bm25_rank !== undefined)
      ) {
        const meta1 = document.createElement("span");
        meta1.className = "meta-item";
        meta1.innerHTML = `LLM Relevance: <strong>${cand.metadata.llm_score ?? "N/A"}/3</strong>`;
        metaRow.appendChild(meta1);

        const meta2 = document.createElement("span");
        meta2.className = "meta-item";
        meta2.innerHTML = `Original BM25 Rank: <strong>#${cand.metadata.bm25_rank ?? "N/A"}</strong>`;
        metaRow.appendChild(meta2);

        if (cand.metadata.bm25_score !== undefined) {
          const meta3 = document.createElement("span");
          meta3.className = "meta-item";
          meta3.innerHTML = `BM25 Score: <strong>${cand.metadata.bm25_score.toFixed(2)}</strong>`;
          metaRow.appendChild(meta3);
        }

        if (cand.metadata.b5_fallback) {
          const meta4 = document.createElement("span");
          meta4.className = "meta-item";
          meta4.innerHTML = `Fallback: <strong style="color: #b45309;">True</strong>`;
          metaRow.appendChild(meta4);
        }
      } else {
        const meta1 = document.createElement("span");
        meta1.className = "meta-item";
        meta1.innerHTML = `Retriever: <strong>${cand.retriever_name}</strong>`;
        metaRow.appendChild(meta1);

        const meta2 = document.createElement("span");
        meta2.className = "meta-item";
        meta2.innerHTML = `Candidate: <strong>Rank #${cand.rank}</strong>`;
        metaRow.appendChild(meta2);
      }

      card.appendChild(metaRow);

      // Developer Review Workflow Components (Visible ONLY in Developer Workflow Mode)
      if (isDev) {
        // 1. Confirmed Review Decision Banner
        const confirmedBanner = document.createElement("div");
        confirmedBanner.className = "review-confirmed-banner";

        const confirmedHeader = document.createElement("div");
        confirmedHeader.className = "review-confirmed-header";

        const confirmedTitle = document.createElement("span");
        confirmedTitle.className = "review-confirmed-title";

        const confirmedRevPill = document.createElement("span");
        confirmedRevPill.className = "review-rev-pill";

        const confirmedTime = document.createElement("span");
        confirmedTime.className = "review-timestamp";

        confirmedHeader.appendChild(confirmedTitle);
        confirmedHeader.appendChild(confirmedRevPill);
        confirmedHeader.appendChild(confirmedTime);

        const confirmedRationale = document.createElement("div");
        confirmedRationale.className = "review-rationale-text";

        confirmedBanner.appendChild(confirmedHeader);
        confirmedBanner.appendChild(confirmedRationale);

        function updateConfirmedBannerContent(status, rationale, updatedAt, revCount) {
          if (!status || status === "unverified") {
            confirmedBanner.style.display = "none";
            return;
          }
          confirmedBanner.style.display = "block";
          let statusLabel = status;
          if (status === "accepted") statusLabel = "Accepted";
          else if (status === "rejected") statusLabel = "Rejected";
          else if (status === "needs_review") statusLabel = "Needs Review";

          confirmedTitle.innerHTML = `Review Decision: <strong>${escapeHtml(statusLabel)}</strong>`;
          confirmedTime.textContent = updatedAt ? `Updated: ${formatTimestamp(updatedAt)}` : "";
          if (revCount && revCount > 0) {
            confirmedRevPill.textContent = `Revision ${revCount}`;
            confirmedRevPill.style.display = "inline-block";
          } else {
            confirmedRevPill.style.display = "none";
          }

          if (rationale && rationale.trim()) {
            confirmedRationale.innerHTML = `<strong>Rationale:</strong> ${escapeHtml(rationale)}`;
            confirmedRationale.style.display = "block";
          } else {
            confirmedRationale.textContent = "";
            confirmedRationale.style.display = "none";
          }
        }

        const initialStatus = cand.developer_verification_status || "unverified";
        if (initialStatus !== "unverified") {
          updateConfirmedBannerContent(
            cand.developer_verification_status,
            cand.developer_verification_note,
            cand.developer_verification_updated_at,
            cand.developer_verification_revision_count
          );
        } else {
          confirmedBanner.style.display = "none";
        }

        // 2. Review Action Bar
        const reviewActionBar = document.createElement("div");
        reviewActionBar.className = "review-action-bar";
        reviewActionBar.setAttribute("role", "toolbar");
        reviewActionBar.setAttribute("aria-label", `Review actions for candidate ${cand.target_id}`);

        const btnAccept = document.createElement("button");
        btnAccept.type = "button";
        btnAccept.className = "btn-review-action btn-review-accept";
        btnAccept.innerHTML = "✓ Accept";
        btnAccept.setAttribute("aria-label", `Mark candidate ${cand.target_id} as accepted`);

        const btnReject = document.createElement("button");
        btnReject.type = "button";
        btnReject.className = "btn-review-action btn-review-reject";
        btnReject.innerHTML = "✗ Reject";
        btnReject.setAttribute("aria-label", `Mark candidate ${cand.target_id} as rejected`);

        const btnNeedsReview = document.createElement("button");
        btnNeedsReview.type = "button";
        btnNeedsReview.className = "btn-review-action btn-review-needs";
        btnNeedsReview.innerHTML = "⏳ Needs Review";
        btnNeedsReview.setAttribute("aria-label", `Mark candidate ${cand.target_id} as needs review`);

        const btnHistory = document.createElement("button");
        btnHistory.type = "button";
        btnHistory.className = "btn-review-action btn-review-history";
        const revCount = cand.developer_verification_revision_count || 0;
        btnHistory.innerHTML = `📜 History${revCount > 0 ? ` (${revCount})` : ""}`;
        btnHistory.setAttribute("aria-expanded", "false");
        btnHistory.setAttribute("aria-label", `View decision history for ${cand.target_id}`);

        reviewActionBar.appendChild(btnAccept);
        reviewActionBar.appendChild(btnReject);
        reviewActionBar.appendChild(btnNeedsReview);
        reviewActionBar.appendChild(btnHistory);

        // 3. Inline Review Form Panel
        const reviewFormPanel = document.createElement("div");
        reviewFormPanel.className = "review-form-panel";
        reviewFormPanel.style.display = "none";
        reviewFormPanel.setAttribute("role", "region");
        reviewFormPanel.setAttribute("aria-label", "Record review decision form");

        let currentDecisionAction = null;

        const formHeader = document.createElement("div");
        formHeader.className = "review-form-header";

        const formTitle = document.createElement("strong");
        formTitle.className = "review-form-title";

        const formTarget = document.createElement("span");
        formTarget.className = "review-form-target";
        formTarget.innerHTML = `Target: <code>${escapeHtml(cand.target_id)}</code>`;

        formHeader.appendChild(formTitle);
        formHeader.appendChild(formTarget);

        const formLabel = document.createElement("label");
        formLabel.className = "review-form-label";
        const textareaId = `review-rationale-${cand.rank}-${Math.random().toString(36).slice(2, 7)}`;
        formLabel.setAttribute("for", textareaId);

        const formTextarea = document.createElement("textarea");
        formTextarea.id = textareaId;
        formTextarea.className = "review-form-textarea";
        formTextarea.rows = 3;

        const formError = document.createElement("div");
        formError.className = "review-form-error";
        formError.setAttribute("role", "alert");
        formError.style.display = "none";

        const formActions = document.createElement("div");
        formActions.className = "review-form-actions";

        const btnSaveDecision = document.createElement("button");
        btnSaveDecision.type = "button";
        btnSaveDecision.className = "btn btn-primary btn-save-decision";
        btnSaveDecision.textContent = "Save Decision";

        const btnCancelDecision = document.createElement("button");
        btnCancelDecision.type = "button";
        btnCancelDecision.className = "btn btn-secondary btn-cancel-decision";
        btnCancelDecision.textContent = "Cancel";

        formActions.appendChild(btnSaveDecision);
        formActions.appendChild(btnCancelDecision);

        reviewFormPanel.appendChild(formHeader);
        reviewFormPanel.appendChild(formLabel);
        reviewFormPanel.appendChild(formTextarea);
        reviewFormPanel.appendChild(formError);
        reviewFormPanel.appendChild(formActions);

        // 4. History Panel
        const historyPanel = document.createElement("div");
        historyPanel.className = "review-history-panel";
        historyPanel.style.display = "none";
        historyPanel.setAttribute("role", "region");
        historyPanel.setAttribute("aria-label", "Decision audit history");

        const historyHeader = document.createElement("div");
        historyHeader.className = "history-header";
        historyHeader.innerHTML = `<span class="history-title">Decision Audit History: <code>${escapeHtml(cand.target_id)}</code></span>`;

        const historyBody = document.createElement("div");
        historyBody.className = "history-body";

        historyPanel.appendChild(historyHeader);
        historyPanel.appendChild(historyBody);

        function openReviewForm(action) {
          if (reviewFormPanel.style.display === "flex" && currentDecisionAction === action) {
            closeReviewForm();
            return;
          }

          closeHistoryPanel();
          currentDecisionAction = action;
          formError.style.display = "none";
          formError.textContent = "";

          const isRequired = action === "accepted" || action === "rejected";
          let actionLabel = action;
          if (action === "accepted") actionLabel = "Accept (✓)";
          else if (action === "rejected") actionLabel = "Reject (✗)";
          else if (action === "needs_review") actionLabel = "Needs Review (⏳)";

          formTitle.textContent = `Record Decision: ${actionLabel}`;
          formLabel.innerHTML = isRequired
            ? `Decision Rationale <span class="required-indicator">* Required</span>`
            : `Decision Rationale <span class="optional-indicator">(Optional)</span>`;

          formTextarea.placeholder = isRequired
            ? `Enter technical justification for marking candidate as ${action} (required)...`
            : `Enter optional notes or open questions for further investigation...`;

          if (cand.developer_verification_note && cand.developer_verification_status === action) {
            formTextarea.value = cand.developer_verification_note;
          } else {
            formTextarea.value = "";
          }

          reviewFormPanel.style.display = "flex";
          formTextarea.focus();
        }

        function closeReviewForm() {
          reviewFormPanel.style.display = "none";
          currentDecisionAction = null;
          formError.style.display = "none";
          formError.textContent = "";
        }

        function closeHistoryPanel() {
          historyPanel.style.display = "none";
          btnHistory.setAttribute("aria-expanded", "false");
        }

        async function openHistoryPanel() {
          closeReviewForm();
          historyPanel.style.display = "block";
          btnHistory.setAttribute("aria-expanded", "true");
          historyBody.innerHTML = `<div class="loading-state"><div class="spinner"></div><span>Loading decision history...</span></div>`;

          try {
            const histUrl = `/api/projects/${state.activeProjectId}/requirements/${encodeURIComponent(state.activeRequirementId)}/decisions/history?target_id=${encodeURIComponent(cand.target_id)}`;
            const events = await fetchJson(histUrl);

            if (!events || events.length === 0) {
              historyBody.innerHTML = `<p class="history-empty">No review decisions recorded for this candidate link yet.</p>`;
              return;
            }

            historyBody.innerHTML = "";
            const timeline = document.createElement("div");
            timeline.className = "history-timeline";

            const sortedEvents = [...events].sort((a, b) => b.revision_number - a.revision_number);

            sortedEvents.forEach((ev) => {
              const item = document.createElement("div");
              item.className = "history-item";

              const itemHeader = document.createElement("div");
              itemHeader.className = "history-item-header";

              const revBadge = document.createElement("span");
              revBadge.className = "history-rev-tag";
              revBadge.textContent = `Revision ${ev.revision_number}`;

              const statusBadge = document.createElement("span");
              if (ev.decision === "accepted") {
                statusBadge.className = "badge-verification-status status-accepted";
                statusBadge.textContent = "✓ Accepted";
              } else if (ev.decision === "rejected") {
                statusBadge.className = "badge-verification-status status-rejected";
                statusBadge.textContent = "✗ Rejected";
              } else {
                statusBadge.className = "badge-verification-status status-needs-review";
                statusBadge.textContent = "⏳ Needs Review";
              }

              const timeSpan = document.createElement("span");
              timeSpan.className = "history-timestamp";
              timeSpan.textContent = formatTimestamp(ev.created_at);

              itemHeader.appendChild(revBadge);
              itemHeader.appendChild(statusBadge);
              itemHeader.appendChild(timeSpan);

              const itemBody = document.createElement("div");
              itemBody.className = "history-item-body";
              if (ev.rationale && ev.rationale.trim()) {
                itemBody.innerHTML = `<strong>Rationale:</strong> ${escapeHtml(ev.rationale)}`;
              } else {
                itemBody.innerHTML = `<em>No rationale recorded</em>`;
              }

              item.appendChild(itemHeader);
              item.appendChild(itemBody);
              timeline.appendChild(item);
            });

            historyBody.appendChild(timeline);
          } catch (err) {
            historyBody.innerHTML = `<div class="review-form-error" role="alert">Failed to load history: ${escapeHtml(err.message)}</div>`;
          }
        }

        btnAccept.addEventListener("click", () => openReviewForm("accepted"));
        btnReject.addEventListener("click", () => openReviewForm("rejected"));
        btnNeedsReview.addEventListener("click", () => openReviewForm("needs_review"));
        btnCancelDecision.addEventListener("click", closeReviewForm);

        btnHistory.addEventListener("click", () => {
          if (historyPanel.style.display === "block") {
            closeHistoryPanel();
          } else {
            openHistoryPanel();
          }
        });

        btnSaveDecision.addEventListener("click", async () => {
          if (!currentDecisionAction) return;

          const rationaleText = formTextarea.value.trim();
          const isRequired = currentDecisionAction === "accepted" || currentDecisionAction === "rejected";

          // Client-side validation: Rationale required for accept and reject
          if (isRequired && !rationaleText) {
            formError.textContent = `A non-empty rationale is required for ${currentDecisionAction} decisions.`;
            formError.style.display = "block";
            formTextarea.focus();
            return;
          }

          formError.style.display = "none";

          // In-flight submission lock: prevent duplicate clicks
          btnSaveDecision.disabled = true;
          btnSaveDecision.textContent = "Saving...";
          btnCancelDecision.disabled = true;
          btnAccept.disabled = true;
          btnReject.disabled = true;
          btnNeedsReview.disabled = true;
          btnHistory.disabled = true;

          try {
            const postUrl = `/api/projects/${state.activeProjectId}/requirements/${encodeURIComponent(state.activeRequirementId)}/decisions`;
            const payload = {
              target_id: cand.target_id,
              decision: currentDecisionAction,
              rationale: rationaleText,
            };

            const res = await fetch(postUrl, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });

            const data = await res.json();
            if (!res.ok) {
              throw new Error(data.error || `Server returned HTTP ${res.status}`);
            }

            // Confirmed update: update local candidate model
            cand.developer_verification_status = data.decision;
            cand.developer_verification_note = data.rationale;
            cand.developer_verification_updated_at = data.updated_at;
            cand.developer_verification_revision_count = data.revision_count;

            // Update badge
            if (data.decision === "accepted") {
              verifBadge.className = "badge-verification-status status-accepted";
              verifBadge.textContent = "✓ Accepted";
            } else if (data.decision === "rejected") {
              verifBadge.className = "badge-verification-status status-rejected";
              verifBadge.textContent = "✗ Rejected";
            } else if (data.decision === "needs_review") {
              verifBadge.className = "badge-verification-status status-needs-review";
              verifBadge.textContent = "⏳ Needs Review";
            } else {
              verifBadge.className = "badge-verification-status status-pending";
              verifBadge.textContent = "⏳ Pending Review";
            }

            // Update confirmed banner
            updateConfirmedBannerContent(
              data.decision,
              data.rationale,
              data.updated_at,
              data.revision_count
            );

            // Update history button text
            btnHistory.innerHTML = `📜 History (${data.revision_count})`;

            // Close form
            closeReviewForm();
          } catch (err) {
            // Accessible error notification without optimistic UI update
            formError.textContent = err.message || "Failed to save review decision.";
            formError.style.display = "block";
          } finally {
            btnSaveDecision.disabled = false;
            btnSaveDecision.textContent = "Save Decision";
            btnCancelDecision.disabled = false;
            btnAccept.disabled = false;
            btnReject.disabled = false;
            btnNeedsReview.disabled = false;
            btnHistory.disabled = false;
          }
        });

        card.appendChild(confirmedBanner);
        card.appendChild(reviewActionBar);
        card.appendChild(reviewFormPanel);
        card.appendChild(historyPanel);
      }

      // Code Preview Section: Collapsed by Default (Requirement 5)
      if (cand.code_preview) {
        const previewSection = document.createElement("div");
        previewSection.className = "code-preview-section";

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "btn-toggle-code";
        toggleBtn.setAttribute("aria-expanded", "false");
        toggleBtn.setAttribute("aria-controls", `code-block-${cand.rank}`);
        toggleBtn.innerHTML = `<span>View Code (${cand.code_lines} lines) ▾</span>`;

        const codeBlockContainer = document.createElement("div");
        codeBlockContainer.id = `code-block-${cand.rank}`;
        codeBlockContainer.className = "code-block-container";
        codeBlockContainer.style.display = "none"; // Collapsed by default

        const codeHeader = document.createElement("div");
        codeHeader.className = "code-block-header";

        const codeMeta = document.createElement("span");
        codeMeta.textContent = `${cand.display_name} • ${cand.code_lines} lines • ${cand.code_chars} chars`;

        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "copy-code-btn";
        copyBtn.textContent = "Copy Code";

        copyBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard
              .writeText(cand.code_preview)
              .then(() => {
                copyBtn.textContent = "Copied!";
                setTimeout(() => {
                  copyBtn.textContent = "Copy Code";
                }, 1500);
              })
              .catch(() => {
                copyBtn.textContent = "Copied!";
                setTimeout(() => {
                  copyBtn.textContent = "Copy Code";
                }, 1500);
              });
          } else {
            // Fallback for non-secure contexts
            const textarea = document.createElement("textarea");
            textarea.value = cand.code_preview;
            document.body.appendChild(textarea);
            textarea.select();
            try {
              document.execCommand("copy");
              copyBtn.textContent = "Copied!";
              setTimeout(() => {
                copyBtn.textContent = "Copy Code";
              }, 1500);
            } finally {
              document.body.removeChild(textarea);
            }
          }
        });

        codeHeader.appendChild(codeMeta);
        codeHeader.appendChild(copyBtn);

        const codeContent = document.createElement("pre");
        codeContent.className = "code-block-content";
        codeContent.textContent = cand.code_preview;

        codeBlockContainer.appendChild(codeHeader);
        codeBlockContainer.appendChild(codeContent);

        // Click to expand/collapse code
        toggleBtn.addEventListener("click", () => {
          const isCurrentlyHidden = codeBlockContainer.style.display === "none";
          codeBlockContainer.style.display = isCurrentlyHidden ? "block" : "none";
          toggleBtn.setAttribute("aria-expanded", isCurrentlyHidden ? "true" : "false");
          const span = toggleBtn.querySelector("span");
          if (span) {
            span.textContent = isCurrentlyHidden
              ? "Hide Code ▴"
              : `View Code (${cand.code_lines} lines) ▾`;
          }
        });

        previewSection.appendChild(toggleBtn);
        previewSection.appendChild(codeBlockContainer);
        card.appendChild(previewSection);
      }

      elements.candidatesList.appendChild(card);
    });

    // Progressive disclosure container for candidates > 5 (Requirement 4)
    if (elements.revealContainer && elements.btnRevealCandidates) {
      if (candidates.length > 5) {
        elements.revealContainer.style.display = "flex";
        state.isCandidatesRevealed = false;
        elements.btnRevealCandidates.setAttribute("aria-expanded", "false");
        elements.revealBtnText.textContent = `Show ${candidates.length - 5} more candidates (5 of ${candidates.length} shown) ▾`;
      } else {
        elements.revealContainer.style.display = "none";
      }
    }
  }

  // Run on page load
  document.addEventListener("DOMContentLoaded", init);
})();
