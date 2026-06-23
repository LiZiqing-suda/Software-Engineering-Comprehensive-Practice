/**
 * UI 状态管理模块
 *
 * 管理聊天界面状态，包括：
 * - 会话 ID 管理（localStorage 持久化）
 * - 消息列表渲染
 * - 流式 token 追加
 * - 状态指示（加载中、就绪、错误）
 */

import { renderMarkdownWithLatex, escapeHtml } from "./render.js";

// —— DOM 引用 ——
export const statusDot = document.getElementById("status-dot");
export const statusText = document.getElementById("status-text");
export const chatMessages = document.getElementById("chat-messages");
export const queryInput = document.getElementById("query-input");
export const submitBtn = document.getElementById("submit-btn");

// —— crypto.randomUUID() polyfill（部分手机浏览器不支持） ——
function generateUUID() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    // Fallback: 手动生成 UUID v4
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

// —— 会话管理 ——
const SESSION_KEY = "suda_qa_session_id";

export function getSessionId() {
    let sid = null;
    try {
        sid = localStorage.getItem(SESSION_KEY);
    } catch (e) {
        // localStorage 不可用（无痕模式等）
    }
    if (!sid) {
        sid = generateUUID();
        try {
            localStorage.setItem(SESSION_KEY, sid);
        } catch (e) {
            // 静默忽略
        }
    }
    return sid;
}

export function newSession() {
    const sid = generateUUID();
    try {
        localStorage.setItem(SESSION_KEY, sid);
    } catch (e) {
        // 静默忽略
    }
    clearMessages();
    return sid;
}

// —— 状态指示 ——
export function setStatus(state) {
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

// —— 消息渲染 ——
let _currentAssistantBubble = null;

/**
 * 清空消息列表
 */
export function clearMessages() {
    if (!chatMessages) return;
    chatMessages.innerHTML = `
        <div class="chat-empty">
            <div class="chat-empty-icon">💬</div>
            <p>输入问题并点击提交，系统将为你检索相关政策文档并生成回答</p>
        </div>
    `;
    _currentAssistantBubble = null;
}

/**
 * 添加用户消息
 * @param {string} text - 用户消息文本
 */
export function addUserMessage(text) {
    if (!chatMessages) return;
    removeEmptyState();
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
        <div>
            <div class="message-bubble">${escapeHtml(text)}</div>
            <div class="message-time">${formatTime()}</div>
        </div>
        <div class="message-avatar">👤</div>
    `;
    chatMessages.appendChild(row);
    scrollToBottom();
}

/**
 * 创建空的助手消息气泡（用于流式填充）
 * @returns {HTMLElement} 助手消息的 bubble 元素
 */
export function createAssistantBubble() {
    if (!chatMessages) return null;
    removeEmptyState();
    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div style="max-width:75%;">
            <div class="message-bubble streaming-cursor"></div>
            <div class="message-time">${formatTime()}</div>
        </div>
    `;
    chatMessages.appendChild(row);
    const bubble = row.querySelector(".message-bubble");
    _currentAssistantBubble = bubble;
    scrollToBottom();
    return bubble;
}

/**
 * 向当前助手气泡追加 token（流式渲染）
 * @param {string} token - 增量文本
 */
export function appendToken(token) {
    if (!_currentAssistantBubble) return;
    // 流式过程中只做简单的 HTML 转义，不渲染 Markdown
    // Markdown 渲染在流结束后统一进行
    _currentAssistantBubble.dataset.rawText =
        (_currentAssistantBubble.dataset.rawText || "") + token;
    _currentAssistantBubble.textContent += token;
    scrollToBottom();
}

/**
 * 流式结束 — 用 Markdown+KaTeX 重新渲染整个气泡
 */
export function finalizeAssistantBubble() {
    if (!_currentAssistantBubble) return;
    _currentAssistantBubble.classList.remove("streaming-cursor");
    const rawText = _currentAssistantBubble.dataset.rawText || "";
    if (rawText) {
        _currentAssistantBubble.innerHTML = renderMarkdownWithLatex(rawText);
    }
    _currentAssistantBubble = null;
    scrollToBottom();
}

/**
 * 添加错误消息
 */
export function addErrorMessage(errorText) {
    if (!chatMessages) return;
    removeEmptyState();
    const row = document.createElement("div");
    row.className = "message-row assistant";
    row.innerHTML = `
        <div class="message-avatar">⚠️</div>
        <div style="max-width:75%;">
            <div class="message-bubble" style="color:var(--danger);">
                ${escapeHtml(errorText)}
            </div>
            <div class="message-time">${formatTime()}</div>
        </div>
    `;
    chatMessages.appendChild(row);
    _currentAssistantBubble = null;
    scrollToBottom();
}

// —— 工具函数 ——

function removeEmptyState() {
    if (!chatMessages) return;
    const empty = chatMessages.querySelector(".chat-empty");
    if (empty) empty.remove();
}

function scrollToBottom() {
    if (!chatMessages) return;
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function formatTime() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, "0");
    const m = String(now.getMinutes()).padStart(2, "0");
    return `${h}:${m}`;
}

/**
 * 禁用/启用输入
 */
export function setInputEnabled(enabled) {
    if (queryInput) queryInput.disabled = !enabled;
    if (submitBtn) submitBtn.disabled = !enabled;
    if (enabled) {
        if (queryInput) queryInput.focus();
        if (submitBtn) submitBtn.innerHTML = '<span class="btn-icon">✉️</span> 提交问题';
    } else {
        if (submitBtn) submitBtn.innerHTML = '<span class="btn-icon">⏳</span> 正在解答...';
    }
}

/**
 * 抖动动画
 */
export function shakeElement(el) {
    if (!el) return;
    el.style.animation = "none";
    el.offsetHeight; // trigger reflow
    el.style.animation = "shake 0.4s ease";
    setTimeout(() => { el.style.animation = ""; }, 400);
}

/**
 * 暗色模式切换
 */
export function initTheme() {
    try {
        const saved = localStorage.getItem("suda_qa_theme");
        if (saved === "dark") {
            document.documentElement.setAttribute("data-theme", "dark");
        }
    } catch (e) {
        // localStorage 不可用时忽略
    }
}

export function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    if (next === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
        try {
            localStorage.setItem("suda_qa_theme", "dark");
        } catch (e) {}
    } else {
        document.documentElement.removeAttribute("data-theme");
        try {
            localStorage.setItem("suda_qa_theme", "light");
        } catch (e) {}
    }
}
