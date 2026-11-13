/**
 * AI Software Engineering Copilot — Vanilla Client-Side Application
 * Handles modular routing, telemetry, AST testing, code reviews, and GitHub inspection.
 */

// Utility selector
const $ = (id) => document.getElementById(id);

// State management
const state = {
  currentView: 'dashboard',
  health: null,
  activeRepoUrl: '',
  historyItems: [],
  activeFilter: 'all',
  selectedModalTask: null
};

// ==========================================
// Toast & Utility Helpers
// ==========================================

let toastTimeout;
function notify(message, type = 'info') {
  const toast = $('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast show ${type}`;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.className = 'toast';
  }, 4000);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return str;
  return str.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c]));
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function copyToClipboard(text, btnElement = null) {
  if (!navigator.clipboard) {
    notify('Clipboard access not permitted in browser.', 'error');
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    notify('Copied to clipboard!', 'success');
    if (btnElement) {
      const orig = btnElement.textContent;
      btnElement.textContent = '✓ Copied!';
      setTimeout(() => { btnElement.textContent = orig; }, 2000);
    }
  }).catch(() => {
    notify('Failed to copy to clipboard.', 'error');
  });
}

function downloadFile(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  notify(`Downloaded ${filename}`, 'success');
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  let data;
  try {
    data = await response.json();
  } catch (err) {
    throw new Error(`Failed to parse server response (${response.status})`);
  }
  if (!response.ok) {
    const errorDetail = data && data.detail ? data.detail : `Server error (${response.status})`;
    throw new Error(errorDetail);
  }
  return data;
}

// ==========================================
// Routing and View Controller
// ==========================================

const VIEW_TITLES = {
  dashboard: 'Dashboard',
  generator: 'Code Generator',
  testing: 'Automated Testing',
  review: 'Code Reviewer',
  github: 'GitHub Assistant',
  history: 'Task History'
};

function switchView(viewName) {
  if (!VIEW_TITLES[viewName]) viewName = 'dashboard';
  state.currentView = viewName;

  // Update DOM Views
  document.querySelectorAll('.view').forEach((el) => {
    el.classList.toggle('active', el.id === `view-${viewName}`);
  });

  // Update Nav Items
  document.querySelectorAll('.nav-item').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === viewName);
  });

  // Update Breadcrumb & URL Hash
  const title = VIEW_TITLES[viewName];
  if ($('crumbTitle')) $('crumbTitle').textContent = title;
  window.history.replaceState(null, '', `#${viewName}`);

  // Close Mobile Nav if open
  if ($('sidebar')) $('sidebar').classList.remove('open');

  // Trigger lazy-load view data
  if (viewName === 'dashboard') loadDashboardData();
  if (viewName === 'history') loadHistoryData();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ==========================================
// 1. Health Diagnostics & Startup
// ==========================================

async function checkSystemHealth() {
  try {
    const health = await api('/api/health');
    state.health = health;

    // Update Topbar
    if ($('topbar-status-badge')) {
      $('topbar-status-badge').innerHTML = '<span class="pulse-dot"></span> System Online';
    }
    if ($('topbar-ai-badge')) {
      $('topbar-ai-badge').textContent = health.mode || 'Demo Mode';
      $('topbar-ai-badge').className = health.ai_configured ? 'badge badge-purple' : 'badge badge-outline';
    }

    // Update Sidebar
    if ($('sidebar-engine-name')) {
      $('sidebar-engine-name').textContent = health.ai_engine.provider;
    }
    if ($('sidebar-engine-mode')) {
      $('sidebar-engine-mode').textContent = health.ai_engine.model;
    }

    // Update Mode Badges across app
    if ($('genModeBadge')) {
      $('genModeBadge').textContent = health.mode || 'DEMO MODE';
    }
    if ($('reviewEngineBadge')) {
      $('reviewEngineBadge').textContent = health.ai_configured ? 'LIVE LLM AUDIT' : 'LOCAL HEURISTIC ENGINE';
    }

    if (health.ai_configured && $('dashboard-env-banner')) {
      $('dashboard-env-banner').innerHTML = `
        <div class="info-banner-icon">✨</div>
        <div class="info-banner-content">
          <strong>AI Provider Active (${escapeHtml(health.ai_engine.provider)})</strong>
          <p>Configured with model: <code>${escapeHtml(health.ai_engine.model)}</code>. Generates custom AI code and reviews.</p>
        </div>
        <span class="badge badge-purple">LIVE AI ACTIVE</span>
      `;
    }
  } catch (err) {
    if ($('topbar-status-badge')) {
      $('topbar-status-badge').innerHTML = '<span class="pulse-dot" style="background:red"></span> Connecting...';
      $('topbar-status-badge').className = 'badge badge-danger';
    }
  }
}

// ==========================================
// 2. Dashboard Telemetry & Activities
// ==========================================

async function loadDashboardData() {
  try {
    const data = await api('/api/dashboard');
    if ($('stat-total-tasks')) $('stat-total-tasks').textContent = data.total_tasks || 0;
    if ($('stat-generations')) $('stat-generations').textContent = data.code_generations || 0;
    if ($('stat-tests')) $('stat-tests').textContent = data.tests_executed || 0;
    if ($('stat-reviews')) $('stat-reviews').textContent = data.code_reviews || 0;

    renderRecentActivities(data.recent_activities || []);
  } catch (err) {
    notify('Failed to refresh dashboard telemetry: ' + err.message, 'error');
  }
}

function renderRecentActivities(items) {
  const container = $('recentActivityContainer');
  if (!container) return;

  if (!items.length) {
    container.innerHTML = '<div class="empty-state">No recorded tasks yet. Try generating code or running automated tests!</div>';
    return;
  }

  const moduleIcons = {
    generate: { symbol: '⚡', color: 'purple' },
    test: { symbol: '✓', color: 'green' },
    review: { symbol: '◉', color: 'amber' },
    github: { symbol: '🐙', color: 'blue' }
  };

  container.innerHTML = items.map((t) => {
    const icon = moduleIcons[t.module] || { symbol: '•', color: 'blue' };
    return `
      <div class="activity-row">
        <div class="activity-icon stat-icon-wrapper ${icon.color}">${icon.symbol}</div>
        <div class="activity-content">
          <div class="activity-title">${escapeHtml(t.title)}</div>
          <div class="activity-snippet">${escapeHtml(t.description)}</div>
        </div>
        <span class="activity-meta">${formatDate(t.created_at)}</span>
      </div>
    `;
  }).join('');
}

// ==========================================
// 3. AI Code Generator Logic
// ==========================================

function initGeneratorModule() {
  // Preset chips
  document.querySelectorAll('.preset-chip[data-prompt]').forEach((chip) => {
    chip.addEventListener('click', () => {
      $('genPrompt').value = chip.dataset.prompt;
      if (chip.dataset.lang) $('genLanguage').value = chip.dataset.lang;
      $('genPrompt').focus();
    });
  });

  const genBtn = $('generateCodeBtn');
  if (!genBtn) return;

  genBtn.addEventListener('click', async () => {
    const prompt = $('genPrompt').value.trim();
    const language = $('genLanguage').value;
    const style = $('genStyle').value;

    if (!prompt) {
      notify('Please enter your programming requirement prompt.', 'error');
      $('genPrompt').focus();
      return;
    }

    genBtn.disabled = true;
    genBtn.textContent = 'Generating code...';

    try {
      const data = await api('/api/generate', {
        method: 'POST',
        body: JSON.stringify({ prompt, language, style })
      });

      // Display Results
      $('genResultContainer').classList.remove('hidden');
      $('genResultCode').textContent = data.code;
      $('genExplanationText').textContent = data.explanation || data.message;
      $('genResultEngineTag').textContent = `${data.provider} (${data.mode})`;

      const extensions = { Python: 'py', JavaScript: 'js', 'C++': 'cpp', Java: 'java' };
      const ext = extensions[language] || 'txt';
      const filename = `generated_${language.toLowerCase()}_solution.${ext}`;
      $('genResultFilename').textContent = filename;

      // Copy & Download handlers
      $('copyGenCodeBtn').onclick = (e) => copyToClipboard(data.code, e.target);
      $('downloadGenCodeBtn').onclick = () => downloadFile(filename, data.code);

      notify('Code generated and saved to task history!', 'success');
      loadDashboardData();
    } catch (err) {
      notify('Code generation failed: ' + err.message, 'error');
    } finally {
      genBtn.disabled = false;
      genBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        Generate Code
      `;
    }
  });
}

// ==========================================
// 4. Automated Testing Logic
// ==========================================

function initTestingModule() {
  // Preset Snippet Buttons
  if ($('presetTestMath')) {
    $('presetTestMath').addEventListener('click', () => {
      $('testSourceCode').value = `def factorial(n: int) -> int:
    """Calculate factorial for non-negative integers."""
    if n < 0:
        raise ValueError("n must be non-negative")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
`;
      $('testSuiteCode').value = '';
    });
  }

  if ($('presetTestString')) {
    $('presetTestString').addEventListener('click', () => {
      $('testSourceCode').value = `def format_user_name(first: str, last: str) -> str:
    """Format and capitalize full name."""
    clean_first = first.strip().capitalize()
    clean_last = last.strip().capitalize()
    return f"{clean_first} {clean_last}"
`;
      $('testSuiteCode').value = '';
    });
  }

  if ($('presetTestBuggy')) {
    $('presetTestBuggy').addEventListener('click', () => {
      $('testSourceCode').value = `def divide_numbers(a: int, b: int) -> float:
    # Buggy: fails to check for zero denominator
    return a / b
`;
      $('testSuiteCode').value = '';
    });
  }

  if ($('presetTestDisallowed')) {
    $('presetTestDisallowed').addEventListener('click', () => {
      $('testSourceCode').value = `import os
# Malicious attempt to test security guardrail
def dangerous_routine():
    os.system("echo security test")
    return True
`;
      $('testSuiteCode').value = '';
    });
  }

  // 1. Auto-Generate Test Suite via AST
  const genSuiteBtn = $('generateTestSuiteBtn');
  if (genSuiteBtn) {
    genSuiteBtn.addEventListener('click', async () => {
      const code = $('testSourceCode').value.trim();
      if (!code) {
        notify('Please enter Python function code first.', 'error');
        $('testSourceCode').focus();
        return;
      }

      genSuiteBtn.disabled = true;
      genSuiteBtn.textContent = 'Synthesizing AST tests...';

      try {
        const data = await api('/api/test/generate-tests', {
          method: 'POST',
          body: JSON.stringify({ code })
        });
        $('testSuiteCode').value = data.generated_tests;
        notify(`Auto-generated test suite for functions: ${data.functions_detected.join(', ')}`, 'success');
      } catch (err) {
        notify('Failed to generate tests: ' + err.message, 'error');
      } finally {
        genSuiteBtn.disabled = false;
        genSuiteBtn.textContent = '✦ Auto-Generate Unit Tests (AST)';
      }
    });
  }

  // 2. Run Tests in Isolated Sandbox
  const runTestsBtn = $('runTestsBtn');
  if (runTestsBtn) {
    runTestsBtn.addEventListener('click', async () => {
      const code = $('testSourceCode').value.trim();
      const test_code = $('testSuiteCode').value.trim();
      const allow_execution = $('allowExecutionToggle').checked;

      if (!code) {
        notify('Please enter Python source code.', 'error');
        return;
      }

      runTestsBtn.disabled = true;
      runTestsBtn.textContent = 'Executing in Sandbox...';

      try {
        const data = await api('/api/test/run', {
          method: 'POST',
          body: JSON.stringify({ code, test_code: test_code || null, allow_execution })
        });

        $('testResultContainer').classList.remove('hidden');

        // Security check alert
        const alertBox = $('testSecurityAlert');
        const violationsList = $('testSecurityViolationsList');
        if (data.security_blocked) {
          alertBox.classList.remove('hidden');
          violationsList.innerHTML = (data.violations || []).map((v) => `<li>${escapeHtml(v)}</li>`).join('');
          $('testResultStatusBadge').className = 'badge badge-danger';
          $('testResultStatusBadge').textContent = 'BLOCKED BY GUARDRAIL';
        } else {
          alertBox.classList.add('hidden');
          const passedAll = data.failed === 0 && data.passed > 0;
          $('testResultStatusBadge').className = passedAll ? 'badge badge-success' : 'badge badge-warning';
          $('testResultStatusBadge').textContent = passedAll ? 'ALL PASSED' : 'TESTS FAILED';
        }

        $('testPassedCount').textContent = data.passed || 0;
        $('testFailedCount').textContent = data.failed || 0;
        $('testDuration').textContent = `${data.duration_ms || 0}ms`;
        $('testConsoleOutput').textContent = data.output || data.message || 'No process output.';

        notify('Testing cycle completed!', 'success');
        loadDashboardData();
      } catch (err) {
        notify('Testing error: ' + err.message, 'error');
      } finally {
        runTestsBtn.disabled = false;
        runTestsBtn.textContent = '✓ Run Tests in Sandbox';
      }
    });
  }
}

// ==========================================
// 5. AI Code Reviewer Logic
// ==========================================

function initReviewerModule() {
  // Preset Snippet Buttons
  if ($('loadReviewVulnerable')) {
    $('loadReviewVulnerable').addEventListener('click', () => {
      $('reviewLanguage').value = 'Python';
      $('reviewSourceCode').value = `import os

# Sensitive credentials hardcoded
API_SECRET_KEY = "sk_live_9482910394857102"
DATABASE_PASSWORD = "SuperSecretPassword123"

def process_user_query(user_input):
    try:
        # Dangerous dynamic execution
        eval("print('Debug: ' + user_input)")
        query = "SELECT * FROM users WHERE name = '" + user_input + "'"
    except:
        # Bare except masks critical errors
        pass
`;
    });
  }

  if ($('loadReviewJs')) {
    $('loadReviewJs').addEventListener('click', () => {
      $('reviewLanguage').value = 'JavaScript';
      $('reviewSourceCode').value = `// Insecure JavaScript with loose equality and XSS
var globalCounter = 0;

function renderUserWelcome(userProfile) {
  if (userProfile.role == "admin") {
    // XSS vulnerability through unescaped innerHTML
    document.getElementById("profile").innerHTML = "<h1>Welcome " + userProfile.name + "</h1>";
  }
}
`;
    });
  }

  if ($('loadReviewCpp')) {
    $('loadReviewCpp').addEventListener('click', () => {
      $('reviewLanguage').value = 'C++';
      $('reviewSourceCode').value = `#include <iostream>
#include <cstring>

void copyBuffer(const char* input) {
    char destination[16];
    // Dangerous unbounded buffer copy
    strcpy(destination, input);
    
    int* ptr = new int[100];
    // Memory leak: ptr is never deleted
}
`;
    });
  }

  if ($('loadReviewClean')) {
    $('loadReviewClean').addEventListener('click', () => {
      $('reviewLanguage').value = 'Python';
      $('reviewSourceCode').value = `"""
Clean, well-typed implementation of a binary search tree node.
"""
from typing import Optional, Any

class TreeNode:
    """Represents a node in a binary search tree."""
    def __init__(self, key: int, value: Any = None) -> None:
        self.key: int = key
        self.value: Any = value
        self.left: Optional['TreeNode'] = None
        self.right: Optional['TreeNode'] = None

    def is_leaf(self) -> bool:
        """Return True if node has no children."""
        return self.left is None and self.right is None
`;
    });
  }

  const reviewBtn = $('runReviewBtn');
  if (!reviewBtn) return;

  reviewBtn.addEventListener('click', async () => {
    const code = $('reviewSourceCode').value.trim();
    const language = $('reviewLanguage').value;

    if (!code) {
      notify('Please paste code to review.', 'error');
      $('reviewSourceCode').focus();
      return;
    }

    reviewBtn.disabled = true;
    reviewBtn.textContent = 'Auditing source code...';

    try {
      const data = await api('/api/review', {
        method: 'POST',
        body: JSON.stringify({ code, language })
      });

      // Show Result Container
      $('reviewResultContainer').classList.remove('hidden');

      // Update Scores & Metrics
      $('reviewScoreNumber').textContent = data.score;
      $('reviewGradeBadge').textContent = `Grade ${data.grade}`;
      $('reviewScoreStatus').textContent = data.score >= 80 ? 'Good Architecture' : data.score >= 60 ? 'Needs Attention' : 'High Risk Code';

      const metrics = data.metrics || {};
      $('metricCritical').textContent = metrics.critical || 0;
      $('metricHigh').textContent = metrics.high || 0;
      $('metricMedium').textContent = metrics.medium || 0;
      $('metricLow').textContent = metrics.low || 0;

      $('findingsSummaryText').textContent = data.summary;

      // Render Findings
      renderFindings(data.findings || []);
      notify(`Review complete! Quality score: ${data.score}/100`, 'success');
      loadDashboardData();
    } catch (err) {
      notify('Review failed: ' + err.message, 'error');
    } finally {
      reviewBtn.disabled = false;
      reviewBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        Run Deep Code Review
      `;
    }
  });
}

function renderFindings(findings) {
  const container = $('findingsList');
  if (!container) return;

  if (!findings.length) {
    container.innerHTML = '<div class="empty-state">No issues flagged. Clean code!</div>';
    return;
  }

  container.innerHTML = findings.map((f) => {
    const sevClass = (f.severity || 'low').toLowerCase();
    const lineLabel = f.line ? `<span class="finding-line">Line ${f.line}</span>` : '';
    const fixSection = f.suggested_fix ? `
      <div class="finding-fix">
        <span class="fix-label">Suggested Improvement:</span>
        <div class="fix-code">${escapeHtml(f.suggested_fix)}</div>
      </div>
    ` : '';

    return `
      <div class="finding-card">
        <div class="finding-header">
          <span class="metric-badge ${sevClass}">${escapeHtml(f.severity)}</span>
          <span class="finding-title">${escapeHtml(f.title)}</span>
          ${lineLabel}
        </div>
        <div class="finding-explanation">${escapeHtml(f.explanation)}</div>
        ${fixSection}
      </div>
    `;
  }).join('');
}

// ==========================================
// 6. GitHub Assistant Logic
// ==========================================

function initGitHubModule() {
  // Preset Chips
  document.querySelectorAll('.preset-chip[data-repo]').forEach((chip) => {
    chip.addEventListener('click', () => {
      $('githubRepoUrl').value = chip.dataset.repo;
      $('inspectRepoBtn').click();
    });
  });

  // Tab navigation
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetTab = btn.dataset.tab;
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${targetTab}`));

      // Load readme or pulls if clicked
      if (targetTab === 'readme' && state.activeRepoUrl) loadReadme(state.activeRepoUrl);
      if (targetTab === 'pulls' && state.activeRepoUrl) loadPulls(state.activeRepoUrl);
    });
  });

  const inspectBtn = $('inspectRepoBtn');
  if (!inspectBtn) return;

  inspectBtn.addEventListener('click', async () => {
    const url = $('githubRepoUrl').value.trim();
    if (!url) {
      notify('Please enter a public GitHub repository URL.', 'error');
      $('githubRepoUrl').focus();
      return;
    }

    inspectBtn.disabled = true;
    inspectBtn.textContent = 'Querying GitHub API...';

    try {
      const data = await api('/api/github/inspect', {
        method: 'POST',
        body: JSON.stringify({ url })
      });

      state.activeRepoUrl = url;
      $('githubResultContainer').classList.remove('hidden');

      // Populate Header Telemetry
      $('ghRepoName').textContent = data.repository;
      $('ghRepoDesc').textContent = data.description;
      $('ghRepoLink').href = data.html_url;
      $('ghStars').textContent = (data.stars || 0).toLocaleString();
      $('ghForks').textContent = (data.forks || 0).toLocaleString();
      $('ghIssues').textContent = (data.open_issues || 0).toLocaleString();
      $('ghLanguage').textContent = data.language || 'Mixed';
      $('ghLicense').textContent = data.license || 'None';
      $('ghBranch').textContent = data.default_branch || 'main';

      // Populate Files
      renderFilesList(data.files || [], url);

      // Populate Commits
      renderCommitsList(data.recent_commits || []);

      notify(`Loaded repository ${data.repository}!`, 'success');
      loadDashboardData();
    } catch (err) {
      notify('GitHub error: ' + err.message, 'error');
    } finally {
      inspectBtn.disabled = false;
      inspectBtn.innerHTML = `
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        Inspect Repository
      `;
    }
  });

  // Copy Preview Button
  if ($('copyFilePreviewBtn')) {
    $('copyFilePreviewBtn').addEventListener('click', (e) => {
      copyToClipboard($('ghPreviewContent').textContent, e.target);
    });
  }
}

function renderFilesList(files, repoUrl) {
  const container = $('ghFilesList');
  if ($('ghFilesCount')) $('ghFilesCount').textContent = files.length;
  if (!container) return;

  if (!files.length) {
    container.innerHTML = '<div class="empty-state">No root files found.</div>';
    return;
  }

  container.innerHTML = files.map((f) => {
    const icon = f.type === 'dir' ? '📁' : '📄';
    const size = f.size ? `${Math.round(f.size / 1024)} KB` : '';
    return `
      <div class="file-row" data-path="${escapeHtml(f.path)}" data-type="${f.type}">
        <span class="file-name">${icon} ${escapeHtml(f.name)}</span>
        <span class="file-size">${size}</span>
      </div>
    `;
  }).join('');

  // Click on file to view preview
  container.querySelectorAll('.file-row').forEach((row) => {
    row.addEventListener('click', async () => {
      container.querySelectorAll('.file-row').forEach((r) => r.classList.remove('active'));
      row.classList.add('active');

      const path = row.dataset.path;
      const type = row.dataset.type;

      if (type === 'dir') {
        $('ghPreviewFilename').textContent = `${path}/ (Directory)`;
        $('ghPreviewContent').textContent = 'Subdirectory exploration via REST API is available on GitHub.';
        $('copyFilePreviewBtn').classList.add('hidden');
        return;
      }

      $('ghPreviewFilename').textContent = path;
      $('ghPreviewContent').textContent = 'Fetching file from GitHub...';
      $('copyFilePreviewBtn').classList.remove('hidden');

      try {
        const fileData = await api('/api/github/file', {
          method: 'POST',
          body: JSON.stringify({ url: repoUrl, path })
        });
        $('ghPreviewContent').textContent = fileData.content;
      } catch (err) {
        $('ghPreviewContent').textContent = 'Failed to load file: ' + err.message;
      }
    });
  });
}

async function loadReadme(url) {
  const readmePre = $('ghReadmeContent');
  if (!readmePre) return;
  readmePre.textContent = 'Fetching README.md...';

  try {
    const data = await api('/api/github/readme', {
      method: 'POST',
      body: JSON.stringify({ url })
    });
    readmePre.textContent = data.content;
  } catch (err) {
    readmePre.textContent = 'Could not load README: ' + err.message;
  }
}

function renderCommitsList(commits) {
  const container = $('ghCommitsList');
  if (!container) return;

  if (!commits.length) {
    container.innerHTML = '<div class="empty-state">No recent commits returned.</div>';
    return;
  }

  container.innerHTML = commits.map((c) => `
    <div class="commit-card">
      <div class="commit-header">
        <span class="commit-sha">${escapeHtml(c.sha)}</span>
        <span class="activity-meta">${formatDate(c.date)}</span>
      </div>
      <div class="activity-title">${escapeHtml(c.message)}</div>
      <div class="helper-text">Committed by: <b>${escapeHtml(c.author)}</b></div>
    </div>
  `).join('');
}

async function loadPulls(url) {
  const container = $('ghPullsList');
  if (!container) return;
  container.innerHTML = '<div class="empty-state">Loading open pull requests...</div>';

  try {
    const data = await api('/api/github/pulls', {
      method: 'POST',
      body: JSON.stringify({ url })
    });

    if (!data.pull_requests || !data.pull_requests.length) {
      container.innerHTML = '<div class="empty-state">No open pull requests found for this repository.</div>';
      return;
    }

    container.innerHTML = data.pull_requests.map((pr) => {
      const review = pr.review_analysis || {};
      const checklistItems = (review.checklist || []).map((item) => `
        <div class="pr-checklist-item">
          <span>${escapeHtml(item.item)}</span>
          <span class="badge ${item.status === 'Pass' ? 'badge-success' : 'badge-warning'}">${escapeHtml(item.status)}</span>
        </div>
      `).join('');

      return `
        <div class="pr-card">
          <div class="pr-header">
            <div>
              <strong>#${pr.number} ${escapeHtml(pr.title)}</strong>
              <div class="helper-text">Author: ${escapeHtml(pr.author)} • ${formatDate(pr.created_at)}</div>
            </div>
            <a href="${escapeHtml(pr.html_url)}" target="_blank" rel="noopener noreferrer" class="button button-sm button-outline">Open PR ↗</a>
          </div>
          <div class="pr-checklist">
            <div class="helper-text" style="font-weight: 600; margin-bottom: 6px;">Automated Review Checklist:</div>
            ${checklistItems}
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Failed to load Pull Requests: ${escapeHtml(err.message)}</div>`;
  }
}

// ==========================================
// 7. Task History Module Logic
// ==========================================

function initHistoryModule() {
  // Filter tabs
  $('historyFilterTabs').querySelectorAll('.filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      $('historyFilterTabs').querySelectorAll('.filter-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeFilter = btn.dataset.filter;
      loadHistoryData();
    });
  });

  // Search input
  let searchTimer;
  $('historySearchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      loadHistoryData();
    }, 300);
  });

  // Refresh
  if ($('refreshHistoryBtn')) {
    $('refreshHistoryBtn').addEventListener('click', loadHistoryData);
  }

  // Clear All
  if ($('clearAllHistoryBtn')) {
    $('clearAllHistoryBtn').addEventListener('click', async () => {
      if (!confirm('Are you sure you want to delete all saved task history?')) return;
      try {
        await api('/api/history', { method: 'DELETE' });
        notify('All task history cleared.', 'success');
        loadHistoryData();
        loadDashboardData();
      } catch (err) {
        notify('Failed to clear history: ' + err.message, 'error');
      }
    });
  }
}

async function loadHistoryData() {
  const container = $('historyTableContainer');
  if (!container) return;

  const moduleFilter = state.activeFilter !== 'all' ? `&module=${state.activeFilter}` : '';
  const searchVal = $('historySearchInput').value.trim();
  const searchParam = searchVal ? `&search=${encodeURIComponent(searchVal)}` : '';

  try {
    const tasks = await api(`/api/history?limit=100${moduleFilter}${searchParam}`);
    state.historyItems = tasks;

    if (!tasks.length) {
      container.innerHTML = '<div class="empty-state">No tasks found matching your filter criteria.</div>';
      return;
    }

    container.innerHTML = `
      <table class="history-table">
        <thead>
          <tr>
            <th>Module</th>
            <th>Title / Action</th>
            <th>Description Preview</th>
            <th>Language</th>
            <th>Created At</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${tasks.map((t) => `
            <tr>
              <td><span class="badge badge-purple">${escapeHtml(t.module.toUpperCase())}</span></td>
              <td><strong>${escapeHtml(t.title)}</strong></td>
              <td><div class="activity-snippet">${escapeHtml(t.description)}</div></td>
              <td>${escapeHtml(t.language || '—')}</td>
              <td><span class="activity-meta" style="margin:0">${formatDate(t.created_at)}</span></td>
              <td>
                <div class="history-actions">
                  <button class="button button-sm button-outline" onclick="openTaskModal(${t.id})">Inspect</button>
                  <button class="button button-sm button-ghost" onclick="reopenTaskDirectly(${t.id})">Reopen</button>
                  <button class="button button-sm button-danger" onclick="deleteHistoryItem(${t.id})">Delete</button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty-state">Failed to load history: ${escapeHtml(err.message)}</div>`;
  }
}

async function deleteHistoryItem(id) {
  try {
    await api(`/api/history/${id}`, { method: 'DELETE' });
    notify('Task deleted successfully.', 'success');
    loadHistoryData();
    loadDashboardData();
  } catch (err) {
    notify('Failed to delete task: ' + err.message, 'error');
  }
}

async function reopenTaskDirectly(id) {
  try {
    const task = await api(`/api/history/${id}`);
    const module = task.module;

    if (module === 'generate') {
      switchView('generator');
      $('genPrompt').value = task.description || '';
      if (task.language) $('genLanguage').value = task.language;
      if (task.result && task.result.code) {
        $('genResultContainer').classList.remove('hidden');
        $('genResultCode').textContent = task.result.code;
        $('genExplanationText').textContent = task.result.explanation || task.result.message || '';
      }
    } else if (module === 'test') {
      switchView('testing');
      const input = task.input_data || {};
      $('testSourceCode').value = input.code || task.description || '';
      if (input.test_code) $('testSuiteCode').value = input.test_code;
    } else if (module === 'review') {
      switchView('review');
      const input = task.input_data || {};
      $('reviewSourceCode').value = input.code || task.description || '';
      if (task.language) $('reviewLanguage').value = task.language;
    } else if (module === 'github') {
      switchView('github');
      $('githubRepoUrl').value = task.description || '';
      $('inspectRepoBtn').click();
    }
    notify(`Loaded task #${id} into ${VIEW_TITLES[module]}`, 'success');
  } catch (err) {
    notify('Failed to reopen task: ' + err.message, 'error');
  }
}

function openTaskModal(id) {
  const task = state.historyItems.find((t) => t.id === id);
  if (!task) return;
  state.selectedModalTask = task;

  $('modalTitle').textContent = `Task #${task.id}: ${task.title}`;
  $('modalMetaRow').innerHTML = `
    <span class="badge badge-purple">${escapeHtml(task.module.toUpperCase())}</span>
    <span class="badge badge-outline">${formatDate(task.created_at)}</span>
    ${task.language ? `<span class="badge badge-blue">${escapeHtml(task.language)}</span>` : ''}
  `;
  $('modalJsonCode').textContent = JSON.stringify(task, null, 2);
  $('taskDetailModal').classList.remove('hidden');

  $('modalCopyJsonBtn').onclick = (e) => {
    copyToClipboard(JSON.stringify(task, null, 2), e.target);
  };
  $('modalReopenBtn').onclick = () => {
    $('taskDetailModal').classList.add('hidden');
    reopenTaskDirectly(task.id);
  };
}

// Modal Close Handlers
if ($('modalCloseBtn')) {
  $('modalCloseBtn').addEventListener('click', () => {
    $('taskDetailModal').classList.add('hidden');
  });
}

window.addEventListener('click', (e) => {
  if (e.target === $('taskDetailModal')) {
    $('taskDetailModal').classList.add('hidden');
  }
});

// ==========================================
// 8. Application Bootstrap
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  // Setup Navigation Clicks
  document.querySelectorAll('[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  document.querySelectorAll('[data-go]').forEach((btn) => {
    btn.addEventListener('click', () => switchView(btn.dataset.go));
  });

  if ($('mobileToggle')) {
    $('mobileToggle').addEventListener('click', () => {
      $('sidebar').classList.toggle('open');
    });
  }

  if ($('refreshDashboardBtn')) {
    $('refreshDashboardBtn').addEventListener('click', loadDashboardData);
  }

  // Initialize Modules
  initGeneratorModule();
  initTestingModule();
  initReviewerModule();
  initGitHubModule();
  initHistoryModule();

  // Check health and load telemetry
  checkSystemHealth();
  loadDashboardData();

  // Check initial hash route
  const hash = window.location.hash.slice(1);
  if (hash && VIEW_TITLES[hash]) {
    switchView(hash);
  } else {
    switchView('dashboard');
  }
});
