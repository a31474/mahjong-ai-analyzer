<template>
  <el-config-provider :locale="elementLocale">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { computed } from 'vue'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import { locale } from '@/i18n'

const localePacks = { 'zh-CN': zhCn }
const elementLocale = computed(() => localePacks[locale.value] || zhCn)
</script>

<style>
:root {
  --omu-surface: #ffffff;
  --omu-surface-soft: rgba(255, 255, 255, 0.96);
  --omu-border: #ebeef5;
  --omu-border-strong: #dcdfe6;
  --omu-text: #303133;
  --omu-text-soft: #606266;
  --omu-text-muted: #909399;
  --omu-accent: #409eff;
  --omu-accent-strong: #337ecc;
  --omu-accent-soft: #ecf5ff;
  --omu-accent-ghost: rgba(64, 158, 255, 0.12);
  --omu-success: #67c23a;
  --omu-warning: #e6a23c;
  --omu-danger: #f56c6c;
  --omu-mono: Consolas, Monaco, monospace;
  --omu-shadow-sm: 0 4px 20px rgba(0, 0, 0, 0.1);
  --omu-shadow-md: 0 8px 24px rgba(0, 0, 0, 0.12);
  --omu-radius: 15px;
  --omu-radius-sm: 8px;
}
html,
body {
  margin: 0;
  padding: 0;
  min-height: 100vh;
}
#app {
  min-height: 100vh;
}
</style>
