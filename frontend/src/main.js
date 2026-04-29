// The Vue build version to load with the `import` command
// (runtime-only or standalone) has been set in webpack.base.conf with an alias.
import Vue from 'vue';
import App from './App';
import router from './router';
import ElementUI from 'element-ui'; // 引入 Element UI
import 'element-ui/lib/theme-chalk/index.css'; // 引入 Element UI 的样式文件


Vue.use(ElementUI); // 全局使用 Element UI

Vue.config.productionTip = false;

new Vue({
  router, // 使用路由
  render: (h) => h(App),
}).$mount('#app');
