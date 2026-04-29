<template>
  <div id="app">
    <div class="list-container">
      <!-- 进度条 -->
      <div class="progress-bar" :style="{ width: progressBar + '%' }"></div>

      <!-- 列表主体 -->
      <ul class="item-list">
        <li v-for="(item, index) in displayedItems" :key="index" @click="goToDetail(item.id)" class="item">
          <div class="item-content">
            <!-- 使用 router-link 跳转到详情页 -->
            <router-link :to="`/news/${item.id}`">
              <img :src="item.image" alt="" class="item-image">
            </router-link>
            <div class="item-text">
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
              <ul class="item-details">
                <li v-for="(detail, i) in item.details" :key="i">{{ detail }}</li>
              </ul>
            </div>
          </div>
        </li>
      </ul>

      <!-- 分页控件 -->
      <el-pagination
        layout="prev, pager, next"
        :total="items.length"
        :page-size="pageSize"
        :current-page.sync="currentPage"
        @current-change="handlePageChange"
        style="text-align: center; margin-top: 20px;"
      />
    </div>
  </div>
</template>

<script>
export default {
  name: 'News',
  data() {
    return {
      items: [
        {
          id: 1,
          image: require('@/assets/news1.jpg'),
          title: '“AI炒股神话”背后 | 金融“3·15”',
          description: '打着AI（人工智能）幌子行“非法荐股”之实的欺诈套路横行。',
          details: [
            'AI炒股“暴富神话”背后可能隐藏着诸多灰色地带，包括非法荐股行为、虚假宣传与诈骗、个人信息泄露与非法使用等。'
          ],
        },
        {
          id: 2,
          image: require('@/assets/news2.jpg'),
          title: '人民银行将“择机降准降息” 权威专家解读如何择机？',
          description: '如何“择机”，我国的货币政策空间是否充足，成为市场关心的重要话题。',
          details: [
            '“适度宽松”下，人民银行打出货币政策“组合拳”',
            '降准还有空间，要灵活掌握时机发挥最大政策效能',
            '推动社会综合融资成本下降需要综合施策',
            '货币政策工具箱丰富，各种工具将灵活搭配'
          ],
        },
        {
         id: 3,
          image: require('@/assets/news3.jpg'),
       title: '“新债王”冈拉克大胆预测：黄金有望冲向4000美元！',
       description: '杰弗里·冈拉克（Jeffrey Gundlach）在其最新宏观经济展望中表示，现在正是进行国际多元化投资的时刻。',
        details: [

      ],
        },{
  id: 4,
  image: require('@/assets/news4.jpg'),
  title: '日本核心通胀放缓至2.9%，日元反弹推动进口下降，市场预计日央行将继续加息',
  description: '日本2月核心CPI同比增速可能放缓至2.9%，低于1月的3.2%',
  details: [

  ],
},{
  id: 5,
  image: require('@/assets/news5.jpg'),
  title: '欧元多头剑指1.10关口！美元跌势终结信号已现？五大货币下周决战关键位！',
  description: '全球外汇市场在多重因素的博弈下呈现显著分化。',
  details: [
    '来源：汇通网'
  ],
},{
  id: 6,
  image: require('@/assets/news6.jpg'),
  title: '最新CPI、PPI数据对美联储来说都不是好消息？',
  description: '尽管表面数据显示通胀温和，但有一些迹象恐怕正暗示：降息遥遥无期……',
  details: [
    '　金十数据'
  ],
},{
  id: 7,
  image: require('@/assets/news7.jpg'),
  title: '三大央行下周接连议息，汇价走势波谲云诡？聚焦3月关键节点！',
  description: '来源：汇通财经',
  details: [

  ],
},{
  id: 8,
  image: require('@/assets/news8.jpg'),
  title: '花旗：韩国经济增长面临挑战',
  description: '来源：Investing.com',
  details: [
    '花旗分析师在3月10-11日首尔宏观考察期间，就韩国经济和政治形势提供了深入见解。'
  ],
},{
  id: 9,
  image: require('@/assets/news.jpg'),
  title: '人工智能助力医疗行业',
  description: 'AI技术在疾病诊断和治疗中的应用日益广泛',
  details: [
    'AI辅助诊断系统准确率超过90%',
    '多家医院引入AI机器人进行手术',
    '政府推动AI医疗标准化建设'
  ],
}

        // 其他新闻项...
      ],
      currentPage: 1,
      pageSize: 4,
      progressBar: 0,
    };
  },
  computed: {
    displayedItems() {
      const start = (this.currentPage - 1) * this.pageSize;
      const end = this.currentPage * this.pageSize;
      return this.items.slice(start, end);
    },
  },
  methods: {
    goToDetail(id) {
      this.$router.push({ path: `/news/${id}` }); // 跳转到详情页
    },
    handlePageChange(page) {
      this.currentPage = page;
      window.scrollTo(0, 0);
    },
    handleScroll() {
      let scrollTop = document.documentElement.scrollTop || document.body.scrollTop;
      let scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight;
      let clientHeight = document.documentElement.clientHeight;
      let scrolled = (scrollTop / (scrollHeight - clientHeight)) * 100;
      this.progressBar = Math.floor(scrolled);
    },
  },
  mounted() {
    window.addEventListener('scroll', this.handleScroll);
  },
  beforeDestroy() {
    window.removeEventListener('scroll', this.handleScroll);
  },
};
</script>

<style scoped>
#app {
  background-image: url('~@/assets/white.png');
  background-size: cover;
  background-color: aliceblue;
  background-position: center;
  background-repeat: no-repeat;
  overflow: hidden;
  margin-top: 0%;
  z-index: 10;

  font-family: 'Avenir', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: #2c3e50;
  margin-top: 60px;
}

.list-container {
  padding: 20px;
}

.item-list {
  display: flex;
  flex-wrap: wrap;
}

.item {
  width: calc(50% - 50px); /* Adjust for spacing */
  margin: 5px;
  border: 1px solid #ddd;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  display: flex;
}

.item-content {
  display: flex;
  align-items: center;
  padding: 10px;
}

.item-image {
  width: 50%;
  height: auto;
  object-fit: cover;
}

.item-text {
  width: 50%;
  padding-left: 10px;
}

.item-text h3 {
  font-size: 18px;
  margin-bottom: 5px;
}

.item-text p {
  font-size: 14px;
  margin-bottom: 10px;
}

.item-details li {
  list-style-type: none;
  font-size: 12px;
  line-height: 1.5;
}

.progress-bar {
  height: 5px;
  background-color: rgb(146, 18, 18);
  position: fixed;
  top: 0;
  left: 0;
  z-index: 1000;
}
</style>
