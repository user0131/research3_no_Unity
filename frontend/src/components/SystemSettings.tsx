import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import './SystemSettings.css';

interface SystemSettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

const SystemSettings: React.FC<SystemSettingsProps> = ({ isOpen, onClose }) => {
  const [timeSpeed, setTimeSpeed] = useState<number>(1.0);
  const [currentTime, setCurrentTime] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadSystemInfo();
    }
  }, [isOpen]);

  const loadSystemInfo = async () => {
    try {
      const [timeResponse, systemResponse] = await Promise.all([
        api.getCurrentTime(),
        api.getSystemDebugInfo(),
      ]);
      setCurrentTime(timeResponse.data.current_time);
      setTimeSpeed(systemResponse.data.time_manager.speed_multiplier || 1.0);
    } catch (error) {
      console.error('システム情報取得エラー:', error);
    }
  };

  const handleSpeedChange = async (newSpeed: number) => {
    setIsLoading(true);
    try {
      const response = await api.setTimeSpeed(newSpeed);
      setTimeSpeed(response.data.speed_multiplier);
      setCurrentTime(response.data.current_time);
    } catch (error) {
      console.error('速度変更エラー:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSystemReset = async () => {
    if (!window.confirm('これまでの会話やデータを初期化しますか？')) {
      return;
    }

    setIsResetting(true);
    try {
      const response = await api.resetSystem();
      alert('システムが初期化されました');
      setCurrentTime(response.data.current_time);
      setTimeSpeed(1.0);
    } catch (error) {
      console.error('システム初期化エラー:', error);
      alert('システム初期化に失敗しました');
    } finally {
      setIsResetting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <div className="settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h2>システム設定</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <div className="settings-content">
          <div className="setting-item">
            <label>現在時刻</label>
            <div className="current-time-display">{currentTime}</div>
          </div>

          <div className="setting-item">
            <label>時間進行速度</label>
            <div className="speed-control">
              <input
                type="range"
                min="0.1"
                max="10"
                step="0.1"
                value={timeSpeed}
                onChange={(e) => setTimeSpeed(parseFloat(e.target.value))}
                onMouseUp={() => handleSpeedChange(timeSpeed)}
                disabled={isLoading}
                className="speed-slider"
              />
              <span className="speed-value">×{timeSpeed.toFixed(1)}</span>
            </div>
            <div className="speed-presets">
              <button
                onClick={() => handleSpeedChange(0.5)}
                disabled={isLoading}
                className="preset-button"
              >
                ×0.5
              </button>
              <button
                onClick={() => handleSpeedChange(1.0)}
                disabled={isLoading}
                className="preset-button"
              >
                ×1.0
              </button>
              <button
                onClick={() => handleSpeedChange(2.0)}
                disabled={isLoading}
                className="preset-button"
              >
                ×2.0
              </button>
              <button
                onClick={() => handleSpeedChange(5.0)}
                disabled={isLoading}
                className="preset-button"
              >
                ×5.0
              </button>
            </div>
          </div>

          <div className="setting-item">
            <label>システム操作</label>
            <button
              onClick={handleSystemReset}
              disabled={isResetting}
              className="reset-button"
            >
              {isResetting ? '初期化中...' : 'システム初期化'}
            </button>
            <div className="reset-description">
              会話履歴、記憶、CSVデータをすべて初期状態に戻します
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SystemSettings;