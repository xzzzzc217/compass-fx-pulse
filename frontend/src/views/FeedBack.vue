<template>
    <div class="FeedBack-container" v-if="showFeedBack">
      <h2>意见反馈</h2>
      <!-- 关闭按钮 -->
      <button @click="closeFeedBack" class="close-button">✕</button>
      <form @submit.prevent="submitFeedBack">
        <label for="FeedBack">请在这里写下您的宝贵意见：</label>
        <textarea id="FeedBack" v-model="FeedBack" placeholder="请输入您的意见..." required></textarea>
        <button type="submit">提交反馈</button>
      </form>
      <p v-if="submitted" class="thank-you">感谢您的反馈！</p>
    </div>
  </template>

  <script>
  export default {
    data() {
      return {
        FeedBack: '',
        submitted: false,
        showFeedBack: true
      };
    },
    methods: {
      submitFeedBack() {
        if (this.FeedBack.trim()) {
          // 这里可以添加将反馈发送到服务器的逻辑
          console.log('反馈意见:', this.FeedBack);
          this.submitted = true;
          this.FeedBack = ''; // 清空输入框
          setTimeout(() => {
            this.submitted = false; // 一段时间后隐藏感谢信息
          }, 3000);
        }
      },
      closeFeedBack() {
        this.showFeedBack = false;
      }
    }
  }
  </script>

  <style scoped>
  .FeedBack-container {
    width: 100%;
    min-height: 90vh;
    margin: 50px auto;
    padding: 20px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    background-color: #fff;
    border-radius: 8px;
    text-align: center;
    position: relative; /* 添加相对定位 */
  }

  h2 {
    margin-bottom: 20px;
    color: #333;
  }

  label {
    display: block;
    margin-bottom: 10px;
    font-size: 16px;
    color: #666;
  }

  textarea {
    width: 100%;
    height: 60vh;
    padding: 10px;
    margin-bottom: 20px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 16px;
    resize: vertical;
  }

  button {
    padding: 10px 20px;
    background-color: rgb(139, 0, 0);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 16px;
  }

  button:hover {
    background-color: rgb(146, 18, 18);
  }

  .thank-you {
    margin-top: 20px;
    color: green;
    font-size: 18px;
  }

  .close-button {
    position: absolute; /* 设置绝对定位 */
    top: 10px; /* 距离顶部的距离 */
    right: 10px; /* 距离右侧的距离 */
    background-color: transparent;
    border: none;
    cursor: pointer;
    font-size: 20px;
    color: #666;
  }

  .close-button:hover {
    color: red;
  }
  </style>
