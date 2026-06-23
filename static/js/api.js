/**
 * API 通信模块
 *
 * 封装与后端的 HTTP 通信，包括：
 * - 非流式问答请求 (qa)
 * - 流式问答请求 (qaStream) — 基于 SSE + ReadableStream
 */

const API_BASE = "";

/**
 * 非流式问答
 * @param {string} query - 用户提问
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{answer: string, session_id: string}>}
 */
export async function qa(query, sessionId) {
    const resp = await fetch(`${API_BASE}/api/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, session_id: sessionId }),
    });

    const result = await resp.json();
    if (resp.status === 429) {
        const retryAfter = resp.headers.get("Retry-After") || "?";
        throw new Error(`访问过于频繁：${result.msg}（${retryAfter}秒后可重试）`);
    }
    if (resp.status !== 200 || result.code !== 200) {
        throw new Error(result.msg || "请求失败");
    }
    return result.data;
}

/**
 * 流式问答 — 通过 SSE 逐 token 推送
 *
 * @param {string} query - 用户提问
 * @param {string} sessionId - 会话 ID
 * @param {object} callbacks - 回调函数集合
 * @param {function} callbacks.onMeta - 收到元信息时调用 ({session_id})
 * @param {function} callbacks.onToken - 收到 token 时调用 (token)
 * @param {function} callbacks.onDone - 流结束时调用
 * @param {function} callbacks.onError - 出错时调用 (errorMessage)
 */
export async function qaStream(query, sessionId, callbacks) {
    const { onMeta, onToken, onDone, onError } = callbacks;

    try {
        const resp = await fetch(`${API_BASE}/api/qa/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query, session_id: sessionId }),
        });

        if (resp.status === 429) {
            const result = await resp.json().catch(() => ({}));
            throw new Error(result.msg || "访问过于频繁");
        }
        if (!resp.ok) {
            const result = await resp.json().catch(() => ({}));
            throw new Error(result.msg || `HTTP ${resp.status}`);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // 保留不完整的行

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;

                const dataStr = line.slice(6).trim();
                if (!dataStr) continue;

                let event;
                try {
                    event = JSON.parse(dataStr);
                } catch {
                    continue; // 跳过解析失败的行
                }

                switch (event.type) {
                    case "meta":
                        onMeta && onMeta(event);
                        break;
                    case "token":
                        onToken && onToken(event.content);
                        break;
                    case "done":
                        onDone && onDone();
                        return;
                    case "error":
                        onError && onError(event.message);
                        return;
                }
            }
        }

        // 如果循环结束没有收到 done 信号，也算完成
        onDone && onDone();

    } catch (err) {
        if (err.name === "AbortError") {
            // 用户主动取消
            return;
        }
        onError && onError(err.message);
    }
}
