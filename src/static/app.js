// Planly Frontend Client State & Operations
let appState = {
  hasPlan: false,
  isPaused: false,
  plan: null,
  syllabus: null,
  metrics: null,
  database: null,
  activeFilter: 'all',
  searchQuery: '',
  todayDate: new Date().toISOString().split('T')[0],
  activeTab: null,
  collapsedWeeks: new Set(),
  expandedDays: new Set(),
  expandedTopics: new Set(),
  collapsedSubtopics: new Set(),
  topicsFilter: 'all',
  topicsSearch: ''
};

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

document.addEventListener("DOMContentLoaded", () => {
  setDefaultDates();
  recalculateAvailabilitySummary();
  loadPlanData();
});

function setDefaultDates() {
  const today = new Date().toISOString().split('T')[0];
  appState.todayDate = today;

  const startDateInput = document.getElementById("plan-start-date");
  if (startDateInput && !startDateInput.value) startDateInput.value = today;

  const resumeDateInput = document.getElementById("resume-start-date");
  if (resumeDateInput) resumeDateInput.value = today;

  const realignDateInput = document.getElementById("realign-from-date");
  if (realignDateInput) realignDateInput.value = today;

  const resetProgressDateInput = document.getElementById("reset-progress-start-date");
  if (resetProgressDateInput) resetProgressDateInput.value = today;
}

// Fetch Full Plan from Server
async function loadPlanData() {
  try {
    const res = await fetch('/api/plan');
    const data = await res.json();

    appState.hasPlan = data.has_plan;
    appState.database = data.database;
    appState.plan = data.plan;
    appState.metrics = data.metrics;
    appState.isPaused = data.plan ? data.plan.is_paused : false;

    renderDatabaseBadge();
    renderPlanStatus();

    if (appState.hasPlan && appState.plan) {
      appState.syllabus = null;
      document.getElementById("stats-bar").style.display = "grid";
      document.getElementById("btn-reset-plan").style.display = "inline-flex";
      const btnResetProgressSetup = document.getElementById("btn-reset-progress-setup");
      if (btnResetProgressSetup) btnResetProgressSetup.style.display = "inline-flex";
      renderStatsBar();
      renderTodayView();
      renderScheduleView();
      renderTopicsView();
      syncFormWithSavedAvailability();
      if (!appState.activeTab) {
        switchTab('tab-today');
      }
    } else {
      document.getElementById("stats-bar").style.display = "none";
      document.getElementById("today-no-plan-view").style.display = "block";
      document.getElementById("today-plan-view").style.display = "none";
      const btnResetProgressSetup = document.getElementById("btn-reset-progress-setup");
      if (btnResetProgressSetup) btnResetProgressSetup.style.display = "none";
      loadSyllabusFallback();
      switchTab('tab-setup');
    }
  } catch (err) {
    console.error("Error loading plan:", err);
    showToast("Failed to load plan from server", true);
  }
}

// Database Status Indicator
function renderDatabaseBadge() {
  const badge = document.getElementById("db-badge");
  const text = document.getElementById("db-text");
  const formStorageName = document.getElementById("form-storage-name");
  const mongoAlert = document.getElementById("mongo-alert");

  if (!appState.database) return;

  if (badge) badge.style.display = "none";
  if (text) text.textContent = "";
  if (formStorageName) formStorageName.textContent = "";

  if (appState.database.connected) {
    if (mongoAlert) mongoAlert.style.display = "none";
  } else {
    if (mongoAlert) mongoAlert.style.display = "flex";
  }
}

// Plan Status Pill and Action Buttons
function renderPlanStatus() {
  const badge = document.getElementById("plan-status-badge");
  const statusText = document.getElementById("status-text");
  const btnPause = document.getElementById("btn-pause");
  const btnResume = document.getElementById("btn-resume");
  const btnRealign = document.getElementById("btn-realign");
  const btnResetProgress = document.getElementById("btn-reset-progress");
  const btnResetProgressSetup = document.getElementById("btn-reset-progress-setup");
  const resetStatLink = document.getElementById("stat-reset-progress-link");
  const pausedBanner = document.getElementById("paused-banner");

  if (!appState.hasPlan) {
    badge.className = "badge badge-status";
    statusText.textContent = "No Active Plan";
    btnPause.style.display = "none";
    btnResume.style.display = "none";
    btnRealign.style.display = "none";
    if (btnResetProgress) btnResetProgress.style.display = "none";
    if (btnResetProgressSetup) btnResetProgressSetup.style.display = "none";
    if (resetStatLink) resetStatLink.style.display = "none";
    pausedBanner.style.display = "none";
    return;
  }

  if (btnResetProgress) btnResetProgress.style.display = "inline-flex";
  if (btnResetProgressSetup) btnResetProgressSetup.style.display = "inline-flex";
  if (resetStatLink) {
    resetStatLink.style.display = (appState.metrics && appState.metrics.completed_problems > 0) ? "inline" : "none";
  }

  if (appState.isPaused) {
    badge.className = "badge badge-status paused";
    statusText.textContent = "Plan Paused";
    btnPause.style.display = "none";
    btnResume.style.display = "inline-flex";
    btnRealign.style.display = "none";
    pausedBanner.style.display = "flex";

    const pausedAt = appState.plan.paused_at ? new Date(appState.plan.paused_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'recently';
    document.getElementById("paused-info").textContent = `Plan paused on ${pausedAt}. When you're ready, click Resume to re-align remaining problems.`;
  } else {
    badge.className = "badge badge-status active";
    statusText.textContent = "Plan Active";
    btnPause.style.display = "inline-flex";
    btnResume.style.display = "none";
    btnRealign.style.display = "inline-flex";
    pausedBanner.style.display = "none";
  }
}

// Render Top Stats Bar
function renderStatsBar() {
  const m = appState.metrics;
  if (!m) return;

  document.getElementById("stat-progress-text").textContent = `${m.completed_problems} / ${m.total_problems} (${m.completion_percent}%)`;
  document.getElementById("stat-progress-bar").style.width = `${m.completion_percent}%`;

  const resetStatLink = document.getElementById("stat-reset-progress-link");
  if (resetStatLink) {
    resetStatLink.style.display = (m.completed_problems > 0) ? "inline" : "none";
  }

  if (m.target_completion_date) {
    const d = new Date(m.target_completion_date);
    document.getElementById("stat-target-date").textContent = d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
  } else {
    document.getElementById("stat-target-date").textContent = "--";
  }

  document.getElementById("stat-days-text").textContent = `${m.completed_study_days} / ${m.total_study_days} Days`;
  document.getElementById("stat-days-sub").textContent = `${m.remaining_study_days} study days left`;

  const avail = appState.plan.weekly_availability || {};
  const totalHrs = Object.values(avail).reduce((acc, h) => acc + Number(h), 0);
  const activeDays = Object.values(avail).filter(h => Number(h) > 0).length;

  document.getElementById("stat-weekly-hours").textContent = `${totalHrs.toFixed(1)} hrs / week`;
  document.getElementById("stat-weekly-days").textContent = `${activeDays} study days / week`;

  const revCount = m.revision_problems || 0;
  const revEl = document.getElementById("stat-revision-count");
  if (revEl) {
    revEl.textContent = `${revCount} Problem${revCount === 1 ? '' : 's'}`;
  }
}

function filterRevisionOnly() {
  switchTab('tab-schedule');
  filterSchedule('revision');
}

// Render Today's Tab
function renderTodayView() {
  const container = document.getElementById("today-plan-view");
  const emptyState = document.getElementById("today-no-plan-view");

  if (!appState.hasPlan) {
    container.style.display = "none";
    emptyState.style.display = "block";
    return;
  }

  emptyState.style.display = "none";
  container.style.display = "block";

  const m = appState.metrics;
  const activeDay = m ? m.active_focus_day : null;
  const problemsList = document.getElementById("today-problems-list");
  const congratsCard = document.getElementById("today-congrats-card");
  const topicsTags = document.getElementById("today-topics-tags");

  if (!activeDay) {
    // Plan complete or no day found
    document.getElementById("today-date-heading").textContent = "All Planned Days Finished!";
    document.getElementById("today-allocated-hours").textContent = "🏆 DSA Syllabus 100% Complete";
    topicsTags.innerHTML = "";
    problemsList.innerHTML = `<div class="congrats-card"><div class="congrats-icon">🎉</div><h3>Congratulations!</h3><p>You have finished the entire Striver's A2Z DSA sheet!</p></div>`;
    congratsCard.style.display = "none";
    return;
  }

  const isRest = activeDay.type === "rest";
  const dateObj = new Date(activeDay.date);
  const dateHeading = dateObj.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  document.getElementById("today-date-heading").textContent = dateHeading;

  const dayBadge = document.getElementById("today-day-badge");
  if (activeDay.date === appState.todayDate) {
    dayBadge.textContent = isRest ? "Today's Rest" : `Today's Session (Day ${activeDay.day_number})`;
    dayBadge.className = "badge badge-accent";
  } else {
    dayBadge.textContent = `Next Up: Day ${activeDay.day_number}`;
    dayBadge.className = "badge badge-status";
  }

  if (isRest) {
    document.getElementById("today-allocated-hours").textContent = "Rest & Recovery";
    topicsTags.innerHTML = "";
    document.getElementById("today-done-count").textContent = "0 tasks";
    document.getElementById("today-done-pct").textContent = "Rest Day";
    document.getElementById("today-progress-bar").style.width = "100%";
    document.getElementById("btn-mark-today-complete").style.display = "none";
    congratsCard.style.display = "none";

    problemsList.innerHTML = `
      <div class="rest-day-card">
        <div class="rest-emoji">🧘 ☕</div>
        <div class="rest-title">Rest & Recharge Day</div>
        <div class="rest-sub">No problems scheduled for today based on your weekly availability. Give your brain time to consolidate concepts!</div>
      </div>
    `;
    return;
  }

  // Study Day
  document.getElementById("btn-mark-today-complete").style.display = "inline-flex";
  document.getElementById("today-allocated-hours").textContent = `⏱️ Allocated: ${activeDay.allocated_hours} Hours (~${activeDay.est_minutes} min)`;

  // Render Topic badges
  topicsTags.innerHTML = (activeDay.topics || []).map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join("");

  const problems = activeDay.problems || [];
  const completedCount = problems.filter(p => p.completed).length;
  const pct = problems.length > 0 ? Math.round((completedCount / problems.length) * 100) : 0;

  document.getElementById("today-done-count").textContent = `${completedCount} of ${problems.length} problems completed`;
  document.getElementById("today-done-pct").textContent = `${pct}%`;
  document.getElementById("today-progress-bar").style.width = `${pct}%`;

  if (completedCount === problems.length && problems.length > 0) {
    congratsCard.style.display = "block";
    document.getElementById("btn-mark-today-complete").textContent = "Mark All Incomplete";
  } else {
    congratsCard.style.display = "none";
    document.getElementById("btn-mark-today-complete").innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Mark All Done`;
  }

  problemsList.innerHTML = problems.map(p => createProblemCardHtml(p, activeDay.day_number)).join("");
}

// Generate Problem Card HTML
function createProblemCardHtml(p, dayNumber, options = {}) {
  const isChecked = p.completed ? "checked" : "";
  const isRevision = Boolean(p.revision);
  let cardClass = p.completed ? "problem-card completed" : "problem-card";
  if (isRevision) cardClass += " marked-revision";
  const diffClass = (p.difficulty || 'basic').toLowerCase();
  const diffTag = p.tag || (p.difficulty ? p.difficulty.toUpperCase() : 'BASIC');

  let linksHtml = '';
  const slug = p.slug || '';
  const hasArticle = Boolean(p.article_link);
  // When article_link is present, show that and do NOT show the practice link
  const practiceLink = (!hasArticle && (p.practice_link || (slug ? `https://takeuforward.org/practice/dsa/${slug}` : ''))) || '';

  if (p.article_link) {
    linksHtml += `<a href="${p.article_link}" target="_blank" rel="noopener" class="resource-btn article" title="Read Article on takeUforward">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
      Article
    </a>`;
  } else if (practiceLink) {
    linksHtml += `<a href="${practiceLink}" target="_blank" rel="noopener" class="resource-btn practice" title="Practice on takeUforward: https://takeuforward.org/practice/dsa/${escapeHtml(slug)}">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
      Practice
    </a>`;
  }

  if (p.leetcode_link) {
    linksHtml += `<a href="${p.leetcode_link}" target="_blank" rel="noopener" class="resource-btn leetcode" title="Solve on LeetCode">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
      LeetCode
    </a>`;
  }
  if (p.youtube_link) {
    linksHtml += `<a href="${p.youtube_link}" target="_blank" rel="noopener" class="resource-btn youtube" title="Watch Video Tutorial">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      Video
    </a>`;
  }

  const primaryLink = hasArticle ? p.article_link : practiceLink;
  const titleHtml = primaryLink
    ? `<a href="${primaryLink}" target="_blank" rel="noopener" class="prob-title-link" title="${hasArticle ? 'Read article on takeUforward' : 'Practice on takeUforward (https://takeuforward.org/practice/dsa/' + escapeHtml(slug) + ')'}">${escapeHtml(p.title)}</a>`
    : escapeHtml(p.title);

  const dayBadge = (options.showDayBadge && p.day_number)
    ? `<span class="day-pill" title="Scheduled on Day ${p.day_number}">📅 Day ${p.day_number}${p.scheduled_date ? ' • ' + formatDisplayDate(p.scheduled_date, false) : ''}</span>`
    : '';

  const revisionBadge = `<span class="revision-badge" id="rev-badge-${p.uid}" style="${isRevision ? '' : 'display: none;'}" title="Marked for revision">🔖 Revision</span>`;

  const revisionBtn = `
    <button type="button" class="btn-revision ${isRevision ? 'active' : ''}" id="btn-rev-${p.uid}" onclick="toggleRevision('${p.uid}', event)" title="${isRevision ? 'Marked for revision (click to remove)' : 'Mark for revision'}">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="${isRevision ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
      </svg>
      <span class="btn-rev-text">${isRevision ? 'Revision' : 'Revise'}</span>
    </button>
  `;

  return `
    <div class="${cardClass}" id="card-${p.uid}" data-uid="${p.uid}">
      <div class="prob-left">
        <input type="checkbox" class="custom-checkbox" id="chk-${p.uid}" ${isChecked} onchange="toggleProblem('${p.uid}', this.checked)">
        <div class="prob-details">
          <div class="prob-breadcrumb">${escapeHtml(p.topic)} &gt; ${escapeHtml(p.subtopic)}</div>
          <div class="prob-title">${titleHtml}</div>
          <div class="prob-meta-row">
            ${dayBadge}
            ${revisionBadge}
            <span class="diff-tag ${diffClass}">${escapeHtml(diffTag)}</span>
            <span class="dur-pill">⏱️ ${escapeHtml(p.duration || (p.est_minutes ? p.est_minutes + ' min' : ''))}</span>
            ${(!hasArticle && slug && practiceLink) ? `<a href="${practiceLink}" target="_blank" rel="noopener" class="slug-pill font-mono" title="takeuforward.org/practice/dsa/${escapeHtml(slug)}">/${escapeHtml(slug)}</a>` : ''}
          </div>
        </div>
      </div>
      <div class="prob-right">
        ${revisionBtn}
        ${linksHtml}
      </div>
    </div>
  `;
}

// Toggle Individual Problem
async function toggleProblem(uid, completed) {
  if (!appState.hasPlan) {
    showToast("Please create a study plan in 'Availability & Plan Setup' to track and save progress!", true);
    document.querySelectorAll(`[data-uid="${uid}"] .custom-checkbox`).forEach(chk => {
      chk.checked = false;
    });
    return;
  }

  // Optimistic UI updates across all matching cards and checkboxes
  document.querySelectorAll(`[data-uid="${uid}"]`).forEach(card => {
    if (completed) card.classList.add("completed");
    else card.classList.remove("completed");
    const chk = card.querySelector('.custom-checkbox');
    if (chk) chk.checked = completed;
  });

  // Update problem in memory state
  if (appState.plan && appState.plan.schedule) {
    for (const d of appState.plan.schedule) {
      if (d.problems) {
        const found = d.problems.find(p => p.uid === uid);
        if (found) {
          found.completed = completed;
          d.completed = d.problems.every(p => p.completed);
          break;
        }
      }
    }
  }

  try {
    const res = await fetch(`/api/problem/${encodeURIComponent(uid)}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed, date: appState.todayDate })
    });
    const data = await res.json();

    if (data.success) {
      if (data.plan) {
        appState.plan = data.plan;
      }
      if (data.metrics) {
        appState.metrics = data.metrics;
      }
      renderStatsBar();
      // Re-render views to keep schedule and counters fully synchronized
      renderTodayView();
      renderTopicsView();
      renderScheduleView();

      if (data.moved_to_today && data.recalculated) {
        const dateMsg = data.new_target_completion_date
          ? ` • New finish date: ${formatDisplayDate(data.new_target_completion_date, true)}`
          : '';
        showToast(`⚡ Solved ahead of time! Moved to Today & schedule realigned${dateMsg}`);
      } else {
        showToast(completed ? "Problem completed! 🎉" : "Marked incomplete");
      }
    } else {
      showToast(data.error || "Failed to update status", true);
    }
  } catch (err) {
    console.error("Error toggling problem:", err);
    showToast("Failed to update status", true);
  }
}

// Toggle Revision for an Individual Problem
async function toggleRevision(uid, event) {
  if (event) {
    event.stopPropagation();
    event.preventDefault();
  }

  if (!appState.hasPlan) {
    showToast("Please create a study plan in 'Availability & Plan Setup' to track revision problems!", true);
    return;
  }

  // Determine current revision state in memory
  let currentRevision = false;
  if (appState.plan && appState.plan.schedule) {
    for (const d of appState.plan.schedule) {
      if (d.problems) {
        const found = d.problems.find(p => p.uid === uid);
        if (found) {
          currentRevision = Boolean(found.revision);
          break;
        }
      }
    }
  }
  const targetRevision = !currentRevision;

  // Optimistic UI updates across all matching cards
  document.querySelectorAll(`[data-uid="${uid}"]`).forEach(card => {
    if (targetRevision) {
      card.classList.add("marked-revision");
    } else {
      card.classList.remove("marked-revision");
    }
    const btnRev = card.querySelector(".btn-revision");
    if (btnRev) {
      btnRev.classList.toggle("active", targetRevision);
      const svg = btnRev.querySelector("svg");
      if (svg) svg.setAttribute("fill", targetRevision ? "currentColor" : "none");
      const txt = btnRev.querySelector(".btn-rev-text");
      if (txt) txt.textContent = targetRevision ? "Revision" : "Revise";
      btnRev.title = targetRevision ? "Marked for revision (click to remove)" : "Mark for revision";
    }
    const badge = card.querySelector(".revision-badge");
    if (badge) {
      badge.style.display = targetRevision ? "inline-flex" : "none";
    }
  });

  // Update in-memory problem state
  if (appState.plan && appState.plan.schedule) {
    for (const d of appState.plan.schedule) {
      if (d.problems) {
        const found = d.problems.find(p => p.uid === uid);
        if (found) {
          found.revision = targetRevision;
          found.revision_marked_at = targetRevision ? new Date().toISOString() : null;
          break;
        }
      }
    }
  }

  // Optimistically update revision metric count in stats bar
  if (appState.metrics) {
    if (targetRevision) {
      appState.metrics.revision_problems = (appState.metrics.revision_problems || 0) + 1;
    } else {
      appState.metrics.revision_problems = Math.max(0, (appState.metrics.revision_problems || 0) - 1);
    }
    renderStatsBar();
  }

  try {
    const res = await fetch(`/api/problem/${encodeURIComponent(uid)}/revision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ revision: targetRevision })
    });
    const data = await res.json();

    if (data.success) {
      if (data.metrics) {
        appState.metrics = data.metrics;
        renderStatsBar();
      }
      showToast(targetRevision ? "Marked for revision 🔖" : "Removed from revision");

      // If active view is filtering for revision, re-render to update the list immediately
      if (appState.activeFilter === "revision") {
        renderScheduleView();
      }
      if (appState.topicsFilter === "revision") {
        renderTopicsView();
      }
    } else {
      showToast(data.error || "Failed to update revision status", true);
    }
  } catch (err) {
    console.error("Error updating revision status:", err);
    showToast("Failed to update revision status", true);
  }
}

// Toggle All Problems for Active Day
async function toggleTodayComplete() {
  const activeDay = appState.metrics ? appState.metrics.active_focus_day : null;
  if (!activeDay || activeDay.type !== "study") return;

  const allCurrentlyDone = (activeDay.problems || []).every(p => p.completed);
  const targetState = !allCurrentlyDone;

  try {
    const res = await fetch(`/api/day/${activeDay.day_number}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: targetState })
    });
    const data = await res.json();

    if (data.success && data.metrics) {
      appState.metrics = data.metrics;
      // Reload fresh plan data to sync day structures
      await loadPlanData();
      showToast(targetState ? "Day marked complete! Great work!" : "Day marked incomplete");
    }
  } catch (err) {
    console.error("Error toggling day:", err);
    showToast("Error updating day status", true);
  }
}

// Format date range for a week
function formatWeekDateRange(startDateStr, endDateStr) {
  if (!startDateStr || !endDateStr) return "";
  const parseSafe = (str) => {
    const parts = String(str).split("T")[0].split("-");
    if (parts.length === 3) {
      return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }
    return new Date(str);
  };
  const d1 = parseSafe(startDateStr);
  const d2 = parseSafe(endDateStr);
  if (isNaN(d1.getTime()) || isNaN(d2.getTime())) {
    return `${startDateStr} – ${endDateStr}`;
  }
  const sameYear = d1.getFullYear() === d2.getFullYear();
  const opts1 = { month: "short", day: "numeric", ...(!sameYear ? { year: "numeric" } : {}) };
  const opts2 = { month: "short", day: "numeric", year: "numeric" };
  return `${d1.toLocaleDateString(undefined, opts1)} – ${d2.toLocaleDateString(undefined, opts2)}`;
}

// Render individual day card inside a week
function renderScheduleDayCard(day, isSearching) {
  const isToday = day.date === appState.todayDate;
  const isRest = day.type === "rest";
  const cardClass = `day-timeline-card ${isToday ? 'is-today' : ''} ${day.completed ? 'is-completed' : ''}`;
  const dateFormatted = formatDisplayDate(day.date, true);

  if (isRest) {
    return `
      <div class="${cardClass}">
        <div class="day-timeline-header">
          <div class="day-header-left">
            <span class="day-badge-num rest">Rest Day</span>
            <span class="day-date-str">${dateFormatted}</span>
          </div>
          <div class="day-header-right">
            <span class="subtext">🧘 Recharge</span>
          </div>
        </div>
      </div>
    `;
  }

  const isRevisionFilter = appState.activeFilter === "revision";
  const dayProblems = day.problems || [];
  const displayProblems = isRevisionFilter ? dayProblems.filter(p => Boolean(p.revision)) : dayProblems;
  const completedProbs = dayProblems.filter(p => p.completed).length;
  const totalProbs = dayProblems.length;
  const isAllDone = totalProbs > 0 && completedProbs === totalProbs;

  if (!appState.expandedDays) appState.expandedDays = new Set();
  const bodyId = `body-day-${day.day_number}`;
  const isExpanded = isSearching || isToday || isRevisionFilter || appState.expandedDays.has(bodyId);

  return `
    <div class="${cardClass}">
      <div class="day-timeline-header" onclick="toggleAccordion('${bodyId}')">
        <div class="day-header-left">
          <span class="day-badge-num ${isAllDone ? 'badge-accent' : ''}">Day ${day.day_number}</span>
          <span class="day-date-str">${dateFormatted}</span>
          ${isToday ? '<span class="badge badge-accent">Today</span>' : ''}
          ${isRevisionFilter ? `<span class="badge badge-warning">${displayProblems.length} for revision</span>` : ''}
        </div>
        <div class="day-header-right">
          <span class="subtext">${completedProbs}/${totalProbs} Done (${day.allocated_hours}h)</span>
          <span class="day-accordion-arrow" id="icon-${bodyId}" style="font-size: 0.8rem; color: var(--text-dim);">${isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>
      <div class="day-timeline-body" id="${bodyId}" style="display: ${isExpanded ? 'flex' : 'none'};">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; flex-wrap: wrap; gap: 0.5rem;">
          <div class="topics-tags">
            ${(day.topics || []).map(t => `<span class="topic-tag">${escapeHtml(t)}</span>`).join('')}
          </div>
          <button class="btn btn-outline btn-sm" onclick="toggleScheduleDay(${day.day_number}, ${!isAllDone})">
            ${isAllDone ? 'Mark Incomplete' : 'Mark Day Done'}
          </button>
        </div>
        <div class="problems-grid">
          ${displayProblems.map(p => createProblemCardHtml(p, day.day_number)).join('')}
        </div>
      </div>
    </div>
  `;
}

// Render Full Schedule Timeline: Group by Week, then inside Week include Day
function renderScheduleView() {
  const container = document.getElementById("schedule-list");
  if (!appState.plan || !appState.plan.schedule) {
    container.innerHTML = `<div class="empty-state"><p>No schedule available yet.</p></div>`;
    return;
  }

  const schedule = appState.plan.schedule;
  const filter = appState.activeFilter || "all";
  const query = (appState.searchQuery || "").toLowerCase().trim();
  const isSearching = Boolean(query);

  if (!appState.collapsedWeeks) appState.collapsedWeeks = new Set();
  if (!appState.expandedDays) appState.expandedDays = new Set();

  // Group all schedule days into weeks
  const weeksMap = new Map();
  schedule.forEach((day, index) => {
    const weekNum = day.week_number || (Math.floor(index / 7) + 1);
    day.week_number = weekNum;

    if (!weeksMap.has(weekNum)) {
      weeksMap.set(weekNum, {
        weekNumber: weekNum,
        days: [],
        startDate: day.date,
        endDate: day.date,
        totalProblems: 0,
        completedProblems: 0,
        totalHours: 0,
        studyDaysCount: 0,
        restDaysCount: 0
      });
    }

    const w = weeksMap.get(weekNum);
    w.days.push(day);
    w.endDate = day.date;

    if (day.type === "study") {
      w.studyDaysCount++;
      w.totalHours += Number(day.allocated_hours) || 0;
      const probs = day.problems || [];
      w.totalProblems += probs.length;
      w.completedProblems += probs.filter(p => p.completed).length;
    } else if (day.type === "rest") {
      w.restDaysCount++;
    }
  });

  let totalMatchingDaysAcrossWeeks = 0;
  const renderedWeeksHtml = [];

  for (const [weekNum, w] of weeksMap.entries()) {
    const matchingDays = w.days.filter(day => {
      // Filter by type / status
      if (filter === "completed" && (!day.completed || day.type !== "study")) return false;
      if (filter === "pending" && (day.completed || day.type !== "study")) return false;
      if (filter === "study" && day.type !== "study") return false;
      if (filter === "rest" && day.type !== "rest") return false;
      if (filter === "revision") {
        if (day.type !== "study") return false;
        const hasRevision = (day.problems || []).some(p => Boolean(p.revision));
        if (!hasRevision) return false;
      }

      // Filter by search query
      if (query) {
        if (day.type === "rest") return "rest".includes(query);
        const matchesTopic = (day.topics || []).some(t => t.toLowerCase().includes(query));
        const matchesProb = (day.problems || []).some(p =>
          p.title.toLowerCase().includes(query) ||
          (p.slug && p.slug.toLowerCase().includes(query))
        );
        return matchesTopic || matchesProb;
      }

      return true;
    });

    if (matchingDays.length === 0) {
      continue;
    }

    totalMatchingDaysAcrossWeeks += matchingDays.length;

    const isCurrentWeek = w.days.some(d => d.date === appState.todayDate);
    const isWeekCompleted = w.totalProblems > 0 && w.completedProblems === w.totalProblems;
    const weekPercent = w.totalProblems > 0 ? Math.round((w.completedProblems / w.totalProblems) * 100) : 0;
    const isCollapsed = (isSearching || filter === "revision") ? false : appState.collapsedWeeks.has(weekNum);
    const dateRangeStr = formatWeekDateRange(w.startDate, w.endDate);

    const daysHtml = matchingDays.map(day => renderScheduleDayCard(day, isSearching)).join('');

    renderedWeeksHtml.push(`
      <div class="week-group-card ${isCurrentWeek ? 'is-current-week' : ''} ${isWeekCompleted ? 'is-week-done' : ''}" id="week-card-${weekNum}">
        <div class="week-header" onclick="toggleWeekAccordion(${weekNum})">
          <div class="week-header-left">
            <span class="week-badge">Week ${weekNum}</span>
            <span class="week-date-range">${dateRangeStr}</span>
            ${isCurrentWeek ? '<span class="badge badge-accent">Current Week</span>' : ''}
            ${isWeekCompleted ? '<span class="badge badge-success">✓ Completed</span>' : ''}
          </div>
          <div class="week-header-right">
            <div class="week-stats-summary">
              <span class="week-stat-pill"><strong>${w.completedProblems}/${w.totalProblems}</strong> Done</span>
              <span class="week-stat-pill">⏱️ ${w.totalHours.toFixed(1)}h</span>
              <span class="week-stat-subtext">${w.studyDaysCount} Study${w.restDaysCount > 0 ? `, ${w.restDaysCount} Rest` : ''}</span>
            </div>
            <div class="week-progress-pill" title="${weekPercent}% complete">
              <div class="week-progress-fill ${isWeekCompleted ? 'done' : ''}" style="width: ${weekPercent}%"></div>
            </div>
            <span class="week-chevron ${isCollapsed ? 'collapsed' : ''}" id="chevron-week-${weekNum}">▼</span>
          </div>
        </div>
        <div class="week-body" id="body-week-${weekNum}" style="display: ${isCollapsed ? 'none' : 'flex'};">
          <div class="week-days-list">
            ${daysHtml}
          </div>
        </div>
      </div>
    `);
  }

  if (totalMatchingDaysAcrossWeeks === 0) {
    if (filter === "revision") {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">🔖</div><h3>No Problems Marked for Revision</h3><p>Click the <strong>Revise</strong> button on any problem card to bookmark it for review.</p></div>`;
    } else {
      container.innerHTML = `<div class="empty-state"><p>No schedule days match your search or filter.</p></div>`;
    }
    return;
  }

  container.innerHTML = renderedWeeksHtml.join('');
}

function toggleWeekAccordion(weekNum) {
  if (!appState.collapsedWeeks) appState.collapsedWeeks = new Set();
  const isCurrentlyCollapsed = appState.collapsedWeeks.has(weekNum);

  if (isCurrentlyCollapsed) {
    appState.collapsedWeeks.delete(weekNum);
  } else {
    appState.collapsedWeeks.add(weekNum);
  }

  const body = document.getElementById(`body-week-${weekNum}`);
  const chevron = document.getElementById(`chevron-week-${weekNum}`);
  if (body) {
    body.style.display = isCurrentlyCollapsed ? "flex" : "none";
  }
  if (chevron) {
    chevron.classList.toggle("collapsed", !isCurrentlyCollapsed);
  }
}

function expandAllWeeks() {
  if (!appState.collapsedWeeks) appState.collapsedWeeks = new Set();
  appState.collapsedWeeks.clear();
  document.querySelectorAll(".week-body").forEach(el => el.style.display = "flex");
  document.querySelectorAll(".week-chevron").forEach(el => el.classList.remove("collapsed"));
}

function collapseAllWeeks() {
  if (!appState.collapsedWeeks) appState.collapsedWeeks = new Set();
  if (appState.plan && appState.plan.schedule) {
    appState.plan.schedule.forEach((day, index) => {
      const wNum = day.week_number || (Math.floor(index / 7) + 1);
      appState.collapsedWeeks.add(wNum);
    });
  }
  document.querySelectorAll(".week-body").forEach(el => el.style.display = "none");
  document.querySelectorAll(".week-chevron").forEach(el => el.classList.add("collapsed"));
}

function toggleAccordion(bodyId) {
  const el = document.getElementById(bodyId);
  if (!el) return;
  const isCurrentlyHidden = el.style.display === "none";
  el.style.display = isCurrentlyHidden ? "flex" : "none";

  if (!appState.expandedDays) appState.expandedDays = new Set();
  if (isCurrentlyHidden) {
    appState.expandedDays.add(bodyId);
  } else {
    appState.expandedDays.delete(bodyId);
  }

  const icon = document.getElementById(`icon-${bodyId}`);
  if (icon) {
    icon.textContent = isCurrentlyHidden ? "▲" : "▼";
  }
}

async function toggleScheduleDay(dayNum, targetState) {
  try {
    const res = await fetch(`/api/day/${dayNum}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ completed: targetState })
    });
    const data = await res.json();
    if (data.success) {
      await loadPlanData();
      showToast(targetState ? `Day ${dayNum} completed!` : `Day ${dayNum} marked incomplete`);
    }
  } catch (err) {
    showToast("Error updating day", true);
  }
}

// Filter Schedule
function filterSchedule(filterName) {
  appState.activeFilter = filterName;
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.filter === filterName);
  });
  renderScheduleView();
}

function handleScheduleSearch(val) {
  appState.searchQuery = val;
  renderScheduleView();
}

// Fetch Syllabus fallback when no active plan exists
async function loadSyllabusFallback() {
  if (appState.syllabus) return;
  try {
    const res = await fetch('/api/syllabus');
    const data = await res.json();
    if (data.success) {
      appState.syllabus = data;
      renderTopicsView();
    }
  } catch (err) {
    console.warn("Could not load syllabus fallback:", err);
  }
}

// Render Topics & Questions Breakdown
function renderTopicsView() {
  const container = document.getElementById("topics-grid");
  if (!container) return;

  const hasPlan = Boolean(appState.hasPlan && appState.plan);
  const summary = (hasPlan && appState.plan.topics_summary) || (appState.syllabus && appState.syllabus.topics_summary);
  const metrics = appState.metrics;

  if (!summary) {
    if (!hasPlan && !appState.syllabus) {
      loadSyllabusFallback();
      container.innerHTML = `<div class="empty-state"><p>Loading syllabus questions and topics...</p></div>`;
      return;
    }
    container.innerHTML = `<div class="empty-state"><p>No topic breakdown available.</p></div>`;
    return;
  }

  // Gather problems: from plan.schedule if available, or from syllabus fallback
  const allProblems = [];
  if (hasPlan && appState.plan.schedule) {
    appState.plan.schedule.forEach(day => {
      if (day.type === "study" && day.problems) {
        day.problems.forEach(p => {
          allProblems.push({
            ...p,
            day_number: day.day_number,
            scheduled_date: day.date
          });
        });
      }
    });
  } else if (appState.syllabus && appState.syllabus.problems) {
    appState.syllabus.problems.forEach(p => {
      allProblems.push({
        ...p,
        completed: false,
        day_number: null,
        scheduled_date: null
      });
    });
  }

  // Group problems by topic and subtopic: topicName -> Map(subtopicName -> [problems])
  const topicProbsMap = new Map();
  allProblems.forEach(p => {
    const tName = p.topic || "";
    const sName = p.subtopic || "";
    if (!topicProbsMap.has(tName)) {
      topicProbsMap.set(tName, new Map());
    }
    const subMap = topicProbsMap.get(tName);
    if (!subMap.has(sName)) {
      subMap.set(sName, []);
    }
    subMap.get(sName).push(p);
  });

  const topicProgress = (metrics && metrics.topic_progress) || {};
  let overallCompleted = 0;
  let overallTotal = 0;

  summary.forEach(t => {
    const stats = topicProgress[t.topic];
    if (stats) {
      overallCompleted += (stats.completed || 0);
      overallTotal += (stats.total || t.total_problems || 0);
    } else {
      const subMap = topicProbsMap.get(t.topic);
      let comp = 0;
      let tot = 0;
      if (subMap) {
        for (const probs of subMap.values()) {
          tot += probs.length;
          comp += probs.filter(p => p.completed).length;
        }
      }
      overallCompleted += comp;
      overallTotal += (tot || t.total_problems || 0);
    }
  });

  // Update overall coverage badge
  const overallCountEl = document.getElementById("topics-overall-count");
  const overallPctEl = document.getElementById("topics-overall-pct");
  const overallPct = overallTotal > 0 ? Math.round((overallCompleted / overallTotal) * 100) : 0;
  if (overallCountEl) overallCountEl.textContent = `${overallCompleted} / ${overallTotal} Solved`;
  if (overallPctEl) overallPctEl.textContent = `${overallPct}%`;

  const activeFilter = appState.topicsFilter || 'all';
  const query = (appState.topicsSearch || '').toLowerCase().trim();
  const isSearching = Boolean(query);

  if (!appState.expandedTopics) appState.expandedTopics = new Set();
  if (!appState.collapsedSubtopics) appState.collapsedSubtopics = new Set();

  let renderedCardsCount = 0;

  const htmlCards = summary.map(t => {
    const stats = topicProgress[t.topic] || { total: t.total_problems, completed: 0 };
    const pct = stats.total > 0 ? Math.round((stats.completed / stats.total) * 100) : 0;
    const isTopicDone = stats.completed === stats.total && stats.total > 0;
    const isTopicInProgress = stats.completed > 0 && stats.completed < stats.total;

    // Apply Filter
    if (activeFilter === "in-progress" && !isTopicInProgress) return "";
    if (activeFilter === "completed" && !isTopicDone) return "";
    if (activeFilter === "pending" && isTopicDone) return "";
    if (activeFilter === "revision") {
      const hasTopicRevision = Array.from(subMap.values()).some(probs => probs.some(p => Boolean(p.revision)));
      if (!hasTopicRevision) return "";
    }

    const subMap = topicProbsMap.get(t.topic) || new Map();
    const subtopicsList = t.subtopics || [];

    // Filter subtopics and questions if searching or revision
    const topicMatchesSearch = isSearching && t.topic.toLowerCase().includes(query);
    const filteredSubtopicsData = [];
    let topicMatchingProblemsCount = 0;

    subtopicsList.forEach((sub, subIdx) => {
      const allSubProbs = subMap.get(sub.subtopic) || [];
      let visibleProbs = allSubProbs;

      if (activeFilter === "revision") {
        visibleProbs = visibleProbs.filter(p => Boolean(p.revision));
      }

      if (isSearching && !topicMatchesSearch) {
        const subtopicMatches = sub.subtopic.toLowerCase().includes(query);
        if (subtopicMatches) {
          visibleProbs = activeFilter === "revision" ? allSubProbs.filter(p => Boolean(p.revision)) : allSubProbs;
        } else {
          visibleProbs = visibleProbs.filter(p => {
            const titleMatch = (p.title || '').toLowerCase().includes(query);
            const slugMatch = (p.slug || '').toLowerCase().includes(query);
            const diffMatch = (p.difficulty || '').toLowerCase().includes(query);
            const tagMatch = (p.tag || '').toLowerCase().includes(query);
            return titleMatch || slugMatch || diffMatch || tagMatch;
          });
        }
      }

      if (visibleProbs.length > 0) {
        topicMatchingProblemsCount += visibleProbs.length;
        filteredSubtopicsData.push({
          sub,
          subIdx,
          problems: visibleProbs,
          totalSubProbs: allSubProbs.length,
          completedCount: allSubProbs.filter(p => p.completed).length
        });
      }
    });

    if (isSearching && !topicMatchesSearch && topicMatchingProblemsCount === 0) {
      return "";
    }

    renderedCardsCount++;

    const isExpanded = isSearching || (activeFilter === "revision") || appState.expandedTopics.has(t.order);

    // Status Badge
    let statusBadgeHtml = '';
    if (isTopicDone) {
      statusBadgeHtml = `<span class="badge badge-success">✓ Completed</span>`;
    } else if (isTopicInProgress) {
      statusBadgeHtml = `<span class="badge badge-accent">${pct}% Done</span>`;
    } else {
      statusBadgeHtml = `<span class="badge badge-dim">Not Started</span>`;
    }

    // Render Subtopics HTML
    const subtopicsHtml = filteredSubtopicsData.map(({ sub, subIdx, problems, totalSubProbs, completedCount }) => {
      const subId = `${t.order}-${subIdx}`;
      const isSubCollapsed = (activeFilter === "revision") ? false : appState.collapsedSubtopics.has(subId);
      const isSubDone = totalSubProbs > 0 && completedCount === totalSubProbs;

      const probCardsHtml = problems.map(p => createProblemCardHtml(p, p.day_number, { showDayBadge: true })).join('');

      return `
        <div class="subtopic-section">
          <div class="subtopic-header" onclick="toggleSubtopicAccordion('${subId}')">
            <div class="subtopic-title">
              <span class="subtopic-arrow" id="subtopic-arrow-${subId}">${isSubCollapsed ? '►' : '▼'}</span>
              <span>${t.order}.${subIdx + 1} ${escapeHtml(sub.subtopic)}</span>
            </div>
            <div class="subtopic-meta">
              <span class="subtopic-done-pill font-mono ${isSubDone ? 'is-done' : ''}">${completedCount} / ${totalSubProbs} Solved</span>
            </div>
          </div>
          <div class="problems-grid" id="subtopic-body-${subId}" style="display: ${isSubCollapsed ? 'none' : 'flex'};">
            ${probCardsHtml}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="topic-group-card ${isTopicDone ? 'is-topic-done' : ''}" id="topic-card-${t.order}">
        <div class="topic-header" onclick="toggleTopicAccordion(${t.order})">
          <div class="topic-header-left">
            <span class="topic-order-badge">Step ${t.order < 10 ? '0' + t.order : t.order}</span>
            <h3 class="topic-title-text">${escapeHtml(t.topic)}</h3>
            ${statusBadgeHtml}
          </div>
          <div class="topic-header-right">
            <span class="subtext font-mono">${stats.completed} / ${stats.total} Solved</span>
            <span class="subtext">${(t.subtopics || []).length} Subtopics</span>
            <button type="button" class="btn btn-secondary btn-sm topic-view-btn" onclick="event.stopPropagation(); toggleTopicAccordion(${t.order});">
              <span id="topic-btn-label-${t.order}">${isExpanded ? 'Hide Questions' : 'View Questions'}</span>
              <span class="topic-accordion-arrow" id="topic-arrow-${t.order}">${isExpanded ? '▲' : '▼'}</span>
            </button>
          </div>
        </div>

        <div class="topic-progress-bar-container">
          <div class="progress-track">
            <div class="progress-fill ${isTopicDone ? 'fill-completed' : ''}" style="width: ${pct}%;"></div>
          </div>
        </div>

        <div class="topic-body" id="topic-body-${t.order}" style="display: ${isExpanded ? 'block' : 'none'};">
          ${subtopicsHtml || '<div class="empty-state"><p>No matching questions found.</p></div>'}
        </div>
      </div>
    `;
  }).join('');

  if (renderedCardsCount === 0) {
    if (activeFilter === "revision") {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔖</div>
          <h3>No Problems Marked for Revision</h3>
          <p>Click the <strong>Revise</strong> button on any problem to bookmark it for review.</p>
          <button class="btn btn-secondary btn-sm" onclick="clearTopicsFilters()">View All Topics</button>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <h3>No topics or questions found</h3>
          <p>No results match "${escapeHtml(query || activeFilter)}". Try adjusting your filter or search query.</p>
          <button class="btn btn-secondary btn-sm" onclick="clearTopicsFilters()">Reset Filters</button>
        </div>
      `;
    }
    return;
  }

  container.innerHTML = htmlCards;
}

// Toggle Topic Accordion
function toggleTopicAccordion(order) {
  if (!appState.expandedTopics) appState.expandedTopics = new Set();
  const body = document.getElementById(`topic-body-${order}`);
  const arrow = document.getElementById(`topic-arrow-${order}`);
  const btnLabel = document.getElementById(`topic-btn-label-${order}`);

  if (!body) return;
  const isCurrentlyHidden = body.style.display === "none";
  body.style.display = isCurrentlyHidden ? "block" : "none";

  if (isCurrentlyHidden) {
    appState.expandedTopics.add(order);
    if (arrow) arrow.textContent = "▲";
    if (btnLabel) btnLabel.textContent = "Hide Questions";
  } else {
    appState.expandedTopics.delete(order);
    if (arrow) arrow.textContent = "▼";
    if (btnLabel) btnLabel.textContent = "View Questions";
  }
}

// Toggle Subtopic Accordion
function toggleSubtopicAccordion(subId) {
  if (!appState.collapsedSubtopics) appState.collapsedSubtopics = new Set();
  const body = document.getElementById(`subtopic-body-${subId}`);
  const arrow = document.getElementById(`subtopic-arrow-${subId}`);
  if (!body) return;

  const isHidden = body.style.display === "none";
  body.style.display = isHidden ? "flex" : "none";
  if (isHidden) {
    appState.collapsedSubtopics.delete(subId);
    if (arrow) arrow.textContent = "▼";
  } else {
    appState.collapsedSubtopics.add(subId);
    if (arrow) arrow.textContent = "►";
  }
}

// Expand All Topics
function expandAllTopics() {
  if (!appState.expandedTopics) appState.expandedTopics = new Set();
  const summary = (appState.plan && appState.plan.topics_summary) || (appState.syllabus && appState.syllabus.topics_summary) || [];
  summary.forEach(t => appState.expandedTopics.add(t.order));
  renderTopicsView();
}

// Collapse All Topics
function collapseAllTopics() {
  if (!appState.expandedTopics) appState.expandedTopics = new Set();
  appState.expandedTopics.clear();
  renderTopicsView();
}

// Filter Topics by Status
function filterTopics(filter) {
  appState.topicsFilter = filter;
  document.querySelectorAll(".topics-controls .filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.topicFilter === filter);
  });
  renderTopicsView();
}

// Search Questions and Topics
function handleTopicsSearch(val) {
  appState.topicsSearch = val;
  renderTopicsView();
}

// Clear Search and Filters
function clearTopicsFilters() {
  appState.topicsFilter = 'all';
  appState.topicsSearch = '';
  const searchInput = document.getElementById("topics-search");
  if (searchInput) searchInput.value = '';
  document.querySelectorAll(".topics-controls .filter-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.topicFilter === 'all');
  });
  renderTopicsView();
}

// Weekly Availability Setup & Hours Input Boxes
function syncHours(day, val) {
  let num = parseFloat(val);
  if (isNaN(num) || num < 0) {
    num = 0;
  }
  const valEl = document.getElementById(`val-${day}`);
  if (valEl) {
    valEl.textContent = num.toFixed(1);
  }
  recalculateAvailabilitySummary();
}

function adjustHours(day, delta) {
  const input = document.getElementById(`input-${day}`) || document.getElementById(`slider-${day}`);
  if (!input || input.disabled) return;
  let current = parseFloat(input.value);
  if (isNaN(current) || current <= 0) {
    current = 0;
  }
  let next = Math.max(0.5, Math.min(16.0, current + delta));
  next = Math.round(next * 2) / 2;
  input.value = next.toFixed(1);
  syncHours(day, input.value);
}

function validateHours(day) {
  const input = document.getElementById(`input-${day}`) || document.getElementById(`slider-${day}`);
  if (!input) return;
  let num = parseFloat(input.value);
  const check = document.getElementById(`check-${day}`);
  if (isNaN(num) || num <= 0) {
    if (check && check.checked) {
      input.value = (day === "Saturday" || day === "Sunday") ? "4.0" : "2.0";
    } else {
      input.value = "0.0";
    }
  } else {
    num = Math.max(0.5, Math.min(16.0, num));
    input.value = Number.isInteger(num) ? num.toFixed(1) : parseFloat(num.toFixed(1));
  }
  syncHours(day, input.value);
}

function toggleDayEnabled(day) {
  const checkbox = document.getElementById(`check-${day}`);
  const card = document.getElementById(`card-${day}`);
  const pill = document.getElementById(`pill-${day}`);
  const input = document.getElementById(`input-${day}`) || document.getElementById(`slider-${day}`);
  const btnDec = document.getElementById(`btn-dec-${day}`);
  const btnInc = document.getElementById(`btn-inc-${day}`);

  if (checkbox.checked) {
    card.classList.remove("disabled");
    pill.textContent = "Active";
    if (input) input.disabled = false;
    if (btnDec) btnDec.disabled = false;
    if (btnInc) btnInc.disabled = false;
    if (input && (!parseFloat(input.value) || parseFloat(input.value) <= 0)) {
      input.value = (day === "Saturday" || day === "Sunday") ? "4.0" : "2.0";
    }
  } else {
    card.classList.add("disabled");
    pill.textContent = "Off Day";
    if (input) input.disabled = true;
    if (btnDec) btnDec.disabled = true;
    if (btnInc) btnInc.disabled = true;
  }
  recalculateAvailabilitySummary();
}

function formatDisplayDate(dateStr, includeWeekday = true) {
  if (!dateStr) return "--";
  const parts = String(dateStr).split("T")[0].split("-");
  let d;
  if (parts.length === 3) {
    d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  } else {
    d = new Date(dateStr);
  }
  if (isNaN(d.getTime())) return dateStr;

  if (includeWeekday) {
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
  } else {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }
}

function estimateEndDateLocally(startDateStr, weeklyAvailability) {
  if (!startDateStr) return null;
  const parts = startDateStr.split("-");
  if (parts.length !== 3) return null;

  let curDate = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  let remainingHours = 189.6;
  const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  let daysCount = 0;
  const maxDays = 365 * 5;

  while (remainingHours > 0 && daysCount < maxDays) {
    const dayName = dayNames[curDate.getDay()];
    const h = parseFloat(weeklyAvailability[dayName]) || 0;
    if (h > 0) {
      remainingHours -= (h * 1.07);
    }
    if (remainingHours <= 0) break;
    curDate.setDate(curDate.getDate() + 1);
    daysCount++;
  }
  return curDate.toISOString().split("T")[0];
}

let estimateDebounceTimer = null;

async function fetchPlanEstimate(availability, startDate) {
  try {
    const res = await fetch("/api/estimate-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weekly_availability: availability,
        start_date: startDate
      })
    });
    const data = await res.json();
    if (data.valid && data.target_completion_date) {
      const summaryEndDate = document.getElementById("summary-end-date");
      const planEndDate = document.getElementById("plan-end-date");
      const summaryEstWeeks = document.getElementById("summary-est-weeks");

      const formatted = formatDisplayDate(data.target_completion_date, true);
      if (summaryEndDate) summaryEndDate.textContent = formatted;
      if (planEndDate) planEndDate.value = `${formatted} (${data.total_study_days} study days)`;
      if (summaryEstWeeks && data.est_weeks) {
        summaryEstWeeks.textContent = `~${Math.round(data.est_weeks)} Weeks (${data.total_calendar_days} days)`;
      }
    }
  } catch (err) {
    console.warn("Could not fetch server plan estimate:", err);
  }
}

function recalculateAvailabilitySummary() {
  let totalHours = 0;
  let activeDays = 0;
  const availability = {};

  DAYS.forEach(d => {
    const check = document.getElementById(`check-${d}`);
    const input = document.getElementById(`input-${d}`) || document.getElementById(`slider-${d}`);
    if (check && check.checked && input) {
      const h = parseFloat(input.value) || 0;
      if (h > 0) {
        totalHours += h;
        activeDays += 1;
        availability[d] = h;
      } else {
        availability[d] = 0;
      }
    } else {
      availability[d] = 0;
    }
  });

  const summaryWeeklyHrs = document.getElementById("summary-weekly-hrs");
  const summaryActiveDays = document.getElementById("summary-active-days");
  const summaryEstWeeks = document.getElementById("summary-est-weeks");
  const summaryEndDate = document.getElementById("summary-end-date");
  const planEndDate = document.getElementById("plan-end-date");

  if (summaryWeeklyHrs) summaryWeeklyHrs.textContent = `${totalHours.toFixed(1)} Hours`;
  if (summaryActiveDays) summaryActiveDays.textContent = `${activeDays} Days`;

  const startDateInput = document.getElementById("plan-start-date");
  const startDate = (startDateInput && startDateInput.value) ? startDateInput.value : appState.todayDate;

  if (totalHours <= 0) {
    if (summaryEstWeeks) summaryEstWeeks.textContent = "Select at least 1 day";
    if (summaryEndDate) summaryEndDate.textContent = "--";
    if (planEndDate) planEndDate.value = "Select at least 1 study day";
    return;
  }

  // Instant local estimate for instant responsive feedback
  const localTargetDate = estimateEndDateLocally(startDate, availability);
  if (localTargetDate) {
    const estWeeks = Math.ceil(360 / totalHours);
    if (summaryEstWeeks && !summaryEstWeeks.textContent.includes("days")) {
      summaryEstWeeks.textContent = `~${estWeeks} Weeks`;
    }
    const formattedLocal = formatDisplayDate(localTargetDate, true);
    if (summaryEndDate && (summaryEndDate.textContent === "--" || summaryEndDate.textContent === "")) {
      summaryEndDate.textContent = formattedLocal;
    }
    if (planEndDate && (!planEndDate.value || planEndDate.value.includes("Select"))) {
      planEndDate.value = formattedLocal;
    }
  }

  // Debounced exact calculation from planner algorithm
  clearTimeout(estimateDebounceTimer);
  estimateDebounceTimer = setTimeout(() => {
    fetchPlanEstimate(availability, startDate);
  }, 80);
}

// Preset availability configurations
function applyPreset(name) {
  const presets = {
    standard: { Monday: 2.0, Tuesday: 2.0, Wednesday: 2.0, Thursday: 2.0, Friday: 2.0, Saturday: 4.0, Sunday: 4.0 },
    pro: { Monday: 1.5, Tuesday: 1.5, Wednesday: 1.5, Thursday: 1.5, Friday: 1.5, Saturday: 3.5, Sunday: 3.5 },
    weekend: { Monday: 0.0, Tuesday: 0.0, Wednesday: 2.0, Thursday: 0.0, Friday: 0.0, Saturday: 5.0, Sunday: 5.0 },
    daily: { Monday: 2.0, Tuesday: 2.0, Wednesday: 2.0, Thursday: 2.0, Friday: 2.0, Saturday: 2.0, Sunday: 2.0 }
  };

  const p = presets[name];
  if (!p) return;

  DAYS.forEach(d => {
    const hrs = p[d] || 0.0;
    const check = document.getElementById(`check-${d}`);
    const input = document.getElementById(`input-${d}`) || document.getElementById(`slider-${d}`);

    if (hrs > 0) {
      check.checked = true;
      if (input) input.value = hrs.toFixed(1);
    } else {
      check.checked = false;
      if (input) input.value = "1.0";
    }
    toggleDayEnabled(d);
    syncHours(d, input ? input.value : hrs);
  });
  showToast(`Applied preset: ${name}`);
}

function syncFormWithSavedAvailability() {
  if (!appState.plan || !appState.plan.weekly_availability) return;
  const avail = appState.plan.weekly_availability;

  if (appState.plan.start_date) {
    const startDateInput = document.getElementById("plan-start-date");
    if (startDateInput) startDateInput.value = appState.plan.start_date;
  }

  if (appState.plan.target_completion_date) {
    const formatted = formatDisplayDate(appState.plan.target_completion_date, true);
    const summaryEndDate = document.getElementById("summary-end-date");
    const planEndDate = document.getElementById("plan-end-date");
    const summaryEstWeeks = document.getElementById("summary-est-weeks");

    if (summaryEndDate) summaryEndDate.textContent = formatted;
    if (planEndDate) {
      const studyDaysText = appState.plan.total_study_days ? ` (${appState.plan.total_study_days} study days)` : "";
      planEndDate.value = `${formatted}${studyDaysText}`;
    }
    if (summaryEstWeeks && appState.plan.total_calendar_days) {
      const weeks = Math.round(appState.plan.total_calendar_days / 7.0);
      summaryEstWeeks.textContent = `~${weeks} Weeks (${appState.plan.total_calendar_days} days)`;
    }
  }

  DAYS.forEach(d => {
    const hrs = parseFloat(avail[d] !== undefined ? avail[d] : 0.0);
    const check = document.getElementById(`check-${d}`);
    const input = document.getElementById(`input-${d}`) || document.getElementById(`slider-${d}`);

    if (hrs > 0) {
      check.checked = true;
      if (input) input.value = hrs.toFixed(1);
    } else {
      check.checked = false;
      if (input) input.value = "1.0";
    }
    toggleDayEnabled(d);
    syncHours(d, input ? input.value : hrs);
  });
}

// Handle Create Plan Form Submission
async function handleCreatePlan(e) {
  e.preventDefault();

  const availability = {};
  DAYS.forEach(d => {
    const check = document.getElementById(`check-${d}`);
    const input = document.getElementById(`input-${d}`) || document.getElementById(`slider-${d}`);
    if (check && check.checked && input) {
      availability[d] = Math.max(0.0, parseFloat(input.value) || 0.0);
    } else {
      availability[d] = 0.0;
    }
  });

  const totalHrs = Object.values(availability).reduce((a, b) => a + b, 0);
  if (totalHrs <= 0) {
    showToast("Please enable at least one day with hours > 0", true);
    return;
  }

  const startDate = document.getElementById("plan-start-date").value || appState.todayDate;
  const btn = document.getElementById("btn-submit-plan");
  btn.disabled = true;
  btn.textContent = "Generating Schedule...";

  try {
    const res = await fetch("/api/create-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weekly_availability: availability,
        start_date: startDate
      })
    });
    const data = await res.json();

    if (data.success) {
      showToast("Plan created successfully! Let's get started!");
      await loadPlanData();
      switchTab("tab-today");
    } else {
      showToast(data.error || "Failed to generate plan", true);
    }
  } catch (err) {
    console.error("Error creating plan:", err);
    showToast("Server error while generating plan", true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Generate & Start Study Plan`;
  }
}

// Tab Switching
function switchTab(tabId) {
  appState.activeTab = tabId;
  document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });

  const targetPane = document.getElementById(tabId);
  if (targetPane) targetPane.classList.add("active");

  if (tabId === "tab-topics") {
    renderTopicsView();
  }
}

// Modals: Pause, Resume, Realign, Reset
function closeModals() {
  document.querySelectorAll(".modal-overlay").forEach(m => m.style.display = "none");
}

function openPauseModal() {
  document.getElementById("modal-pause").style.display = "grid";
}

async function confirmPause() {
  closeModals();
  try {
    const res = await fetch("/api/pause", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("Plan paused. Enjoy your break!");
      await loadPlanData();
    }
  } catch (err) {
    showToast("Failed to pause plan", true);
  }
}

function openResumeModal() {
  const resumeInput = document.getElementById("resume-start-date");
  if (resumeInput) resumeInput.value = appState.todayDate;
  document.getElementById("modal-resume").style.display = "grid";
}

async function confirmResume() {
  const resumeDate = document.getElementById("resume-start-date").value || appState.todayDate;
  closeModals();

  try {
    const res = await fetch("/api/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_date: resumeDate })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Welcome back! Remaining schedule updated.");
      await loadPlanData();
      switchTab("tab-today");
    } else {
      showToast(data.error || "Failed to resume plan", true);
    }
  } catch (err) {
    showToast("Error resuming plan", true);
  }
}

function openRealignModal() {
  const realignInput = document.getElementById("realign-from-date");
  if (realignInput) realignInput.value = appState.todayDate;
  document.getElementById("modal-realign").style.display = "grid";
}

async function confirmRealign() {
  const fromDate = document.getElementById("realign-from-date").value || appState.todayDate;
  closeModals();

  try {
    const res = await fetch("/api/realign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_date: fromDate })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Schedule re-aligned from ${fromDate}`);
      await loadPlanData();
      switchTab("tab-today");
    } else {
      showToast(data.error || "Failed to realign schedule", true);
    }
  } catch (err) {
    showToast("Error realigning schedule", true);
  }
}

function openResetProgressModal() {
  const startDateInput = document.getElementById("reset-progress-start-date");
  if (startDateInput) startDateInput.value = appState.todayDate;

  const restartScheduleCheckbox = document.getElementById("reset-progress-restart-schedule");
  if (restartScheduleCheckbox) {
    restartScheduleCheckbox.checked = true;
    toggleResetScheduleOption(true);
  }

  const progressInfo = document.getElementById("reset-progress-current-info");
  if (progressInfo) {
    if (appState.metrics && appState.metrics.completed_problems > 0) {
      progressInfo.innerHTML = `<strong>Current Progress:</strong> ${appState.metrics.completed_problems} of ${appState.metrics.total_problems} problems solved (${appState.metrics.completion_percent}% complete across ${appState.metrics.completed_study_days} study days).`;
    } else {
      progressInfo.innerHTML = `<strong>Current Progress:</strong> 0 of 495 problems solved (0% complete).`;
    }
  }

  document.getElementById("modal-reset-progress").style.display = "grid";
}

function toggleResetScheduleOption(checked) {
  const dateInput = document.getElementById("reset-progress-start-date");
  if (dateInput) {
    dateInput.disabled = !checked;
    dateInput.style.opacity = checked ? "1" : "0.5";
  }
}

async function confirmResetProgress() {
  const restartScheduleCheckbox = document.getElementById("reset-progress-restart-schedule");
  const restartSchedule = restartScheduleCheckbox ? restartScheduleCheckbox.checked : true;
  const startDate = document.getElementById("reset-progress-start-date") ? document.getElementById("reset-progress-start-date").value : appState.todayDate;

  closeModals();

  try {
    const res = await fetch("/api/reset-progress", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        restart_schedule: restartSchedule,
        start_date: startDate
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Progress reset to 0! Ready to start fresh.");
      await loadPlanData();
      switchTab("tab-today");
    } else {
      showToast(data.error || "Failed to reset progress", true);
    }
  } catch (err) {
    showToast("Error resetting progress", true);
  }
}

function openResetModal() {
  document.getElementById("modal-reset").style.display = "grid";
}

async function confirmReset() {
  closeModals();
  try {
    const res = await fetch("/api/reset", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("Plan reset successfully");
      await loadPlanData();
      switchTab("tab-setup");
    }
  } catch (err) {
    showToast("Error resetting plan", true);
  }
}

// Toast helper
let toastTimeout;
function showToast(msg, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;

  clearTimeout(toastTimeout);
  toast.textContent = msg;
  toast.style.borderColor = isError ? "var(--danger)" : "var(--success)";
  toast.classList.add("show");

  toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 3200);
}

// Utility: HTML escape
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
