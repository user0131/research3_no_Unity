import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ManagerDebugData, SystemInfo } from '../types';
import './DebugPanel.css';

const DebugPanel: React.FC = () => {
  const [managerData, setManagerData] = useState<Record<string, ManagerDebugData>>({});
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedManager, setSelectedManager] = useState<string>('all');
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (isExpanded) {
      loadDebugData();
      const interval = setInterval(loadDebugData, 5000);
      return () => clearInterval(interval);
    }
  }, [isExpanded, selectedManager]);

  const loadDebugData = async () => {
    try {
      const [managerResponse, systemResponse] = await Promise.all([
        api.getManagerDebugData(selectedManager),
        api.getSystemDebugInfo(),
      ]);
      setManagerData(managerResponse.data);
      setSystemInfo(systemResponse.data);
    } catch (error) {
      console.error('デバッグデータ取得エラー:', error);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  return (
    <div className={`debug-panel ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <div className="debug-header" onClick={() => setIsExpanded(!isExpanded)}>
        <h3>開発者ツール</h3>
        <span className="toggle-icon">{isExpanded ? '▼' : '▲'}</span>
      </div>

      {isExpanded && (
        <div className="debug-content">
          <div className="debug-controls">
            <select
              value={selectedManager}
              onChange={(e) => setSelectedManager(e.target.value)}
              className="manager-selector"
            >
              <option value="all">全マネージャー</option>
              <option value="information">情報管理班</option>
              <option value="supply">物資管理班</option>
            </select>
            <button onClick={loadDebugData} className="refresh-button">
              更新
            </button>
          </div>

          {systemInfo && (
            <div className="system-info-section">
              <h4 onClick={() => toggleSection('system')}>
                システム情報 {expandedSections['system'] ? '▼' : '▶'}
              </h4>
              {expandedSections['system'] && (
                <div className="info-content">
                  <div className="info-item">
                    <span className="label">現在時刻:</span>
                    <span className="value">{systemInfo.time_manager.current_time}</span>
                  </div>
                  <div className="info-item">
                    <span className="label">速度倍率:</span>
                    <span className="value">×{systemInfo.time_manager.speed_multiplier}</span>
                  </div>
                  <div className="info-item">
                    <span className="label">スケジュールタスク数:</span>
                    <span className="value">{systemInfo.inf_provider.scheduled_tasks_count}</span>
                  </div>
                  <div className="info-item">
                    <span className="label">全体会話履歴数:</span>
                    <span className="value">{systemInfo.global_conversation_history_count}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {Object.entries(managerData).map(([key, manager]) => (
            <div key={key} className="manager-section">
              <h4 onClick={() => toggleSection(key)}>
                {manager.name} {expandedSections[key] ? '▼' : '▶'}
              </h4>
              {expandedSections[key] && (
                <div className="manager-details">
                  <div className="status-section">
                    <h5>ステータス</h5>
                    <div className="info-item">
                      <span className="label">利用可能:</span>
                      <span className={`value ${manager.status.available ? 'available' : 'unavailable'}`}>
                        {manager.status.available ? '○' : '×'}
                      </span>
                    </div>
                    <div className="info-item">
                      <span className="label">会話中:</span>
                      <span className="value">{manager.status.in_conversation ? 'はい' : 'いいえ'}</span>
                    </div>
                  </div>

                  <div className="csv-section">
                    <h5>保有CSVファイル</h5>
                    {Object.entries(manager.csv_files).map(([csvName, csvData]) => (
                      <div key={csvName} className="csv-item">
                        <div
                          className="csv-header"
                          onClick={() => toggleSection(`${key}-csv-${csvName}`)}
                        >
                          <span className="csv-name">{csvName}</span>
                          <span className="csv-shape">
                            ({csvData.shape[0]}行 × {csvData.shape[1]}列)
                          </span>
                        </div>
                        {expandedSections[`${key}-csv-${csvName}`] && (
                          <div className="csv-details">
                            <div className="columns-list">
                              <strong>カラム:</strong> {csvData.columns.join(', ')}
                            </div>
                            <div className="sample-data">
                              <strong>サンプルデータ:</strong>
                              <pre>{JSON.stringify(csvData.sample_data, null, 2)}</pre>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  <div className="memory-section">
                    <h5>メモリ情報</h5>
                    <div className="info-item">
                      <span className="label">会話履歴数:</span>
                      <span className="value">{manager.memory.conversation_history_count}</span>
                    </div>
                    {manager.memory.inventory && (
                      <div className="inventory-section">
                        <strong>在庫:</strong>
                        <pre>{JSON.stringify(manager.memory.inventory, null, 2)}</pre>
                      </div>
                    )}
                  </div>

                  {manager.workers && manager.workers.length > 0 && (
                    <div className="workers-section">
                      <h5>ワーカー</h5>
                      {manager.workers.map((worker, index) => (
                        <div key={index} className="info-item">
                          <span className="label">{worker.type}:</span>
                          <span className={`value ${worker.available ? 'available' : 'unavailable'}`}>
                            {worker.available ? '利用可能' : '使用中'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DebugPanel;