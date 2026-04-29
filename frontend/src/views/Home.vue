<template>
  <div class="image-container">
    <img src="../assets/background1.png" alt="填充图片" class="fill-image">
  </div>
</template>

<style scoped>
/* 确保容器充满页面 */
.image-container {
  position: relative; /* 相对定位 */
  width: 100vw; /* 视口宽度 */
  height: 82vh; /* 视口高度 */
  overflow: hidden; /* 隐藏超出部分 */
  z-index: 1;
}

/* 图片充满容器 */
.fill-image {
  position: absolute; /* 绝对定位 */
  top: 0;
  left: 0;
  width: 98.125%; /* 宽度充满容器 */
  height: 100%; /* 高度充满容器 */
  object-fit: cover; /* 保持比例并填充容器 */
}
</style>

