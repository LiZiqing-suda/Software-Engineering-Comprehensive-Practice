/**
 * 应用入口模块
 *
 * 绑定事件处理、初始化页面。
 * 同时监听 click 和 pointerdown 事件，确保在手机浏览器
 * （尤其是 iOS Safari 软键盘打开时）也能正常触发。
 */

import { qaStream } from "./api.js";
import {
    getSessionId,
    newSession,
    setStatus,
    setInputEnabled,
    addUserMessage,
    createAssistantBubble,
    appendToken,
    finalizeAssistantBubble,
    addErrorMessage,
    shakeElement,
    toggleTheme,
    initTheme,
    clearMessages,
    queryInput,
} from "./ui.js";

// —— 防重复提交 ——
let _submitting = false;

/**
 * 提交问题（流式）
 * @param {string} [queryText] - 可选的外部传入问题文本
 */
export async function submitQuery(queryText) {
    // 防止重复点击
    if (_submitting) return;

    const query = (queryText || (queryInput && queryInput.value) || "").trim();
    if (!query) {
        shakeElement(queryInput);
        return;
    }

    _submitting = true;

    let sessionId;
    try {
        sessionId = getSessionId();
    } catch (e) {
        addErrorMessage("会话初始化失败：" + e.message);
        _submitting = false;
        return;
    }

    // UI 状态 — 立即给用户视觉反馈
    setInputEnabled(false);
    setStatus("loading");
    addUserMessage(query);
    const bubble = createAssistantBubble();

    try {
        await qaStream(query, sessionId, {
            onMeta(event) {
                if (event.session_id) {
                    try {
                        localStorage.setItem("suda_qa_session_id", event.session_id);
                    } catch (e) {}
                }
            },
            onToken(token) {
                appendToken(token);
            },
            onDone() {
                finalizeAssistantBubble();
                setStatus("success");
                setInputEnabled(true);
                if (queryInput) queryInput.value = "";
                _submitting = false;
            },
            onError(msg) {
                if (bubble) bubble.remove();
                addErrorMessage(msg);
                setStatus("error");
                setInputEnabled(true);
                _submitting = false;
            },
        });
    } catch (err) {
        if (bubble) bubble.remove();
        addErrorMessage(err.message || "未知错误");
        setStatus("error");
        setInputEnabled(true);
        _submitting = false;
    }
}

/**
 * 处理提交按钮点击/触摸
 * 使用 pointerdown 事件确保在 iOS Safari 软键盘打开时也能触发
 * （pointerdown 在键盘关闭前触发，click 在键盘关闭后可能落在错误位置）
 */
let _submitPending = false;
function handleSubmitTrigger(e) {
    // 阻止默认行为，防止移动端可能的页面缩放或表单提交
    e.preventDefault();
    // 防止 pointerdown + click 双重触发
    if (_submitPending) return;
    _submitPending = true;
    submitQuery();
    // 300ms 后重置，避免被后续 click 事件再次触发
    setTimeout(function () {
        _submitPending = false;
    }, 300);
}

/**
 * 初始化事件绑定
 */
function initEvents() {
    // === 提交按钮 ===
    // 同时绑定 click 和 pointerdown，确保各种手机浏览器都能触发
    var submitBtn = document.getElementById("submit-btn");
    if (submitBtn) {
        submitBtn.addEventListener("click", handleSubmitTrigger);
        submitBtn.addEventListener("pointerdown", handleSubmitTrigger);
    }

    // === 快捷键 Ctrl+Enter ===
    if (queryInput) {
        queryInput.addEventListener("keydown", function (e) {
            if (e.ctrlKey && e.key === "Enter") {
                e.preventDefault();
                submitQuery();
            }
        });
    }

    // === 快捷问题标签 ===
    // 使用 click + touchend 双保险（手机端 span 元素 click 可靠性差）
    document.querySelectorAll(".quick-chip").forEach(function (chip) {
        chip.addEventListener("click", function (e) {
            e.preventDefault();
            var q = this.getAttribute("data-query");
            if (queryInput) queryInput.value = q;
            submitQuery(q);
        });
        // 手机端：touchend 作为后备，确保触摸事件能触发
        chip.addEventListener("touchend", function (e) {
            e.preventDefault();
            var q = this.getAttribute("data-query");
            if (queryInput) queryInput.value = q;
            submitQuery(q);
        });
    });

    // === 新建对话 ===
    var btnNewChat = document.getElementById("btn-new-chat");
    if (btnNewChat) {
        btnNewChat.addEventListener("click", function () {
            newSession();
            setStatus("default");
        });
        btnNewChat.addEventListener("pointerdown", function (e) {
            e.preventDefault();
            newSession();
            setStatus("default");
        });
    }

    // === 清空屏幕 ===
    var btnClearChat = document.getElementById("btn-clear-chat");
    if (btnClearChat) {
        btnClearChat.addEventListener("click", function () {
            clearMessages();
            setStatus("default");
        });
        btnClearChat.addEventListener("pointerdown", function (e) {
            e.preventDefault();
            clearMessages();
            setStatus("default");
        });
    }

    // === 暗色模式切换 ===
    var btnTheme = document.getElementById("btn-theme");
    if (btnTheme) {
        btnTheme.addEventListener("click", function () {
            toggleTheme();
            var isDark = document.documentElement.getAttribute("data-theme") === "dark";
            btnTheme.textContent = isDark ? "☀️" : "🌙";
        });
        btnTheme.addEventListener("pointerdown", function (e) {
            e.preventDefault();
            toggleTheme();
            var isDark = document.documentElement.getAttribute("data-theme") === "dark";
            btnTheme.textContent = isDark ? "☀️" : "🌙";
        });
    }
}

// ——— 应用启动 ———
(function () {
    try {
        initTheme();
    } catch (e) {
        console.warn("initTheme 失败:", e);
    }

    try {
        initEvents();
        console.log("苏州大学校园政策智能问答系统 v2.0 已就绪");
    } catch (e) {
        console.error("事件绑定失败:", e);
        // 兜底：即使模块事件绑定失败，尝试用内联方式绑定提交按钮
        var fallbackBtn = document.getElementById("submit-btn");
        if (fallbackBtn) {
            fallbackBtn.onclick = function () {
                submitQuery();
            };
        }
    }
})();
