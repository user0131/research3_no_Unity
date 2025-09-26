import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ManagerDebugData, Message } from '../types'; // 型設定
import './ManagerInfo.css';

interface ManagerInfoProps {
  managerType: 'information' | 'supply';
}

const ManagerInfo: React.FC<ManagerInfoProps> = ({ managerType }) => {
  const [managerData, setManagerData] = useState<ManagerDebugData | null>(null); // ManageDebucDataとは
  const [conversationHistory, setConversationHistory] = useState<Message[]>([]);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(() => {
    const saved = localStorage.getItem(`expandedSections_${managerType}`);
    const defaultState = {
      status: true,
      csv: true,
      knowledge: true,
      conversation: true,
      workers: true,
    };
    return saved ? { ...defaultState, ...JSON.parse(saved) } : defaultState;
  });

  useEffect(() => {
    loadManagerData();
    loadConversationHistory();
    const interval = setInterval(() => {
      loadManagerData();
      loadConversationHistory();
    }, 5000);
    return () => clearInterval(interval);
  }, [managerType]);

  useEffect(() => {
    localStorage.setItem(`expandedSections_${managerType}`, JSON.stringify(expandedSections));
  }, [expandedSections, managerType]);

  const loadManagerData = async () => {
    try {
      const response = await api.getManagerDebugData(managerType);
      const data = response.data[`${managerType}_manager`];
      if (data) {
        setManagerData(data);
      }
    } catch (error) {
      console.error('マネージャーデータ取得エラー:', error);
    }
  };

  const loadConversationHistory = async () => {
    try {
      const response = await api.getHistory(managerType);
      setConversationHistory(response.data.history || []);
    } catch (error) {
      console.error('会話履歴取得エラー:', error);
    }
  };

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  const toggleCsvDetail = (csvName: string) => {
    const key = `csv-${csvName}`;
    setExpandedSections(prev => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  if (!managerData) {
    return <div className="manager-info-loading">読み込み中...</div>; // 
  }

  return (
    <div className="manager-info-container">
      <div className="manager-info-section">
        <h3 onClick={() => toggleSection('status')} className="section-header">
          ステータス {expandedSections.status ? '▼' : '▶'}
        </h3>
        {expandedSections.status && (
          <div className="section-content">
            <div className="info-row">
              <span className="info-label">利用可能:</span>
              <span className={`info-value ${managerData.status.available ? 'available' : 'unavailable'}`}>
                {managerData.status.available ? '○' : '×'}
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">会話中:</span>
              <span className="info-value">
                {managerData.status.in_conversation ? 'はい' : 'いいえ'}
              </span>
            </div>
            {managerData.status.away_reason && (
              <div className="info-row">
                <span className="info-label">離席理由:</span>
                <span className="info-value">{managerData.status.away_reason}</span>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="manager-info-section">
        <h3 onClick={() => toggleSection('csv')} className="section-header">
          保有CSVファイル {expandedSections.csv ? '▼' : '▶'}
        </h3>
        {expandedSections.csv && (
          <div className="section-content">
            {Object.entries(managerData.csv_files).length > 0 ? (
              Object.entries(managerData.csv_files).map(([csvName, csvData]) => (
                <div key={csvName} className="csv-item">
                  <div
                    className="csv-header"
                    onClick={() => toggleCsvDetail(csvName)}
                  >
                    <span className="csv-name">{csvName}</span>
                    <span className="csv-shape">
                      {csvData.shape[0]}行 × {csvData.shape[1]}列
                    </span>
                  </div>
                  {expandedSections[`csv-${csvName}`] && (
                    <div className="csv-details">
                      <div className="csv-columns">
                        <strong>カラム:</strong>
                        <div className="columns-list">
                          {csvData.columns.join(', ')}
                        </div>
                      </div>
                      <div className="csv-sample">
                        <strong>データ内容:</strong>
                        <div className="sample-data">
                          <pre>{JSON.stringify(csvData.sample_data, null, 2)}</pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="no-data">CSVファイルなし</div>
            )}
          </div>
        )}
      </div>

      <div className="manager-info-section">
        <h3 onClick={() => toggleSection('knowledge')} className="section-header">
          知っている知識 {expandedSections.knowledge ? '▼' : '▶'}
        </h3>
        {expandedSections.knowledge && (
          <div className="section-content">
            {Object.entries(managerData.knowledge_files || {}).length > 0 ? (
              Object.entries(managerData.knowledge_files).map(([filename, content]) => (
                <div key={filename} className="knowledge-item">
                  <div className="knowledge-header">
                    <span className="knowledge-filename">{filename}</span>
                  </div>
                  <div className="knowledge-content">
                    <pre>{content}</pre>
                  </div>
                </div>
              ))
            ) : (
              <div className="no-data">知識ファイルなし</div>
            )}
          </div>
        )}
      </div>

      <div className="manager-info-section">
        <h3 onClick={() => toggleSection('conversation')} className="section-header">
          会話履歴（付与情報含む） {expandedSections.conversation ? '▼' : '▶'}
        </h3>
        {expandedSections.conversation && (
          <div className="section-content conversation-history">
            {conversationHistory.length > 0 ? (
              <div className="conversation-list">
                {conversationHistory.map((message, index) => (
                  <div key={index} className={`conversation-message ${message.role}`}>
                    <div className="message-header">
                      <span className="message-role">{message.name || message.role}</span>
                    </div>
                    <div className="message-content">{message.content}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-data">会話履歴なし</div>
            )}
          </div>
        )}
      </div>

      {managerType === 'supply' && managerData.memory?.inventory && (
        <div className="manager-info-section">
          <h3 onClick={() => toggleSection('inventory')} className="section-header">
            在庫情報 {expandedSections.inventory ? '▼' : '▶'}
          </h3>
          {expandedSections.inventory && (
            <div className="section-content">
              <div className="inventory-info">
                <pre>{JSON.stringify(managerData.memory.inventory, null, 2)}</pre>
              </div>
            </div>
          )}
        </div>
      )}

      {managerData.workers && managerData.workers.length > 0 && (
        <div className="manager-info-section">
          <h3 onClick={() => toggleSection('workers')} className="section-header">
            ワーカー情報 {expandedSections.workers ? '▼' : '▶'}
          </h3>
          {expandedSections.workers && (
            <div className="section-content">
              {managerData.workers.map((worker, index) => (
                <div key={index} className="info-row">
                  <span className="info-label">{worker.type}:</span>
                  <span className={`info-value ${worker.available ? 'available' : 'unavailable'}`}>
                    {worker.available ? '利用可能' : '使用中'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ManagerInfo;