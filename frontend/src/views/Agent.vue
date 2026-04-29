<template>
  <div class="agent-container">
    <div class="left-panel">
      <h2>智能体调用追踪</h2>
      <div class="examples">
        <p>试试问：</p>
        <button v-for="ex in examples" :key="ex" class="example-btn" @click="userInput=ex">
          {{ ex }}
        </button>
      </div>

      <div class="trace-panel">
        <h3>Agent 推理步骤</h3>
        <div v-if="!traces.length" class="placeholder">
          调用工具时这里会显示 Agent 的规划与执行轨迹
        </div>
        <div v-for="(t, i) in traces" :key="i" :class="['trace-item', t.kind]">
          <div class="trace-header">
            <span class="trace-kind">{{ traceLabel(t.kind) }}</span>
            <span class="trace-time">{{ traceTiming(t) }}</span>
          </div>
          <div v-if="t.kind === 'plan'" class="trace-body">
            <strong>规划调用：</strong>{{ t.tools.join(', ') }}
            <span v-if="t.llm_decide_ms" class="latency">LLM 决策 {{ t.llm_decide_ms }}ms</span>
          </div>
          <div v-else-if="t.kind === 'synth_start'" class="trace-body">
            <strong>开始合成回答</strong>
            <span class="latency">已用时 {{ t.elapsed_ms }}ms</span>
          </div>
          <div v-else-if="t.kind === 'reflection'" class="trace-body">
            <div>
              <strong>质量审查 (round {{ (t.retry || 0) + 1 }})：</strong>
              <span :class="['score-pill', t.score >= 7 ? 'pass' : 'fail']">{{ t.score }}/10</span>
              <span v-if="t.reflect_ms" class="latency">耗时 {{ t.reflect_ms }}ms</span>
            </div>
            <div v-if="t.issues" class="reflection-issue"><strong>问题：</strong>{{ t.issues }}</div>
            <div v-if="t.suggestion" class="reflection-issue"><strong>建议：</strong>{{ t.suggestion }}</div>
            <div v-if="t.score < 7" class="retry-note">↻ 触发重新合成</div>
          </div>
          <div v-else-if="t.kind === 'tool_result'" class="trace-body">
            <div>
              <strong>工具：</strong><code>{{ t.name }}</code>
              <span v-if="t.tool_exec_ms" class="latency">耗时 {{ t.tool_exec_ms }}ms</span>
            </div>
            <div><strong>参数：</strong><pre>{{ JSON.stringify(t.args, null, 2) }}</pre></div>
            <!-- Special-case RAG results: show as citation cards instead of raw JSON -->
            <div v-if="t.name === 'search_forex_knowledge' && t.result && t.result.results">
              <strong>命中 {{ t.result.n }} 条：</strong>
              <div v-for="(r, ri) in t.result.results" :key="ri" class="citation">
                <div class="cite-head">
                  <span class="cite-tag">{{ r.category }}</span>
                  <span v-if="r.currency" class="cite-tag">{{ r.currency }}</span>
                  <span class="cite-score">rerank {{ r.rerank_score }}</span>
                </div>
                <div class="cite-title">{{ r.title }}</div>
                <div class="cite-text">{{ r.text.slice(0, 220) }}{{ r.text.length > 220 ? '…' : '' }}</div>
              </div>
            </div>
            <div v-else><strong>结果：</strong><pre>{{ JSON.stringify(t.result, null, 2) }}</pre></div>
          </div>
        </div>
      </div>
    </div>

    <div class="right-panel">
      <h2>最终回答</h2>
      <div class="answer-area">
        <div v-if="!answer && !isStreaming" class="placeholder">
          输入问题后，Agent 会自动选择工具并合成回答
        </div>
        <div v-else class="answer-text markdown-body" v-html="answerHtml"></div>
      </div>
      <div class="input-area">
        <input
          v-model="userInput"
          placeholder="例如：我有 100 万美元的美元/日元敞口，1 天 99% VaR 是多少？"
          @keyup.enter="send"
          :disabled="isStreaming"
        />
        <button @click="send" :disabled="isStreaming || !userInput.trim()">
          {{ isStreaming ? '处理中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { api } from '@/config';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

// Configure marked: enable GitHub-style line breaks, no embedded HTML
marked.setOptions({ breaks: true, gfm: true });

export default {
  name: 'Agent',
  computed: {
    answerHtml() {
      if (!this.answer) return '';
      const html = marked.parse(this.answer);
      return DOMPurify.sanitize(html);
    },
  },
  data() {
    return {
      userInput: '',
      answer: '',
      traces: [],
      isStreaming: false,
      eventSource: null,
      examples: [
        '现在美元兑日元的汇率是多少？',
        '美元兑欧元在 2026 年 4 月的最大、最小、平均汇率分别是多少？',
        '我有 100 万美元的美元/日元敞口，1 天 99% VaR 是多少？',
        '预测未来 30 天的欧元/美元走势',
        '什么是 carry trade？',
        '美联储 FOMC 的决策框架是什么？',
        '日本央行 YCC 政策对日元有什么影响？',
        '港币联系汇率制度怎么运作？',
      ],
    };
  },
  methods: {
    traceLabel(kind) {
      return {
        plan: '🧠 规划',
        tool_result: '🔧 工具调用',
        synth_start: '✍️ 合成中',
        reflection: '🔍 质量审查',
      }[kind] || kind;
    },
    traceTiming(t) {
      if (t.round) return `round ${t.round}`;
      return '';
    },
    send() {
      if (!this.userInput.trim() || this.isStreaming) return;
      this.answer = '';
      this.traces = [];
      this.isStreaming = true;

      const q = encodeURIComponent(this.userInput);
      const url = api(`/api/agent?query=${q}&trace=1`);
      this.eventSource = new EventSource(url);

      this.eventSource.onmessage = (event) => {
        try {
          const obj = JSON.parse(event.data);
          if (obj.trace) {
            this.traces.push(obj.trace);
          } else if (obj.text === '[DONE]') {
            this.isStreaming = false;
            this.eventSource.close();
          } else if (obj.text && obj.text.startsWith('[ERROR]')) {
            this.answer += `\n\n${obj.text}`;
            this.isStreaming = false;
            this.eventSource.close();
          } else if (obj.text) {
            this.answer += obj.text;
          }
        } catch (e) {
          console.error('parse error:', e, event.data);
        }
      };
      this.eventSource.onerror = (e) => {
        console.error('SSE error:', e);
        this.isStreaming = false;
        if (this.eventSource) this.eventSource.close();
      };
    },
  },
  beforeDestroy() {
    if (this.eventSource) this.eventSource.close();
  },
};
</script>

<style scoped>
.agent-container {
  display: flex;
  height: calc(100vh - 100px);
  gap: 20px;
  padding: 20px;
  background-color: #ddd;
}
.left-panel {
  width: 45%;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.right-panel {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
}
.examples {
  margin-bottom: 12px;
}
.example-btn {
  display: inline-block;
  margin: 4px 4px 4px 0;
  padding: 4px 10px;
  background: #f4f4f4;
  border: 1px solid #ddd;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
}
.example-btn:hover { background: rgb(146, 18, 18); color: #fff; }

.trace-panel {
  flex: 1;
  overflow-y: auto;
  border-top: 1px solid #eee;
  padding-top: 10px;
}
.placeholder { color: #999; font-style: italic; padding: 20px; text-align: center; }
.trace-item {
  margin-bottom: 12px;
  padding: 10px;
  border-radius: 6px;
  border-left: 4px solid;
}
.trace-item.plan      { background: #fff8e1; border-color: #f2b441; }
.trace-item.tool_result { background: #e8f4fd; border-color: #1e88e5; }
.trace-item.reflection { background: #f3e5f5; border-color: #8e24aa; }
.trace-item.synth_start { background: #f5f5f5; border-color: #999; }
.score-pill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
}
.score-pill.pass { background: #c8e6c9; color: #1b5e20; }
.score-pill.fail { background: #ffcdd2; color: #b71c1c; }
.reflection-issue {
  font-size: 12px;
  color: #555;
  margin-top: 4px;
  line-height: 1.5;
}
.retry-note {
  margin-top: 6px;
  font-size: 11px;
  color: #b71c1c;
  font-weight: 600;
}
.trace-header {
  display: flex;
  justify-content: space-between;
  font-weight: 500;
  margin-bottom: 6px;
  font-size: 13px;
}
.trace-time { color: #888; font-size: 11px; }
.latency {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  background: #fff3e0;
  color: #e65100;
  border-radius: 4px;
  font-size: 11px;
}
.trace-body pre {
  background: #fafafa;
  border: 1px solid #eee;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 11px;
  max-height: 180px;
  overflow: auto;
  margin: 4px 0;
}
code {
  background: #fff;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: Consolas, monospace;
  color: rgb(146, 18, 18);
}
.citation {
  background: #fff;
  border: 1px solid #cce4f7;
  border-radius: 5px;
  padding: 8px 10px;
  margin-top: 6px;
  font-size: 12px;
}
.cite-head {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 10px;
  align-items: center;
}
.cite-tag {
  background: #e8f4fd;
  color: #1565c0;
  padding: 2px 6px;
  border-radius: 8px;
}
.cite-score {
  margin-left: auto;
  color: #888;
}
.cite-title {
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}
.cite-text {
  color: #555;
  line-height: 1.5;
  white-space: pre-wrap;
}

.answer-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #fafafa;
  border-radius: 6px;
  margin-bottom: 12px;
  line-height: 1.7;
  font-size: 14px;
}
.markdown-body >>> h1,
.markdown-body >>> h2,
.markdown-body >>> h3,
.markdown-body >>> h4 {
  margin: 16px 0 8px 0;
  font-weight: 600;
  color: #222;
  line-height: 1.3;
}
.markdown-body >>> h1 { font-size: 20px; border-bottom: 2px solid #eee; padding-bottom: 4px; }
.markdown-body >>> h2 { font-size: 18px; border-bottom: 1px solid #eee; padding-bottom: 2px; }
.markdown-body >>> h3 { font-size: 16px; }
.markdown-body >>> h4 { font-size: 14px; color: #555; }
.markdown-body >>> p { margin: 8px 0; }
.markdown-body >>> ul, .markdown-body >>> ol { padding-left: 24px; margin: 8px 0; }
.markdown-body >>> li { margin: 4px 0; }
.markdown-body >>> strong { color: rgb(146, 18, 18); font-weight: 600; }
.markdown-body >>> code {
  background: #f0f0f0;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: Consolas, monospace;
  font-size: 13px;
  color: #c7254e;
}
.markdown-body >>> pre {
  background: #f6f8fa;
  padding: 10px;
  border-radius: 5px;
  overflow-x: auto;
  margin: 8px 0;
}
.markdown-body >>> pre code {
  background: transparent;
  padding: 0;
  color: #333;
}
.markdown-body >>> blockquote {
  border-left: 4px solid rgb(146, 18, 18);
  margin: 8px 0;
  padding: 4px 12px;
  color: #666;
  background: #fff;
}
.markdown-body >>> table {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}
.markdown-body >>> th, .markdown-body >>> td {
  border: 1px solid #ddd;
  padding: 6px 10px;
}
.markdown-body >>> th { background: #f4f4f4; font-weight: 600; }
.markdown-body >>> hr {
  border: none;
  border-top: 1px solid #ddd;
  margin: 12px 0;
}
.input-area { display: flex; gap: 8px; }
.input-area input {
  flex: 1;
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 14px;
}
.input-area button {
  padding: 10px 20px;
  background: rgb(146, 18, 18);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.input-area button:disabled { background: #999; cursor: not-allowed; }
</style>
