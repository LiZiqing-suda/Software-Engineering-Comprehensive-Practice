/**
 * 苏州大学校园政策智能问答系统 - 合并脚本（非模块版本）
 *
 * 将所有功能合并到全局命名空间 SudaQA 下，使用普通 <script> 标签加载，
 * 不使用 ES Module，兼容所有手机浏览器（微信、QQ、UC、百度等）。
 */

(function () {
    "use strict";

    // ==================== 全局命名空间 ====================
    var SudaQA = window.SudaQA || {};

    // ==================== Polyfill ====================
    function generateUUID() {
        if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
            return crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === "x" ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    // ==================== render 模块 ====================
    // marked 延迟初始化
    var _markedReady = false;
    function ensureMarked() {
        if (_markedReady) return true;
        if (typeof marked === "undefined" || typeof marked.parse !== "function") {
            return false;
        }
        try {
            marked.setOptions({
                breaks: true,
                gfm: true,
                headerIds: false,
                mangle: false,
            });
            _markedReady = true;
            return true;
        } catch (e) {
            return false;
        }
    }

    var PURIFY_CONFIG = {
        ADD_TAGS: [
            "span", "svg", "path", "g", "rect", "text",
            "mrow", "mi", "mn", "mo", "msup", "mfrac",
            "mtable", "mtr", "mtd", "mtext", "annotation",
        ],
        ADD_ATTR: [
            "class", "style", "xmlns", "viewBox", "d", "fill",
            "stroke", "stroke-width", "transform", "font-family",
            "font-size", "font-style", "font-weight", "text-anchor",
            "x", "y", "width", "height", "data-markdown",
            "data-canonical", "aria-hidden",
        ],
    };

    function escapeHtml(text) {
        var div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    function renderMarkdownWithLatex(rawText) {
        if (!ensureMarked()) {
            return escapeHtml(rawText).replace(/\n/g, "<br>");
        }

        var latexBlocks = [];

        // 保护块级公式
        var text = rawText.replace(/\$\$([\s\S]*?)\$\$/g, function (_, f) {
            latexBlocks.push({ formula: f.trim(), display: true });
            return "\n@@LATEX_" + (latexBlocks.length - 1) + "@@\n";
        });
        text = text.replace(/\\\[([\s\S]*?)\\\]/g, function (_, f) {
            latexBlocks.push({ formula: f.trim(), display: true });
            return "\n@@LATEX_" + (latexBlocks.length - 1) + "@@\n";
        });

        // 保护行内公式
        text = text.replace(/\$([^\$\n]+?)\$/g, function (_, f) {
            latexBlocks.push({ formula: f.trim(), display: false });
            return "@@LATEX_" + (latexBlocks.length - 1) + "@@";
        });
        text = text.replace(/\\\(([\s\S]*?)\\\)/g, function (_, f) {
            latexBlocks.push({ formula: f.trim(), display: false });
            return "@@LATEX_" + (latexBlocks.length - 1) + "@@";
        });

        // Markdown → HTML
        var html = marked.parse(text);

        // XSS 净化
        if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
            html = DOMPurify.sanitize(html, PURIFY_CONFIG);
        }

        // 占位符 → KaTeX
        var katexAvailable = typeof katex !== "undefined" && typeof katex.renderToString === "function";

        html = html.replace(/@@LATEX_(\d+)@@/g, function (_, id) {
            var lb = latexBlocks[parseInt(id)];
            if (!lb) return "";

            if (!katexAvailable) {
                if (lb.display) {
                    return '<pre style="background:#f5f5f5;padding:8px;border-radius:4px;text-align:center;">' + escapeHtml(lb.formula) + "</pre>";
                }
                return "<code>" + escapeHtml(lb.formula) + "</code>";
            }

            try {
                return katex.renderToString(lb.formula, {
                    displayMode: lb.display,
                    throwOnError: false,
                    errorColor: "#e74c3c",
                    strict: false,
                });
            } catch (e) {
                return lb.display
                    ? '<pre style="color:#e74c3c;background:#fdf0ef;padding:8px;border-radius:4px;">公式渲染失败: ' + escapeHtml(lb.formula) + "</pre>"
                    : '<code style="color:#e74c3c;">' + escapeHtml(lb.formula) + "</code>";
            }
        });

        return html;
    }

    // ==================== DOM 引用 & 会话管理 ====================
    var statusDot, statusText, chatMessages, queryInput, submitBtn;
    var SESSION_KEY = "suda_qa_session_id";
    var _currentAssistantBubble = null;

    function getDomRefs() {
        statusDot = document.getElementById("status-dot");
        statusText = document.getElementById("status-text");
        chatMessages = document.getElementById("chat-messages");
        queryInput = document.getElementById("query-input");
        submitBtn = document.getElementById("submit-btn");
    }

    function getSessionId() {
        var sid = null;
        try {
            sid = localStorage.getItem(SESSION_KEY);
        } catch (e) {}
        if (!sid) {
            sid = generateUUID();
            try {
                localStorage.setItem(SESSION_KEY, sid);
            } catch (e) {}
        }
        return sid;
    }

    function newSession() {
        var sid = generateUUID();
        try {
            localStorage.setItem(SESSION_KEY, sid);
        } catch (e) {}
        clearMessages();
        return sid;
    }

    // ==================== UI 状态 ====================
    function setStatus(state) {
        if (!statusDot || !statusText) return;
        statusDot.className = "chat-header-dot";
        switch (state) {
            case "loading":
                statusDot.classList.add("loading-dot");
                statusText.textContent = "正在检索并生成回答...";
                break;
            case "success":
                statusText.textContent = "回答完成";
                break;
            case "error":
                statusDot.style.background = "var(--danger)";
                statusText.textContent = "请求出错";
                break;
            default:
                statusText.textContent = "就绪";
        }
    }

    function clearMessages() {
        if (!chatMessages) return;
        chatMessages.innerHTML =
            '<div class="chat-empty">' +
            '<div class="chat-empty-icon">💬</div>' +
            "<p>输入问题并点击提交，系统将为你检索相关政策文档并生成回答</p>" +
            "</div>";
        _currentAssistantBubble = null;
    }

    function formatTime() {
        var now = new Date();
        var h = String(now.getHours()).padStart(2, "0");
        var m = String(now.getMinutes()).padStart(2, "0");
        return h + ":" + m;
    }

    function removeEmptyState() {
        if (!chatMessages) return;
        var empty = chatMessages.querySelector(".chat-empty");
        if (empty) empty.remove();
    }

    function scrollToBottom() {
        if (!chatMessages) return;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function addUserMessage(text) {
        if (!chatMessages) return;
        removeEmptyState();
        var row = document.createElement("div");
        row.className = "message-row user";
        row.innerHTML =
            "<div>" +
            '<div class="message-bubble">' + escapeHtml(text) + "</div>" +
            '<div class="message-time">' + formatTime() + "</div>" +
            "</div>" +
            '<div class="message-avatar">👤</div>';
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function createAssistantBubble() {
        if (!chatMessages) return null;
        removeEmptyState();
        var row = document.createElement("div");
        row.className = "message-row assistant";
        row.innerHTML =
            '<div class="message-avatar">🤖</div>' +
            '<div style="max-width:75%;">' +
            '<div class="message-bubble streaming-cursor"></div>' +
            '<div class="message-time">' + formatTime() + "</div>" +
            "</div>";
        chatMessages.appendChild(row);
        var bubble = row.querySelector(".message-bubble");
        _currentAssistantBubble = bubble;
        scrollToBottom();
        return bubble;
    }

    function appendToken(token) {
        if (!_currentAssistantBubble) return;
        _currentAssistantBubble.dataset.rawText =
            (_currentAssistantBubble.dataset.rawText || "") + token;
        _currentAssistantBubble.textContent += token;
        scrollToBottom();
    }

    function finalizeAssistantBubble() {
        if (!_currentAssistantBubble) return;
        _currentAssistantBubble.classList.remove("streaming-cursor");
        var rawText = _currentAssistantBubble.dataset.rawText || "";
        if (rawText) {
            _currentAssistantBubble.innerHTML = renderMarkdownWithLatex(rawText);
        }
        _currentAssistantBubble = null;
        scrollToBottom();
    }

    function addErrorMessage(errorText) {
        if (!chatMessages) return;
        removeEmptyState();
        var row = document.createElement("div");
        row.className = "message-row assistant";
        row.innerHTML =
            '<div class="message-avatar">⚠️</div>' +
            '<div style="max-width:75%;">' +
            '<div class="message-bubble" style="color:var(--danger);">' +
            escapeHtml(errorText) +
            "</div>" +
            '<div class="message-time">' + formatTime() + "</div>" +
            "</div>";
        chatMessages.appendChild(row);
        _currentAssistantBubble = null;
        scrollToBottom();
    }

    function setInputEnabled(enabled) {
        if (queryInput) queryInput.disabled = !enabled;
        if (submitBtn) submitBtn.disabled = !enabled;
        if (enabled) {
            if (queryInput) queryInput.focus();
            if (submitBtn) submitBtn.innerHTML = '<span class="btn-icon">✉️</span> 提交问题';
        } else {
            if (submitBtn) submitBtn.innerHTML = '<span class="btn-icon">⏳</span> 正在解答...';
        }
    }

    function shakeElement(el) {
        if (!el) return;
        el.style.animation = "none";
        el.offsetHeight;
        el.style.animation = "shake 0.4s ease";
        setTimeout(function () {
            el.style.animation = "";
        }, 400);
    }

    // ==================== 暗色模式 ====================
    function initTheme() {
        try {
            var saved = localStorage.getItem("suda_qa_theme");
            if (saved === "dark") {
                document.documentElement.setAttribute("data-theme", "dark");
            }
        } catch (e) {}
    }

    function toggleTheme() {
        var current = document.documentElement.getAttribute("data-theme");
        var next = current === "dark" ? "light" : "dark";
        if (next === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
            try { localStorage.setItem("suda_qa_theme", "dark"); } catch (e) {}
        } else {
            document.documentElement.removeAttribute("data-theme");
            try { localStorage.setItem("suda_qa_theme", "light"); } catch (e) {}
        }
    }

    // ==================== API 通信 ====================
    function qaStream(query, sessionId, callbacks) {
        var onMeta = callbacks.onMeta;
        var onToken = callbacks.onToken;
        var onDone = callbacks.onDone;
        var onError = callbacks.onError;

        fetch("/api/qa/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query, session_id: sessionId }),
        })
            .then(function (resp) {
                if (resp.status === 429) {
                    return resp.json()
                        .catch(function () { return {}; })
                        .then(function (result) {
                            throw new Error(result.msg || "访问过于频繁");
                        });
                }
                if (!resp.ok) {
                    return resp.json()
                        .catch(function () { return {}; })
                        .then(function (result) {
                            throw new Error(result.msg || "HTTP " + resp.status);
                        });
                }

                var reader = resp.body.getReader();
                var decoder = new TextDecoder();
                var buffer = "";

                function pump() {
                    return reader.read().then(function (_a) {
                        var done = _a.done;
                        var value = _a.value;

                        if (done) {
                            if (onDone) onDone();
                            return;
                        }

                        buffer += decoder.decode(value, { stream: true });
                        var lines = buffer.split("\n");
                        buffer = lines.pop();

                        for (var i = 0; i < lines.length; i++) {
                            var line = lines[i];
                            if (line.indexOf("data: ") !== 0) continue;

                            var dataStr = line.slice(6).trim();
                            if (!dataStr) continue;

                            var event;
                            try {
                                event = JSON.parse(dataStr);
                            } catch (e) {
                                continue;
                            }

                            switch (event.type) {
                                case "meta":
                                    if (onMeta) onMeta(event);
                                    break;
                                case "token":
                                    if (onToken) onToken(event.content);
                                    break;
                                case "done":
                                    if (onDone) onDone();
                                    return;
                                case "error":
                                    if (onError) onError(event.message);
                                    return;
                            }
                        }

                        return pump();
                    });
                }

                return pump();
            })
            .catch(function (err) {
                if (err.name === "AbortError") return;
                if (onError) onError(err.message);
            });
    }

    // ==================== 提交逻辑 ====================
    var _submitting = false;

    function submitQuery(queryText) {
        if (_submitting) return;

        var query = (queryText || (queryInput ? queryInput.value : "") || "").trim();
        if (!query) {
            shakeElement(queryInput);
            return;
        }

        _submitting = true;

        var sessionId;
        try {
            sessionId = getSessionId();
        } catch (e) {
            addErrorMessage("会话初始化失败：" + e.message);
            _submitting = false;
            return;
        }

        // 立即给用户视觉反馈
        setInputEnabled(false);
        setStatus("loading");
        addUserMessage(query);
        var bubble = createAssistantBubble();

        qaStream(query, sessionId, {
            onMeta: function (event) {
                if (event.session_id) {
                    try {
                        localStorage.setItem("suda_qa_session_id", event.session_id);
                    } catch (e) {}
                }
            },
            onToken: function (token) {
                appendToken(token);
            },
            onDone: function () {
                finalizeAssistantBubble();
                setStatus("success");
                setInputEnabled(true);
                if (queryInput) queryInput.value = "";
                _submitting = false;
            },
            onError: function (msg) {
                if (bubble) bubble.remove();
                addErrorMessage(msg);
                setStatus("error");
                setInputEnabled(true);
                _submitting = false;
            },
        });
    }

    // ==================== 事件绑定 ====================
    function initEvents() {
        // 提交按钮 — 同时绑定 pointerdown（iOS键盘兼容）和 click
        var btn = document.getElementById("submit-btn");
        if (btn) {
            btn.addEventListener("pointerdown", function (e) {
                e.preventDefault();
                submitQuery();
            });
            btn.addEventListener("click", function (e) {
                e.preventDefault();
                submitQuery();
            });
        }

        // 快捷键 Ctrl+Enter
        var input = document.getElementById("query-input");
        if (input) {
            input.addEventListener("keydown", function (e) {
                if (e.ctrlKey && e.key === "Enter") {
                    e.preventDefault();
                    submitQuery();
                }
            });
        }

        // 快捷问题标签
        var chips = document.querySelectorAll(".quick-chip");
        for (var i = 0; i < chips.length; i++) {
            (function (chip) {
                chip.addEventListener("click", function (e) {
                    e.preventDefault();
                    var q = chip.getAttribute("data-query");
                    var qi = document.getElementById("query-input");
                    if (qi) qi.value = q;
                    submitQuery(q);
                });
                chip.addEventListener("touchend", function (e) {
                    e.preventDefault();
                    var q = chip.getAttribute("data-query");
                    var qi = document.getElementById("query-input");
                    if (qi) qi.value = q;
                    submitQuery(q);
                });
            })(chips[i]);
        }

        // 新建对话
        var btnNew = document.getElementById("btn-new-chat");
        if (btnNew) {
            btnNew.addEventListener("click", function () {
                newSession();
                setStatus("default");
            });
        }

        // 清空屏幕
        var btnClear = document.getElementById("btn-clear-chat");
        if (btnClear) {
            btnClear.addEventListener("click", function () {
                clearMessages();
                setStatus("default");
            });
        }

        // 暗色模式
        var btnTheme = document.getElementById("btn-theme");
        if (btnTheme) {
            btnTheme.addEventListener("click", function () {
                toggleTheme();
                var isDark = document.documentElement.getAttribute("data-theme") === "dark";
                btnTheme.textContent = isDark ? "☀️" : "🌙";
            });
        }
    }

    // ==================== 启动 ====================
    function init() {
        getDomRefs();
        initTheme();
        initEvents();
        console.log("苏州大学校园政策智能问答系统 v2.0 已就绪（兼容模式）");
    }

    // DOM 加载完成后启动
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    // 暴露到全局，方便调试
    window.SudaQA = {
        submitQuery: submitQuery,
        newSession: newSession,
        clearMessages: clearMessages,
        toggleTheme: toggleTheme,
    };
})();
