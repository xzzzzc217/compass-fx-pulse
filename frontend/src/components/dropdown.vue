<template>
    <div class="dropdown">
      <!-- 触发按钮 -->
      <button @click="toggleDropdown" class="dropdown-button">选择一项</button>
      
      <!-- 下拉菜单 -->
      <div v-if="isOpen" class="dropdown-content">
        <div v-for="(item, index) in items" :key="index" @click="selectItem(item)" class="dropdown-item">
          {{ item }}
        </div>
      </div>
    </div>
  </template>
  
  <script>
  export default {
    name: 'Dropdown',
    data() {
      return {
        isOpen: false,
        items: ['选项一', '选项二', '选项三']
      }
    },
    methods: {
      toggleDropdown() {
        this.isOpen = !this.isOpen;
      },
      selectItem(item) {
        console.log('选择了:', item);
        this.isOpen = false; // 选择后关闭下拉框
      }
    }
  }
  </script>
  
  <style scoped>
  /* 设置整个下拉框的基本样式 */
  .dropdown {
    position: relative;
    display: inline-block;
  }
  
  /* 按钮样式 */
  .dropdown-button {
    background-color: transparent;
    border: none;
    color: white;
    padding: 10px;
    font-size: 16px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }
  
  .dropdown-button:hover {
    background-color: rgba(255, 255, 255, 0.2); /* 鼠标悬停时稍微变亮 */
  }
  
  /* 下拉菜单样式 */
  .dropdown-content {
    position: absolute;
    background-color: transparent;
    min-width: 160px;
    box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.2);
    z-index: 1;
  }
  
  /* 下拉菜单中的每个项 */
  .dropdown-item {
    color: white;
    padding: 12px 16px;
    text-decoration: none;
    display: block;
    transition: background-color 0.3s ease;
  }
  
  .dropdown-item:hover {
    background-color: rgba(255, 255, 255, 0.2);
  }
  
  /* 确保点击外部区域时关闭下拉框 */
  body {
    margin: 0;
    height: 100%;
    overflow: hidden;
  }
  
  body.click-off-close .dropdown-content {
    display: none;
  }
  
  body.click-off-close .dropdown.open .dropdown-content {
    display: block;
  }
  </style>