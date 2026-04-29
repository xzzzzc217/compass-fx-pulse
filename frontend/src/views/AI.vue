<template>
  <div class="container">
    <!-- 历史对话栏 -->
    <div class="history">
      <h3>历史对话</h3>
      <div v-for="(message, index) in historyMessages" :key="index" class="history-msg">
        <p class="sender-tag"><strong>{{ message.sender }}:</strong></p>
        <div v-if="message.sender === '系统'" class="markdown-body" v-html="renderMd(message.text)"></div>
        <div v-else>{{ message.text }}</div>
        <hr v-if="message.separator" />
      </div>
    </div>
    
    <!-- 对话框 -->
    <div class="chatbox">
      <div class="chat-history" ref="chatHistory">
        <img v-if="chatMessages.length === 0" src="@/assets/AIbackground1.png" alt="robot" class="center-image" />
        <div v-for="(message, index) in chatMessages" :key="index" :class="{'user-message': message.sender === '用户', 'system-message': message.sender === '系统'}">
          <div :class="['message', message.sender === '用户' ? 'user' : 'system']">
            <div class="avatar">
              <img :src="message.sender === '用户' ? userAvatar : systemAvatar" alt="avatar" />
            </div>
            <div class="message-text markdown-body">
              <p class="sender-tag"><strong>{{ message.sender }}:</strong></p>
              <div v-if="message.sender === '系统'" v-html="renderMd(message.text)"></div>
              <div v-else>{{ message.text }}</div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="chat-input">
        <input type="text" v-model="userInput" placeholder="请输入您的问题..." />
        <button @click="sendMessage">发送</button>
      </div>
    </div>
  </div>
</template>

<script>
import Vue from 'vue';
import VueRouter from 'vue-router'; // 确保使用的是 Vue Router 3.x 版本
import { api } from '@/config';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({ breaks: true, gfm: true });

export default {
  name: "AI",
  data() {
    return {
      userInput: '',
      chatMessages: [],
      historyMessages: [],
      userAvatar: require('@/assets/logo2.png'),
      systemAvatar: require('@/assets/touxiang1.png'),
      messageCount: 0,
    };
  },
  methods: {
    renderMd(text) {
      if (!text) return '';
      return DOMPurify.sanitize(marked.parse(text));
    },
    async loadHistory() {
      try {
      // 发送请求获取多组对话数据
      const response = await fetch(api('/api/multiple-messages'));
      const conversations = await response.json();

      // 遍历每个对话并更新聊天和历史记录
      conversations.forEach((conversation, index) => {
        // 将当前对话添加到历史记录，并在最后添加分隔符（除了最后一组）
        this.historyMessages.push(...conversation, ...(index < conversations.length - 1 ? [{ separator: true }] : []));

        // 滚动到底部
        this.scrollToBottom();
      });
    } catch (error) {
      console.error('Error fetching multiple messages:', error);
    }

    },
    sendMessage() {
      if (this.userInput.trim() === '') return;

      // 添加用户消息
      this.chatMessages.push({ sender: '用户', text: this.userInput });

      const query = encodeURIComponent(this.userInput);
      this.userInput = '';
      

      // 发送用户消息到后端并处理流式响应
      const eventSource = new EventSource(api(`/api/messages?query=${query}`));

      eventSource.onmessage = (event) => {
        if (JSON.parse(event.data).text === "[DONE]") {

          this.sendCountToBackend(this.messageCount++);
          eventSource.close(); // 关闭 EventSource 连接
          return;
        }

        try {
          const chunk = JSON.parse(event.data); // 解析 JSON
          if (chunk.text) {
            const lastMessageIndex = this.chatMessages.length - 1;
            if (lastMessageIndex >= 0 && this.chatMessages[lastMessageIndex].sender === "系统") {
              this.chatMessages[lastMessageIndex].text += chunk.text;
            } else {
              this.chatMessages.push({ sender: "系统", text: chunk.text });
            }
            this.scrollToBottom();
          }
        } catch(error) {
          console.error("JSON 解析错误:", error, "原始数据:", event.data);
        }
      };
    },
    sendCountToBackend(count) {
      const conversationData = this.chatMessages.map(message => ({
      sender: message.sender,
      text: message.text,
      chatcount:count
    }));
      fetch(api('/api/count'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(conversationData )
      }).then(response => response.json())
        .catch(error => console.error('Error sending count to backend:', error));
    },
    scrollToBottom() {
      this.$nextTick(() => {
        const chatHistory = this.$refs.chatHistory;
        if (chatHistory) {
          chatHistory.scrollTop = chatHistory.scrollHeight;
        }
      });
    },
    handleBeforeUnload() {
      this.messageCount = 0; // 刷新页面时重置计数
    },
    handleRouteChange() {
      this.messageCount = 0; // 路由变化时重置计数
    }
  },
  mounted() {
    this.loadHistory();
    window.addEventListener('beforeunload', this.handleBeforeUnload);
    this.$router.beforeEach((to, from, next) => {
      this.handleRouteChange();
      next();
    });
    this.scrollToBottom();
    
  },
  beforeDestroy() {
    window.removeEventListener('beforeunload', this.handleBeforeUnload);
  }
};
</script>
  
  <style scoped>
  .container {
    display: flex;
    height: 100vh;
    background-color: #ddd;
  }
  
  .history {
    min-width: 20%;
    max-width: 20%;
    background-color: #fff;
    border-right: 1px solid #ddd;
    overflow-y: scroll;
    padding: 10px;
    box-sizing: border-box;
  }
  .sender-tag { margin: 0 0 4px 0; font-size: 13px; color: #666; }
  .history-msg { margin-bottom: 10px; padding-bottom: 6px; }
  .markdown-body >>> h1,
  .markdown-body >>> h2,
  .markdown-body >>> h3,
  .markdown-body >>> h4 {
    margin: 10px 0 6px 0; font-weight: 600; color: #222;
  }
  .markdown-body >>> h1 { font-size: 18px; border-bottom: 2px solid #eee; padding-bottom: 2px; }
  .markdown-body >>> h2 { font-size: 16px; border-bottom: 1px solid #eee; padding-bottom: 2px; }
  .markdown-body >>> h3 { font-size: 15px; }
  .markdown-body >>> h4 { font-size: 14px; color: #555; }
  .markdown-body >>> p  { margin: 6px 0; }
  .markdown-body >>> ul, .markdown-body >>> ol { padding-left: 20px; margin: 6px 0; }
  .markdown-body >>> li { margin: 3px 0; }
  .markdown-body >>> strong { color: rgb(146, 18, 18); font-weight: 600; }
  .markdown-body >>> code { background:#f0f0f0; padding:1px 5px; border-radius:3px; font-family:Consolas,monospace; font-size:13px; color:#c7254e; }
  .markdown-body >>> pre  { background:#f6f8fa; padding:8px; border-radius:5px; overflow-x:auto; margin:6px 0; }
  .markdown-body >>> pre code { background: transparent; padding: 0; color: #333; }
  .markdown-body >>> hr { border:none; border-top:1px solid #ddd; margin:10px 0; }
  .markdown-body >>> blockquote { border-left:3px solid rgb(146,18,18); margin:6px 0; padding:2px 10px; color:#666; }
  .markdown-body >>> table { border-collapse:collapse; margin:6px 0; width:100%; }
  .markdown-body >>> th, .markdown-body >>> td { border:1px solid #ddd; padding:5px 8px; }
  .markdown-body >>> th { background:#f4f4f4; font-weight:600; }
  
  .chatbox {
    flex-grow: 1;
    background-color: #fff;
    padding: 20px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    border: 15px solid rgb(139, 0, 0);
    border-radius: 60px;
    margin-left: 10px;
    margin-right: 10px;
  }
  
  .chat-history {
    overflow-y: scroll;
    flex-grow: 1;
    margin-bottom: 10px;
    position: relative;
  }
  
  .center-image {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    max-width: 1000px;
    opacity: 0.5;
  }
  
  .chat-input {
    display: flex;
    align-items: center;
  }
  
  .chat-input input {
    width: 80%;
    padding: 10px;
    font-size: 16px;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  .chat-input button {
    padding: 10px;
    font-size: 16px;
    background-color: rgb(139, 0, 0);
    color: #fff;
    border: none;
    border-radius: 4px;
    margin-left: 10px;
  }
  
  .message {
    display: flex;
    align-items: flex-start;
    margin-bottom: 10px;
  }
  
  .message .avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    overflow: hidden;
    margin-right: 10px;
  }
  
  .message .avatar img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  
  .message-text {
    max-width: 70%;
    padding: 10px;
    border-radius: 10px;
    background-color: #f1f1f1;
    word-wrap: break-word;
    white-space: pre-wrap;
  }
  
  .user {
    flex-direction: row-reverse;
  }
  
  .system {
    flex-direction: row;
  }
  
  .user .message-text {
    background-color: rgb(139, 0, 0);
    color: white;
    text-align: right;
    margin-left: 10px;
  }
  
  .system .message-text {
    background-color: #f0f0f0;
    color: #333;
    text-align: left;
    margin-right: 10px;
  }
  </style>
