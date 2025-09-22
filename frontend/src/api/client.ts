import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const api = {
  // チャット関連
  startChat: () => apiClient.post('/chat/start'),
  sendMessage: (message: string) => apiClient.post('/chat/send', { message }),
  getHistory: (managerType: string = 'all') =>
    apiClient.get('/chat/history', { params: { manager_type: managerType } }),

  // 時間管理
  getCurrentTime: () => apiClient.get('/time/current'),
  setTimeSpeed: (speed: number) => apiClient.post('/time/speed', { speed }),

  // マネージャーステータス
  getManagersStatus: () => apiClient.get('/managers/status'),

  // デバッグ情報
  getManagerDebugData: (managerType: string = 'all') =>
    apiClient.get('/debug/manager-data', { params: { manager_type: managerType } }),
  getSystemDebugInfo: () => apiClient.get('/debug/system-info'),

  // ヘルスチェック
  healthCheck: () => apiClient.get('/health'),

  // システム操作
  resetSystem: () => apiClient.post('/system/reset'),
};

export default apiClient;