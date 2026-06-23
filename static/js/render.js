/**
 * 渲染模块 — Markdown + KaTeX 公式渲染
 *
 * 策略：
 * 1. 先将 LaTeX 公式替换为占位符
 * 2. 用 marked 将 Markdown 转为 HTML
 * 3. DOMPurify 做 XSS 净化
 * 4. 将占位符替换为 KaTeX 渲染结果
 *
 * 所有 CDN 依赖（marked / DOMPurify / katex）均为延迟初始化，
 * 即使 CDN 加载失败，模块也能正常加载，事件绑定不受影响。
 */

// —— 延迟初始化 marked ——
let _markedReady = false;
function ensureMarked() {
    if (_markedReady) return true;
    if (typeof marked === "undefined" || typeof marked.parse !== "function") {
        return false;
    }
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false,
    });
    _markedReady = true;
    return true;
}

// DOMPurify 配置 — 放行 KaTeX 所需标签和属性
const PURIFY_CONFIG = {
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

/**
 * 转义 HTML 特殊字符
 */
export function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 渲染 Markdown 文本（含 LaTeX 公式）为 HTML
 * @param {string} rawText - 原始文本
 * @returns {string} 渲染后的 HTML；若核心库未加载则返回转义后的纯文本
 */
export function renderMarkdownWithLatex(rawText) {
    // 如果 marked 未就绪，回退为纯文本展示
    if (!ensureMarked()) {
        return escapeHtml(rawText).replace(/\n/g, "<br>");
    }

    const latexBlocks = [];

    // 1. 保护块级公式：$$...$$ 和 \[...\]
    let text = rawText.replace(/\$\$([\s\S]*?)\$\$/g, (_, f) => {
        latexBlocks.push({ formula: f.trim(), display: true });
        return `\n@@LATEX_${latexBlocks.length - 1}@@\n`;
    });
    text = text.replace(/\\\[([\s\S]*?)\\\]/g, (_, f) => {
        latexBlocks.push({ formula: f.trim(), display: true });
        return `\n@@LATEX_${latexBlocks.length - 1}@@\n`;
    });

    // 2. 保护行内公式：$...$ 和 \(...\)
    text = text.replace(/\$([^\$\n]+?)\$/g, (_, f) => {
        latexBlocks.push({ formula: f.trim(), display: false });
        return `@@LATEX_${latexBlocks.length - 1}@@`;
    });
    text = text.replace(/\\\(([\s\S]*?)\\\)/g, (_, f) => {
        latexBlocks.push({ formula: f.trim(), display: false });
        return `@@LATEX_${latexBlocks.length - 1}@@`;
    });

    // 3. Markdown → HTML
    let html = marked.parse(text);

    // 4. XSS 净化
    if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
        html = DOMPurify.sanitize(html, PURIFY_CONFIG);
    }

    // 5. 占位符 → KaTeX（仅在 katex 可用时）
    const katexAvailable = typeof katex !== "undefined" && typeof katex.renderToString === "function";

    html = html.replace(/@@LATEX_(\d+)@@/g, (_, id) => {
        const lb = latexBlocks[parseInt(id)];
        if (!lb) return "";

        if (!katexAvailable) {
            // KaTeX 不可用，显示原始公式
            if (lb.display) {
                return `<pre style="background:#f5f5f5;padding:8px;border-radius:4px;text-align:center;">${escapeHtml(lb.formula)}</pre>`;
            }
            return `<code>${escapeHtml(lb.formula)}</code>`;
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
                ? `<pre style="color:#e74c3c;background:#fdf0ef;padding:8px;border-radius:4px;">公式渲染失败: ${escapeHtml(lb.formula)}</pre>`
                : `<code style="color:#e74c3c;">${escapeHtml(lb.formula)}</code>`;
        }
    });

    return html;
}
