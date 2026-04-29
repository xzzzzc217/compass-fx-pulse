<template>
  <div class="news-list">
    <h1>新闻列表</h1>
    <ul>
      <li v-for="news in paginatedNews" :key="news.id" @click="goToNewsDetail(news.id)">
        <h2>{{ news.title }}</h2>
        <p>{{ news.summary }}</p>
      </li>
    </ul>

    <!-- 分页按钮 -->
    <div class="pagination">
      <button @click="prevPage" :disabled="currentPage === 1">上一页</button>
      <span>第 {{ currentPage }} 页 / 共 {{ totalPages }} 页</span>
      <button @click="nextPage" :disabled="currentPage === totalPages">下一页</button>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      newsList: [
        { id: 1, title: '新闻标题1', summary: '这是新闻1的简介', content: '这是新闻1的详细内容...' },
        { id: 2, title: '新闻标题2', summary: '这是新闻2的简介', content: '这是新闻2的详细内容...' },
        { id: 3, title: '新闻标题3', summary: '这是新闻3的简介', content: '这是新闻3的详细内容...' },
        { id: 4, title: '新闻标题4', summary: '这是新闻4的简介', content: '这是新闻4的详细内容...' },
        { id: 5, title: '新闻标题5', summary: '这是新闻5的简介', content: '这是新闻5的详细内容...' },
        { id: 6, title: '新闻标题6', summary: '这是新闻6的简介', content: '这是新闻6的详细内容...' },
        { id: 7, title: '新闻标题7', summary: '这是新闻7的简介', content: '这是新闻7的详细内容...' },
        { id: 8, title: '新闻标题8', summary: '这是新闻8的简介', content: '这是新闻8的详细内容...' },
        { id: 9, title: '新闻标题9', summary: '这是新闻9的简介', content: '这是新闻9的详细内容...' },
        { id: 10, title: '新闻标题10', summary: '这是新闻10的简介', content: '这是新闻10的详细内容...' },
      ],
      currentPage: 1, // 当前页码
      pageSize: 3, // 每页显示的新闻数量
    };
  },
  computed: {
    // 计算总页数
    totalPages() {
      return Math.ceil(this.newsList.length / this.pageSize);
    },
    // 获取当前页的新闻数据
    paginatedNews() {
      const start = (this.currentPage - 1) * this.pageSize;
      const end = start + this.pageSize;
      return this.newsList.slice(start, end);
    },
  },
  methods: {
    goToNewsDetail(id) {
      this.$router.push(`/news/${id}`);
    },
    // 上一页
    prevPage() {
      if (this.currentPage > 1) {
        this.currentPage--;
      }
    },
    // 下一页
    nextPage() {
      if (this.currentPage < this.totalPages) {
        this.currentPage++;
      }
    },
  },
};
</script>

<style scoped>
.news-list {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
}

ul {
  list-style-type: none;
  padding: 0;
}

li {
  margin-bottom: 20px;
  cursor: pointer;
  border-bottom: 1px solid #ccc;
  padding-bottom: 10px;
}

li h2 {
  margin: 0;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
}

button {
  padding: 5px 10px;
  background-color: rgb(146, 18, 18);
  color: white;
  border: none;
  cursor: pointer;
}

button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

button:hover:not(:disabled) {
  background-color: rgb(146, 18, 18);
}
</style>
