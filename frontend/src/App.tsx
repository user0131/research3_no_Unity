import React, { useState, useEffect } from 'react';
import Chat from './components/Chat';
import ManagerInfo from './components/ManagerInfo';
import SystemSettings from './components/SystemSettings';
import PersonChat from './components/PersonChat';
import PersonInfo from './components/PersonInfo';
import './App.css';

type ViewMode = 'chat' | 'person';

function App() {
  const [selectedManager, setSelectedManager] = useState<'information' | 'supply'>(() => {
    const saved = localStorage.getItem('selectedManager');
    return (saved === 'supply' || saved === 'information') ? saved : 'information';
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    const saved = localStorage.getItem('viewMode');
    return (saved === 'chat' || saved === 'person') ? saved : 'chat';
  });
  const [selectedPerson, setSelectedPerson] = useState<string>(() => {
    const saved = localStorage.getItem('selectedPerson');
    if (saved) {
      // 保存された人物が現在のmanagerで有効かチェック
      const validPersons = selectedManager === 'supply'
        ? ['supply_manager', 'ワーカーA', 'ワーカーB', 'ワーカーC']
        : ['Player', 'information_manager'];
      if (validPersons.includes(saved)) {
        return saved;
      }
    }
    // デフォルト値
    return selectedManager === 'supply' ? 'supply_manager' : 'Player';
  });

  useEffect(() => {
    localStorage.setItem('selectedManager', selectedManager);
    // manager切り替え時に現在のpersonが有効かチェック
    const validPersons = getPersonsForManager(selectedManager);
    if (!validPersons.includes(selectedPerson)) {
      // 現在の人物が無効な場合のみデフォルト値を設定
      const defaultPerson = selectedManager === 'supply' ? 'supply_manager' : 'Player';
      setSelectedPerson(defaultPerson);
    }
  }, [selectedManager, selectedPerson]);

  useEffect(() => {
    localStorage.setItem('viewMode', viewMode);
  }, [viewMode]);

  useEffect(() => {
    localStorage.setItem('selectedPerson', selectedPerson);
  }, [selectedPerson]);

  const getPersonsForManager = (managerType: 'information' | 'supply') => {
    if (managerType === 'supply') {
      return ['supply_manager', 'ワーカーA', 'ワーカーB', 'ワーカーC'];
    } else {
      return ['Player', 'information_manager'];
    }
  };

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
          {viewMode === 'person' && (
            <div className="person-tabs">
              {getPersonsForManager(selectedManager).map((person) => (
                <button
                  key={person}
                  className={`person-tab ${selectedPerson === person ? 'active' : ''}`}
                  onClick={() => setSelectedPerson(person)}
                >
                  {person === 'supply_manager' ? '物資Manager' :
                   person === 'information_manager' ? '情報Manager' : person}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="header-right">
          <div className="view-buttons">
            <button
              className={`view-button ${viewMode === 'chat' ? 'active' : ''}`}
              onClick={() => setViewMode('chat')}
            >
              💬 チャット
            </button>
            <button
              className={`view-button ${viewMode === 'person' ? 'active' : ''}`}
              onClick={() => setViewMode('person')}
            >
              👤 人物別ログ
            </button>
          </div>
          <button className="settings-button" onClick={() => setIsSettingsOpen(true)}>
            ⚙️ 設定
          </button>
        </div>
      </header>

      <main className="app-main">
        {viewMode === 'person' ? (
          <>
            <div className="main-content">
              <PersonChat person={selectedPerson} />
            </div>
            <div className="sidebar">
              <PersonInfo person={selectedPerson} />
            </div>
          </>
        ) : (
          <>
            <div className="main-content">
              <Chat selectedManager={selectedManager} />
            </div>
            <div className="sidebar">
              <ManagerInfo managerType={selectedManager} />
            </div>
          </>
        )}
      </main>

      <SystemSettings isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
}

export default App;
