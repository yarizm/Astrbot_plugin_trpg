(function () {
  "use strict";

  var currentScenarioId = null;
  var sessionsData = null;
  var bridge = null;

  // --- SVG Icons ---

  var ICONS = {
    success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    empty: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
  };

  // --- Utils ---

  function toast(msg, type) {
    var el = document.getElementById("toast");
    var icon = ICONS[type] || ICONS.info;
    el.innerHTML = icon + "<span>" + esc(msg) + "</span>";
    el.className = "toast toast-" + (type || "info") + " show";
    clearTimeout(el._timer);
    el._timer = setTimeout(function () {
      el.className = "toast";
    }, 3500);
  }

  function setLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      btn._origHtml = btn.innerHTML;
      btn.disabled = true;
      var text = btn.textContent.trim();
      btn.innerHTML = '<span class="spinner"></span> ' + esc(text);
    } else {
      btn.disabled = false;
      if (btn._origHtml) btn.innerHTML = btn._origHtml;
    }
  }

  function emptyHtml(text) {
    return '<div class="empty">' + ICONS.empty + "<p>" + esc(text) + "</p></div>";
  }

  function skeletonCards(count) {
    var html = "";
    for (var i = 0; i < (count || 6); i++) {
      html += '<div class="skeleton skeleton-card"></div>';
    }
    return html;
  }

  async function apiGet(endpoint, params) {
    try {
      return await bridge.apiGet(endpoint, params || {});
    } catch (e) {
      toast(e.message || "请求失败", "error");
      return null;
    }
  }

  async function apiPost(endpoint, body) {
    try {
      return await bridge.apiPost(endpoint, body || {});
    } catch (e) {
      toast(e.message || "请求失败", "error");
      return null;
    }
  }

  async function uploadFile(file) {
    var area = document.getElementById("upload-area");
    try {
      area.classList.add("uploading");
      await bridge.upload("trpg/web/scenarios/upload", file);
      toast("上传成功", "success");
      loadScenarios();
    } catch (e) {
      toast(e.message || "上传失败", "error");
    } finally {
      area.classList.remove("uploading");
    }
  }

  // --- Tabs ---

  document.querySelectorAll(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
      document.querySelectorAll(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
      if (btn.dataset.tab === "scenarios") loadScenarios();
      if (btn.dataset.tab === "sessions") loadSessions();
      if (btn.dataset.tab === "config") loadConfig();
    });
  });

  // --- Scenarios ---

  async function loadScenarios() {
    var list = document.getElementById("scenario-list");
    list.innerHTML = skeletonCards(6);

    var status = document.getElementById("status-filter").value;
    var params = {};
    if (status) params.status = status;
    var scenarios = await apiGet("trpg/web/scenarios", params);
    if (!scenarios) { list.innerHTML = emptyHtml("加载失败"); return; }

    if (scenarios.length === 0) {
      list.innerHTML = emptyHtml("暂无剧本，上传 Markdown 文件开始导入");
      return;
    }

    list.innerHTML = scenarios.map(function (s) {
      var tags = (s.tag_list || []).map(function (t) {
        return '<span class="tag">' + esc(t) + "</span>";
      }).join("");
      var badge = "badge-" + s.status;
      var statusLabel = { draft: "草稿", published: "已发布", archived: "已归档" }[s.status] || s.status;
      return '<div class="card scenario-card" data-id="' + s.id + '" data-status="' + s.status + '">' +
        '<div class="meta"><span class="badge ' + badge + '">' + statusLabel + "</span>" + tags + "</div>" +
        '<div class="card-title">' + esc(s.title) + "</div>" +
        '<div class="summary">' + esc(s.summary || "暂无简介") + "</div>" +
        '<div class="card-footer">' +
          '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg> ' +
          esc(s.recommended_players || "未填写") + "</div></div>";
    }).join("");

    list.querySelectorAll(".scenario-card").forEach(function (card) {
      card.addEventListener("click", function () {
        openScenarioDetail(parseInt(card.dataset.id));
      });
    });
  }

  async function openScenarioDetail(id) {
    var s = await apiGet("trpg/web/scenarios/" + id);
    if (!s) return;
    currentScenarioId = s.id;

    document.getElementById("scenario-list").style.display = "none";
    document.querySelector("#tab-scenarios .filter-bar").style.display = "none";
    document.getElementById("upload-area").style.display = "none";
    document.getElementById("scenario-detail").style.display = "block";

    document.getElementById("detail-title").textContent = s.title;
    document.getElementById("edit-title").value = s.title;
    document.getElementById("edit-summary").value = s.summary || "";
    document.getElementById("edit-tags").value = s.tags || "";
    document.getElementById("edit-players").value = s.recommended_players || "";
    document.getElementById("edit-opening").value = s.opening_scene || "";
    document.getElementById("edit-raw").value = s.raw_markdown || "";

    document.getElementById("btn-publish-scenario").style.display = s.status === "published" ? "none" : "";
  }

  function backToList() {
    document.getElementById("scenario-detail").style.display = "none";
    document.getElementById("scenario-list").style.display = "";
    document.querySelector("#tab-scenarios .filter-bar").style.display = "";
    document.getElementById("upload-area").style.display = "";
    currentScenarioId = null;
    loadScenarios();
  }

  document.getElementById("btn-back-list").addEventListener("click", backToList);
  document.getElementById("btn-refresh-scenarios").addEventListener("click", loadScenarios);
  document.getElementById("status-filter").addEventListener("change", loadScenarios);

  document.getElementById("btn-save-scenario").addEventListener("click", async function () {
    if (!currentScenarioId) return;
    var title = document.getElementById("edit-title").value.trim();
    var raw = document.getElementById("edit-raw").value.trim();
    if (!title) { toast("标题不能为空", "error"); return; }
    if (!raw) { toast("剧本内容不能为空", "error"); return; }

    var btn = document.getElementById("btn-save-scenario");
    setLoading(btn, true);
    var result = await apiPost("trpg/web/scenarios/" + currentScenarioId, {
      title: title,
      summary: document.getElementById("edit-summary").value.trim(),
      tags: document.getElementById("edit-tags").value.trim(),
      recommended_players: document.getElementById("edit-players").value.trim(),
      opening_scene: document.getElementById("edit-opening").value.trim(),
      raw_markdown: raw,
    });
    setLoading(btn, false);
    if (result) toast("保存成功", "success");
  });

  document.getElementById("btn-publish-scenario").addEventListener("click", async function () {
    if (!currentScenarioId) return;
    if (!confirm("确认发布此剧本？")) return;
    var btn = document.getElementById("btn-publish-scenario");
    setLoading(btn, true);
    var result = await apiPost("trpg/web/scenarios/" + currentScenarioId + "/publish");
    setLoading(btn, false);
    if (result) { toast("发布成功", "success"); backToList(); }
  });

  // --- Upload ---

  var uploadArea = document.getElementById("upload-area");
  var fileInput = document.getElementById("file-input");

  uploadArea.addEventListener("click", function () { fileInput.click(); });
  uploadArea.addEventListener("dragover", function (e) { e.preventDefault(); uploadArea.classList.add("dragover"); });
  uploadArea.addEventListener("dragleave", function () { uploadArea.classList.remove("dragover"); });
  uploadArea.addEventListener("drop", function (e) {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", function () {
    if (fileInput.files.length > 0) { uploadFile(fileInput.files[0]); fileInput.value = ""; }
  });

  // --- Sessions ---

  async function loadSessions() {
    var el = document.getElementById("session-list");
    el.innerHTML = skeletonCards(4);

    var data = await apiGet("trpg/web/sessions");
    if (!data) { el.innerHTML = emptyHtml("加载失败"); return; }
    sessionsData = data;

    document.getElementById("session-detail").style.display = "none";
    document.getElementById("session-list").style.display = "";

    var active = sessionsData.active_sessions || [];
    var history = sessionsData.history_sessions || [];

    if (active.length === 0 && history.length === 0) {
      el.innerHTML = emptyHtml("暂无跑团记录");
      return;
    }

    var html = "";
    if (active.length > 0) {
      html += '<div class="session-group-title"><span class="dot"></span> 进行中的会话</div>';
      active.forEach(function (s) {
        html += '<div class="session-item" data-platform="' + esc(s.platform_name) + '" data-session="' + esc(s.session_id) + '">' +
          '<div class="session-info"><div class="fw-500">' + esc(s.scenario_title) + '</div>' +
          '<div class="session-id">' + esc(s.platform_name) + " / " + esc(s.session_id) + '</div></div>' +
          '<div class="session-right"><div class="fw-500 text-primary">回合 ' + s.turn_count + '</div>' +
          '<div class="fs-12 text-muted">' + esc(s.current_stage) + '</div></div></div>';
      });
    }

    if (history.length > 0) {
      html += '<div class="session-group-title mt-20">历史会话</div>';
      history.forEach(function (s) {
        html += '<div class="session-item" data-platform="' + esc(s.platform_name) + '" data-session="' + esc(s.session_id) + '">' +
          '<div class="session-info"><div class="session-id">' + esc(s.platform_name) + " / " + esc(s.session_id) + '</div></div>' +
          '<div class="text-muted fs-13">' + s.history_count + ' 条记录</div></div>';
      });
    }

    el.innerHTML = html;
    el.querySelectorAll(".session-item").forEach(function (item) {
      item.addEventListener("click", function () {
        openSessionDetail(item.dataset.platform, item.dataset.session);
      });
    });
  }

  async function openSessionDetail(platform, sessionId) {
    var records = await apiGet("trpg/web/sessions/" + encodeURIComponent(platform) + "/" + encodeURIComponent(sessionId));
    if (!records) return;

    document.getElementById("session-list").style.display = "none";
    document.getElementById("session-detail").style.display = "block";
    document.getElementById("session-detail-title").textContent = platform + " / " + sessionId;

    var list = document.getElementById("session-history-list");
    if (records.length === 0) {
      list.innerHTML = emptyHtml("无历史记录");
      return;
    }

    list.innerHTML = '<div class="history-timeline">' + records.map(function (r) {
      var notes = [];
      try { notes = JSON.parse(r.notes_snapshot || "[]"); } catch (e) { /* ignore */ }
      var notesStr = notes.length > 0 ? notes.join(", ") : "无";
      return '<div class="history-entry">' +
        '<div class="meta">' +
          '<span>剧本 #' + r.scenario_id + '</span>' +
          '<span>回合: ' + r.turn_count + '</span>' +
          '<span>阶段: ' + esc(r.final_stage) + '</span>' +
        '</div>' +
        '<div class="meta">' +
          '<span>' + esc(r.started_at) + ' ~ ' + esc(r.ended_at) + '</span>' +
        '</div>' +
        '<div class="summary-text"><strong>总结：</strong>' + esc(r.summary || "无") + '</div>' +
        '<div class="notes-line">记录板: ' + esc(notesStr) + '</div></div>';
    }).join("") + "</div>";
  }

  document.getElementById("btn-back-sessions").addEventListener("click", function () {
    document.getElementById("session-detail").style.display = "none";
    document.getElementById("session-list").style.display = "";
    loadSessions();
  });
  document.getElementById("btn-refresh-sessions").addEventListener("click", loadSessions);

  // --- Config ---

  var CONFIG_GROUPS = {
    "基本配置": ["admin_user_ids", "db_filename", "bootstrap_builtin_scenarios", "max_import_chars", "max_list_size", "scenario_export_dir"],
    "LLM 配置": ["solo_provider_id", "solo_fallback_provider_id", "solo_system_prompt_override", "solo_max_steps"],
  };

  async function loadConfig() {
    var form = document.getElementById("config-form");
    form.innerHTML = skeletonCards(3);

    var config = await apiGet("trpg/web/config");
    if (!config) { form.innerHTML = emptyHtml("加载失败"); return; }

    var html = "";

    Object.keys(CONFIG_GROUPS).forEach(function (groupName) {
      var keys = CONFIG_GROUPS[groupName];
      html += '<div class="config-section">';
      html += '<div class="config-section-title">' + esc(groupName) + '</div>';

      keys.forEach(function (key) {
        var item = config[key];
        if (!item) return;
        var type = item.type;
        var value = item.value;
        var desc = item.description;

        html += '<div class="form-group">';
        html += "<label>" + esc(key) + "</label>";
        if (desc) html += '<div class="desc">' + esc(desc) + "</div>";

        if (item.sensitive) {
          if (type === "list") {
            var listStr = Array.isArray(value) ? value.join(", ") : String(value || "");
            html += '<input type="text" class="form-control" data-key="' + esc(key) + '" data-type="list" data-sensitive="true" value="' + esc(listStr) + '" placeholder="逗号分隔">';
            html += '<div class="desc" style="color:var(--warning);font-size:12px">敏感配置，修改后需确认</div>';
          } else {
            html += '<input type="text" class="form-control" data-key="' + esc(key) + '" data-type="' + type + '" data-sensitive="true" value="' + esc(value || "") + '" placeholder="留空或输入新值">';
          }
        } else if (type === "bool") {
          var checked = value ? "checked" : "";
          html += '<div class="switch-wrap"><label class="switch">' +
            '<input type="checkbox" data-key="' + esc(key) + '" data-type="bool" ' + checked + '>' +
            '<span class="slider"></span></label><span>' + (value ? "开启" : "关闭") + '</span></div>';
        } else if (type === "int") {
          html += '<input type="number" class="form-control" data-key="' + esc(key) + '" data-type="int" value="' + esc(String(value)) + '">';
        } else if (type === "list") {
          var listStr = Array.isArray(value) ? value.join(", ") : String(value || "");
          html += '<input type="text" class="form-control" data-key="' + esc(key) + '" data-type="list" value="' + esc(listStr) + '" placeholder="逗号分隔">';
        } else {
          html += '<input type="text" class="form-control" data-key="' + esc(key) + '" data-type="string" value="' + esc(String(value || "")) + '">';
        }
        html += "</div>";
      });

      html += "</div>";
    });

    form.innerHTML = html;

    form.querySelectorAll('.switch input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener("change", function () {
        var span = cb.closest(".switch-wrap").querySelector("span:not(.slider)");
        if (span) span.textContent = cb.checked ? "开启" : "关闭";
      });
    });
  }

  document.getElementById("btn-save-config").addEventListener("click", async function () {
    if (!confirm("确认保存配置？部分配置需要重启插件才能生效。")) return;
    var form = document.getElementById("config-form");
    var data = {};
    form.querySelectorAll("[data-key]").forEach(function (el) {
      var key = el.dataset.key;
      if (el.dataset.type === "bool") {
        data[key] = el.checked;
      } else {
        data[key] = el.value;
      }
    });
    var btn = document.getElementById("btn-save-config");
    setLoading(btn, true);
    var result = await apiPost("trpg/web/config", data);
    setLoading(btn, false);
    if (result) toast("配置已保存", "success");
  });

  // --- Helpers ---

  function esc(str) {
    if (str == null) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // --- Init ---

  function waitForBridge(maxWaitMs) {
    return new Promise(function (resolve, reject) {
      var start = Date.now();
      function check() {
        if (window.AstrBotPluginPage) {
          resolve(window.AstrBotPluginPage);
          return;
        }
        if (Date.now() - start > maxWaitMs) {
          reject(new Error("Bridge SDK 加载超时（" + maxWaitMs / 1000 + "秒）"));
          return;
        }
        setTimeout(check, 200);
      }
      check();
    });
  }

  async function init() {
    try {
      // Step 1: Wait for bridge SDK to be available (with timeout)
      try {
        bridge = await waitForBridge(10000);
      } catch (e) {
        var diag = [
          "Bridge SDK 未加载。诊断信息：",
          "- 当前 URL: " + window.location.href,
          "- 是否在 iframe 中: " + (window.self !== window.top),
          "- AstrBotPluginPage 存在: " + !!window.AstrBotPluginPage,
        ].join("\n");
        console.error(diag);
        toast("Bridge SDK 未加载，请确保从 AstrBot Dashboard (v4.24.2+) 访问此页面", "error");
        document.getElementById("scenario-list").innerHTML =
          '<div class="empty" style="text-align:left;padding:24px">' +
          '<p style="font-weight:600;margin-bottom:8px">Bridge SDK 加载失败</p>' +
          '<p style="font-size:13px;color:var(--text-muted);line-height:1.6">' +
          "请检查：<br>1. AstrBot 版本 >= 4.24.2<br>" +
          "2. 从 Dashboard 的插件详情页进入<br>" +
          "3. 浏览器控制台是否有脚本加载错误<br>" +
          "4. 插件的 pages/admin/ 目录是否完整</p></div>";
        return;
      }

      // Step 2: Wait for parent context (with timeout)
      var readyResult = await Promise.race([
        bridge.ready(),
        new Promise(function (r) { setTimeout(function () { r(null); }, 8000); }),
      ]);

      if (!readyResult) {
        console.warn("Bridge ready() timed out, proceeding without context");
      }

      // Step 3: Load data
      loadScenarios();
    } catch (e) {
      console.error("TRPG WebUI init error:", e);
      toast("初始化失败: " + e.message, "error");
    }
  }

  init();
})();
