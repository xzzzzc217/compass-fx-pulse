<template>
  <div class="exchange-rate-prediction">
    <!-- 左侧内容 -->
    <div class="left-content">
      <h1>汇率预测</h1>

      <div class="select-container">
        <p>选择货币A</p>
        <el-select v-model="currencyA" placeholder="请选择货币A" class="currency-select">
          <el-option
            v-for="item in currencyOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          ></el-option>
        </el-select>
      </div>
      <div class="select-container">
        <p>选择货币B</p>
        <el-select v-model="currencyB" placeholder="请选择货币B" class="currency-select">
          <el-option
            v-for="item in currencyOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          ></el-option>
        </el-select>
      </div>
    </div>

    <!-- 右侧图表 -->
    <div class="right-content">
      <div class="chart-controls">
        <el-button
          @click="switchChart('line')"
          :type="chartType === 'line' ? 'primary' : ''"
          class="chart-button"
        >
          折线图
        </el-button>
        <!-- <el-button
          @click="switchChart('bar')"
          :type="chartType === 'bar' ? 'primary' : ''"
          class="chart-button"
        >
          柱状图
        </el-button> -->
      </div>

      <!-- 确保 div 绑定后再渲染图表 -->
      <div v-if="chartReady" ref="chart" class="chart-container"></div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import * as echarts from 'echarts';
import { nextTick } from 'vue';
import { api } from '@/config';

export default {
  name: 'ExchangeRatePrediction',
  data() {
    return {
      currencyA: '',
      currencyB: '',
      currencyOptions: [
        { value: 'USD', label: '美元 (USD)' },
        { value: 'EUR', label: '欧元 (EUR)' },
        { value: 'JPY', label: '日元 (JPY)' },
        { value: 'HKD', label: '港币 (HKD)' },
        { value: 'GBP', label: '英镑 (GBP)' },
        { value: 'AUD', label: '澳元 (AUD)' },
      ],
      chart: null,
      chartType: 'line',
      chartData: { dates: [], rates: [] },
      chartReady: false, // 控制图表区域是否渲染
    };
  },
  watch: {
    currencyA() {
      if (this.currencyA && this.currencyB) {
        this.fetchExchangeRateData();
      }
    },
    currencyB() {
      if (this.currencyA && this.currencyB) {
        this.fetchExchangeRateData();
      }
    }
  },
  async mounted() {
    await nextTick(); // 等待 DOM 渲染完成
    this.chartReady = true;
    await nextTick(); // 确保 v-if 绑定后再初始化图表
    this.initChart();
    window.addEventListener('resize', this.resizeChart);
  },
  beforeDestroy() {
    window.removeEventListener('resize', this.resizeChart);
    if (this.chart) {
      this.chart.dispose();
    }
  },
  methods: {
    async initChart() {
      await nextTick(); // 确保 DOM 已经渲染
      if (this.$refs.chart) {
        this.chart = echarts.init(this.$refs.chart);
        this.renderChart();
      }
    },

    renderChart() {
    if (!this.chart) {
      return;
    }

    const dates = this.chartData.dates.length ? this.chartData.dates : ['无数据'];
    const rates = this.chartData.rates.length ? this.chartData.rates : [0];

    const option = {
      title: { 
        text: '汇率走势', 
        left: 'center', 
        textStyle: { fontSize: 24, fontWeight: 'bold', color: '#333' } 
      },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: dates,
      },
      yAxis: {
        type: 'value',
        scale: true, // 自动适配范围
      },
      series: [
        {
          name: '汇率',
          type: 'line',
          data: rates,
          itemStyle: {
            normal: {
              color: function(params) {
                if (params.dataIndex < 20) {
                  return '#000'; // 黑色
                } else if (params.dataIndex >= 20 && params.dataIndex < 23) {
                  return '#008000'; // 绿色
                } else {
                  return '#FF0000'; // 红色
                }
              }
            }
          },
          lineStyle: {
            normal: {
              color: function(params) {
                if (params.dataIndex < 19) {
                  return '#000'; // 黑色
                } else if (params.dataIndex >= 19 && params.dataIndex < 22) {
                  return '#008000'; // 绿色
                } else {
                  return '#FF0000'; // 红色
                }
              }
            }
          },
          symbolSize: function(params) {
            // 设置第21、22、23、24、25的数据点更大
            if (params.dataIndex >= 20) {
              return 10; // 或者其他你认为合适的大小
            }
            return 5; // 默认大小
          }
        }
      ],
      markLine: {
        silent: true,
        data: [
          {
            xAxis: dates[19],
            lineStyle: { color: '#008000' }, // 在第20个点前添加一条绿线
          },
          {
            xAxis: dates[22],
            lineStyle: { color: '#FF0000' }, // 在第23个点前添加一条红线
          }
        ]
      }
    };

    this.chart.clear();
    this.chart.setOption(option);
  },
    async fetchExchangeRateData() {
      try {
        const response = await axios.get(api('/api/exchange_rate_prediction'), {
          params: { currencyA: this.currencyA, currencyB: this.currencyB },
        });

        console.log('Received data:', response.data);
        this.chartData = { ...response.data };

        await nextTick();
        this.renderChart();
      } catch (error) {
        console.error('获取汇率数据失败:', error);
      }
    },
    switchChart(type) {
      this.chartType = type;
      this.renderChart();
    },
    resizeChart() {
      if (this.chart) {
        this.chart.resize();
      }
    }
  },
};
</script>

<style scoped>
.exchange-rate-prediction {
  display: flex;
  padding: 40px;
  gap: 50px;
  background-color: #ddd;
  border-radius: 16px;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.15);
  max-width: 1590px;
  margin: 40px auto;
}

.left-content {
  flex: 1;
  padding: 30px;
  background-color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.right-content {
  flex: 4;
  display: flex;
  flex-direction: column;
  gap: 30px;
  padding: 30px;
  background-color: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.chart-container {
  height: 500px;
  background-color: #fff;
  border-radius: 12px;
  padding: 20px;
}

.chart-controls {
  display: flex;
  gap: 15px;
  justify-content: flex-end;
}

.chart-button.el-button--gray {
  background-color: #ccc;
  border-color: #999;
  color: #333;
}
</style>
