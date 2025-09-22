import React, { useState, useEffect } from 'react';
import Chat from './components/Chat';
import ManagerInfo from './components/ManagerInfo';
import SystemSettings from './components/SystemSettings';
import './App.css';

function App() {
  const [selectedManager, setSelectedManager] = useState<'information' | 'supply'>(() => {
    const saved = localStorage.getItem('selectedManager');
    return (saved === 'supply' || saved === 'information') ? saved : 'information';
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem('selectedManager', selectedManager);
  }, [selectedManager]);

  return (
    <div className="App">
      <header className="app-header">
        <div className="header-left">
          <h1>災害対応システム</h1>
          <div className="manager-tabs">
            <button
              className={`tab ${selectedManager === 'information' ? 'active' : ''}`}
              onClick={() => setSelectedManager('information')}
            >
              情報管理班
            </button>
            <button
              className={`tab ${selectedManager === 'supply' ? 'active' : ''}`}
              onClick={() => setSelectedManager('supply')}
            >
              物資管理班
            </button>
          </div>
        </div>
        <div className="header-right">
          <button className="settings-button" onClick={() => setIsSettingsOpen(true)}>
            ⚙️ 設定
          </button>
        </div>
      </header>

      <main className="app-main">
        <div className="main-content">
          <Chat selectedManager={selectedManager} />
        </div>
        <div className="sidebar">
          <ManagerInfo managerType={selectedManager} />
        </div>
      </main>

      <SystemSettings isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
}

export default App;
