<template>
  <div>
    <el-menu
      :default-active="activeIndex"
      mode="horizontal"
      @select="handleSelect"
      class="custom-menu"
    >
    <el-menu-item index="/">
    <img src="./assets/logo2.png" alt="Logo" style="width: 65px; height:61px; margin-right: 8px;">
  </el-menu-item>

  <!-- 首页 -->
  <el-menu-item index="/">首页</el-menu-item>

  <!-- 汇率（带下拉菜单） -->
  <el-submenu index="2">
    <template slot="title">汇率</template>
    <el-menu-item index="/exchange-rate-prediction">汇率预测</el-menu-item>
    <el-menu-item index="/historical-exchange-rate">历史汇率数据</el-menu-item>
  </el-submenu>

  <!-- 指南问答AI -->
  <el-menu-item index="/ai">慧聚答疑</el-menu-item>

  <!-- Function Calling Agent -->
  <el-menu-item index="/agent">智能助手</el-menu-item>

  <!-- 咨询新闻 -->
  <el-menu-item index="/news">财经洞察</el-menu-item>

  <!-- 更多（带下拉菜单） -->
  <el-submenu index="more">
    <template slot="title">更多</template>
    <el-menu-item index="/about-us">关于我们</el-menu-item>
    <el-menu-item index="/feedback">意见反馈</el-menu-item>
  </el-submenu>
  <div
      id="google_translate_element"
      style="
        position: absolute;
        top: 10px;
        right: 10px;
        z-index: 2000;
        opacity: 0.7;
      "
    ></div>
</el-menu>

    <router-view/>

    <!-- 底部友情链接 -->
    <footer class="footer-links">
      <div class="links-container">
        <h3>友情链接:</h3>
        <ul>
          <li><a href="https://www.nber.org/" target="_blank">国民经济研究局</a></li>
          <li><a href="https://cepr.org/" target="_blank">经济政策研究中心</a></li>
          <li><a href="https://data.worldbank.org/" target="_blank">世界银行数据库</a></li>
          <li><a href="https://www.fma.org/" target="_blank">国际金融管理协会</a></li>
          <li><a href="https://www.wsj.com/" target="_blank">华尔街日报</a></li>
        </ul>
      </div>
    </footer>
  </div>
</template>

<script>
export default {
  mounted() {
	    document
.addEventListener("visibilitychange", this.watchVisibility); // 监听页面hide or visible
	  },
	  methods: {
	    watchVisibility() {
	      if (document.visibilityState == "visible") {
	        setTimeout(() => {
	          location
.reload();
	        }, 1 * 1000);
	      }
	    },
	  },
  data() {
    return {
      activeIndex: '/', // 默认激活的菜单项
    };
  },
  methods: {
    handleSelect(key) {
      // 路由跳转
      this.$router.push(key);
    },
  },
};
</script>

<style scoped>
/* 自定义菜单样式 */

.custom-menu {
  width: 100%; /* 菜单宽度 */
  background-color: #c5c4c4; /* 背景颜色为白色 */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); /* 添加阴影效果 */
  border-bottom: none;
  height: 80px; /* 调整导航栏高度 */
}

/* 菜单项样式 */
.custom-menu >>> .el-menu-item {
  font-size: 25px; /* 字体大小 */
  padding: 0 30px; /* 调整内边距 */
  color: #333; /* 文字颜色为深灰色 */
  background-color: transparent; /* 背景颜色为透明 */
  transition: color 0.3s, background-color 0.3s; /* 添加过渡效果 */
  border-bottom: none;
  font-weight: 500; /* 字体加粗 */
  height: 80px; /* 调整菜单项高度 */
  line-height: 80px; /* 垂直居中 */
}

/* 菜单项悬停样式 */
.custom-menu >>> .el-menu-item:hover {
  color: #ffffff !important; /* 文字颜色变为白色 */
  background-color: rgb(146, 18, 18) !important; /* 背景颜色变为红色 */
  border-bottom: none;
}

/* 下拉菜单标题样式 */
.custom-menu >>> .el-submenu__title {
  font-size: 25px; /* 字体大小 */
  padding: 0 30px; /* 调整内边距 */
  color: #333; /* 文字颜色为深灰色 */
  background-color: transparent; /* 背景颜色为透明 */
  transition: color 0.3s, background-color 0.3s; /* 添加过渡效果 */
  border-bottom: none;
  font-weight: 500; /* 字体加粗 */
  height: 80px; /* 调整下拉菜单标题高度 */
  line-height: 80px; /* 垂直居中 */
}

/* 下拉菜单标题悬停样式 */
.custom-menu >>> .el-submenu__title:hover {
  color: #ffffff !important; /* 文字颜色变为白色 */
  background-color: rgb(146, 18, 18) !important; /* 背景颜色变为红色 */
  border-bottom: none;
}

/* 下拉菜单项样式 */
.custom-menu >>> .el-submenu .el-menu-item {
  font-size: 16px; /* 下拉菜单项的字体大小 */
  padding: 0 30px; /* 调整内边距 */
  color: #333; /* 文字颜色为深灰色 */
  background-color: #ffffff; /* 背景颜色为白色 */
  transition: color 0.3s, background-color 0.3s; /* 添加过渡效果 */
  border-bottom: none;
  height: 50px; /* 调整下拉菜单项高度 */
  line-height: 50px; /* 垂直居中 */
}

/* 下拉菜单项悬停样式 */
.custom-menu >>> .el-submenu .el-menu-item:hover {
  color: #ffffff !important; /* 文字颜色变为白色 */
  background-color: rgb(146, 18, 18) !important; /* 背景颜色变为红色 */
  border-bottom: none;
}

/* 下拉菜单整体样式 */
.custom-menu >>> .el-submenu .el-menu {
  background-color: #ffffff; /* 下拉菜单背景颜色为白色 */
  border: 1px solid #e6e6e6; /* 添加边框 */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); /* 添加阴影效果 */
}

/* 底部友情链接样式 */
.footer-links {
  margin-top: auto; /* 确保底部始终在页面最下方 */
  padding: 10px 30px; /* 调整内边距 */
  background-color: #ddd;
  text-align: center;
  border-top: 1px solid #e6e6e6;
}

.links-container {
  max-width: 1200px;
  margin: 0 auto;
  display: flex; /* 使用 flex 布局 */
  align-items: center; /* 垂直居中 */
  justify-content: center; /* 水平居中 */
  gap: 10px; /* 设置元素之间的间距 */
}

.links-container h3 {
  margin: 0; /* 去掉默认的外边距 */
  font-size: 16px;
  color: #333;
}

.links-container ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  gap: 10px; /* 设置链接之间的间距 */
}

.links-container ul li {
  display: inline;
}

.links-container ul li a {
  color: rgb(146, 18, 18);
  text-decoration: none;
  font-size: 14px;
}

.links-container ul li a:hover {
  text-decoration: underline;
}

</style>
