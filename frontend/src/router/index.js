import Vue from 'vue';
import VueRouter from 'vue-router';
import NewsList from '../components/NewsList.vue'; // 新闻列表组件
import NewsDetail from '../components/NewsDetail.vue'; // 新闻详情组件
import AboutUs from '@/views/AboutUs.vue';
import FeedBack from '../views/FeedBack.vue';


Vue.use(VueRouter);


// 路由懒加载：按需加载组件
const routes = [
  {
    path: '/',
    name: 'Home',
    component: () => import('../views/Home.vue'), // 首页
  },
  {
    path: '/exchange-rate-prediction',
    name: 'ExchangeRatePrediction',
    component: () => import('../views/ExchangeRatePrediction.vue'), // 汇率预测
  },
  {
    path: '/historical-exchange-rate',
    name: 'HistoricalExchangeRate',
    component: () => import('@/views/HistoricalExchangeRate.vue'), // 历史汇率数据
  },
  {
    path: '/ai',
    name: 'GAI',
    component: () => import('@/views/AI.vue'), // 指南问答AI
  },
  {
    path: '/agent',
    name: 'Agent',
    component: () => import('@/views/Agent.vue'), // Function Calling Agent
  },
  {
    path: '/news',
    name: 'News',
    component: () => import('@/views/News.vue'), // 咨询新闻
  },
  {
    path: '/news', // 新闻列表页
    component: NewsList,
  },
  {
    path: '/news/:id', // 新闻详情页，动态路由
    component: NewsDetail,
    props: true, // 将路由参数作为 props 传递给组件
  },
  {
    path: '/', // 默认重定向到新闻列表页
    redirect: '/news',
  },
  {
    path:'/about-us',
    name:'AboutUs',
    component: AboutUs,
  },
  {
    path:'/feedback',
    name:'FeedBack',
    component:FeedBack,
  },
];

const router = new VueRouter({
  mode: 'history', // 使用 history 模式
  routes,
});

export default router;
