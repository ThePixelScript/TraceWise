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
      verifBadge.textContent = isDev
        ? "⏳ Pending Review"
        : "⏳ Unverified (Milestone B6)";
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
