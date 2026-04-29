<template>
  <div class="container">
    <div class="historical-exchange-rate">
      <div class="header">
        <h1>历史汇率数据</h1>
      </div>
      <div class="select-container">
        <p>选择货币A</p>
        <el-select v-model="currencyA" placeholder="请选择货币A" class="currency-select">
          <el-option v-for="item in currencyOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
        </el-select>
      </div>
      <div class="select-container">
        <p>选择货币B</p>
        <el-select v-model="currencyB" placeholder="请选择货币B" class="currency-select">
          <el-option v-for="item in currencyOptions" :key="item.value" :label="item.label" :value="item.value"></el-option>
        </el-select>
      </div>
      <div class="date-picker-container">
        <p>选择日期范围</p>
        <el-date-picker v-model="dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期"></el-date-picker>
      </div>
    </div>
    <div class="record-display">
      <div class="toggle-buttons">
        <el-button :type="activeTab === 'table' ? 'primary' : 'default'" @click="activeTab = 'table'" class="custom-history-button">
          历史记录
        </el-button>
        <el-button :type="activeTab === 'chart' ? 'primary' : 'default'" @click="switchToChart" class="charts-button">
          折线图
        </el-button>
      </div>
      <div v-show="activeTab === 'table'" v-if="showContent">
        <el-table :data="pagedTableData" style="width: 100%">
          <el-table-column prop="date" label="日期" width="240" align="center"></el-table-column>
          <el-table-column prop="currencyA" label="货币A" width="200" align="center"></el-table-column>
          <el-table-column prop="currencyB" label="货币B" width="200" align="center"></el-table-column>
          <el-table-column prop="exchangeRate" label="汇率" width="600" align="center"></el-table-column>
        </el-table>
        <el-pagination background layout="prev, pager, next" :total="totalRecords" :page-size="pageSize" :current-page="currentPage" @current-change="handlePageChange"></el-pagination>
      </div>
      <div v-show="activeTab === 'chart'" v-if="showContent" class="chart-container">
        <el-empty description="暂无数据" v-if="!tableData.length" />
        <div v-else ref="chart" style="width: 100%; height: 400px;"></div>
      </div>
    </div>
  </div>
</template>

<script>
import axios from 'axios';
import * as echarts from 'echarts';
import { api } from '@/config';

export default {
  data() {
    return {
      tableData: [],
      showContent: false,
      currencyOptions: [
        {'value': 'USD', 'label': '美元 (USD)'},
        {'value': 'GBP', 'label': '英镑 (GBP)'},
        {'value': 'EUR', 'label': '欧元 (EUR)'},
        {'value': 'JPY', 'label': '日元 (JPY)'},
        {'value': 'HKD', 'label': '港币 (HKD)'},
        {'value': 'AUD', 'label': '澳元 (AUD)'},
      ],
      currencyA: '',
      currencyB: '',
      dateRange: [],
      totalRecords: 0,
      pageSize: 10,
      currentPage: 1,
      activeTab: 'table',
      chartInstance: null,
    };
  },
  computed: {
    pagedTableData() {
      const start = (this.currentPage - 1) * this.pageSize;
      const end = start + this.pageSize;
      return this.tableData.slice(start, end);
    },
    chartData() {
      return {
        dates: this.tableData.map(item => item.date),
        exchangeRates: this.tableData.map(item => parseFloat(item.exchangeRate)),
      };
    },
  },
  watch: {
    currencyA() { this.fetchTableData(); },
    currencyB() { this.fetchTableData(); },
    dateRange() { this.fetchTableData(); },
    tableData() {
      this.showContent = true;
      if (this.activeTab === 'chart') {
        this.$nextTick(() => {
          this.renderChart();
        });
      }
    },
  },
  methods: {
    async fetchTableData() {
      if (!this.currencyA || !this.currencyB || this.dateRange.length !== 2) {
        return;
      }
      try {
        const response = await axios.get(api('/api/exchange_rates'), {
          params: {
            currencyA: this.currencyA,
            currencyB: this.currencyB,
            start_date: this.dateRange[0].toISOString().split('T')[0],
            end_date: this.dateRange[1].toISOString().split('T')[0],
          },
        });
        this.tableData = response.data;
        this.totalRecords = this.tableData.length;
      } catch (error) {
        console.error('获取数据失败:', error);
      }
    },
    renderChart() {
      if (!this.$refs.chart) return;
      if (!this.chartInstance) {
        this.chartInstance = echarts.init(this.$refs.chart);
      }
      const option = {
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: this.chartData.dates, name: '日期' },
        yAxis: { type: 'value', name: '汇率', scale: true },
        series: [{ name: '汇率', type: 'line', data: this.chartData.exchangeRates, smooth: true }],
      };
      this.chartInstance.setOption(option);
    },
    switchToChart() {
      this.activeTab = 'chart';
      this.$nextTick(() => {
        this.renderChart();
      });
    },
    handlePageChange(currentPage) {
      this.currentPage = currentPage;
    },
  },
  beforeDestroy() {
    if (this.chartInstance) {
      this.chartInstance.dispose();
    }
  },
};
</script>

<style scoped>
.container {
  display: flex;
  gap: 30px;
  padding: 30px;
  max-width: 1590px;
  margin: 0 auto;
  background-color: #ddd;
  border-radius: 10px;
  min-height: 90vh;
}
.record-display {
  flex: 2;
  background-color: #fff;
  border-radius: 8px;
}
.toggle-buttons {
  display: flex;
  gap: 10px;
}
.chart-container {
  width: 100%;
  height: 400px;
}
.custom-history-button.el-button--primary{
  background-color: rgb(139, 0, 0);
  border-color: rgb(139, 0, 0);
}
.charts-button.el-button--primary{
  background-color: rgb(139, 0, 0);
  border-color: rgb(139, 0, 0);
}
</style>