import React, { useState, useEffect, useRef, useMemo } from 'react';
import { api } from '../api/client';
import { Message } from '../types';
import './Chat.css';

interface ChatProps {
  selectedManager: 'information' | 'supply' | 'infrastructure' | 'mayor';
  selectedChatPerson?: string;
  setSelectedChatPerson?: (person: string) => void;
}

const Chat: React.FC<ChatProps> = ({ selectedManager, selectedChatPerson: externalSelectedPerson, setSelectedChatPerson: externalSetSelectedPerson }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState('');
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const [managerStatus, setManagerStatus] = useState<any>(null);
  const [internalSelectedPerson, setInternalSelectedPerson] = useState<string>(() => {
    if (selectedManager === 'information') {
      return localStorage.getItem(`selectedChatPerson_${selectedManager}`) || 'information_manager';
    }
    return selectedManager === 'supply' ? 'supply_manager' : 'infrastructure_manager';
  });

  // 外部から渡される場合はそれを使用、そうでなければ内部状態を使用
  const selectedPerson = useMemo(() =>
    externalSelectedPerson || internalSelectedPerson,
    [externalSelectedPerson, internalSelectedPerson]
  );
  const setSelectedPerson = externalSetSelectedPerson || setInternalSelectedPerson;
  const messagesEndRef = useRef<null | HTMLDivElement>(null);

  useEffect(() => {
    loadHistory();
    startChat();

    // 時刻を定期的に更新（10秒ごと）
    const timeInterval = setInterval(async () => {
      try {
        const response = await api.getCurrentTime();
        setCurrentTime(response.data.current_time);
      } catch (error) {
        console.error('時刻更新エラー:', error);
      }
    }, 10000);

    // 会話履歴を定期的に更新（1秒ごと）
    const historyInterval = setInterval(() => {
      loadHistory();
    }, 1000);

    // マネージャーステータスを定期的に更新（3秒ごと）
    const statusInterval = setInterval(async () => {
      try {
        const response = await api.getManagersStatus();
        setManagerStatus(response.data);
      } catch (error) {
        console.error('マネージャーステータス更新エラー:', error);
      }
    }, 3000);

    return () => {
      clearInterval(timeInterval);
      clearInterval(historyInterval);
      clearInterval(statusInterval);
    };
  }, [selectedManager, selectedPerson]);

  useEffect(() => {
    if (selectedManager === 'information' && !externalSelectedPerson) {
      localStorage.setItem(`selectedChatPerson_${selectedManager}`, selectedPerson);
    }
  }, [selectedManager, selectedPerson, externalSelectedPerson]);

  useEffect(() => {
    if (shouldAutoScroll) {
      scrollToBottom();
    }
  }, [messages, shouldAutoScroll]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const startChat = async () => {
    try {
      const response = await api.startChat();
      setCurrentTime(response.data.current_time);
    } catch (error) {
      console.error('チャット開始エラー:', error);
    }
  };

  const loadHistory = async () => {
    try {
      if (selectedManager === 'information' && selectedPerson) {
        // 危機管理室で特定の人物（情報Managerまたは市長）を選択した場合
        if (selectedPerson === 'mayor') {
          const response = await api.getHistory('mayor');
          setMessages(response.data.history || []);
        } else {
          const response = await api.getHistory(selectedManager, selectedPerson);
          setMessages(response.data.history || []);
        }
      } else {
        const response = await api.getHistory(selectedManager);
        setMessages(response.data.history || []);
      }
    } catch (error) {
      console.error('履歴取得エラー:', error);
    }
  };

  // マネージャーが利用可能かチェック
  const isManagerAvailable = () => {
    if (!managerStatus) return true; // まだ状態が取得できていない場合は送信可能とする

    if (selectedManager === 'information') {
      if (selectedPerson === 'mayor') {
        // 市長の場合はmanagerStatus内に情報がないため、一旦送信可能とする
        return true;
      } else {
        return managerStatus.information_manager?.available || false;
      }
    } else if (selectedManager === 'supply') {
      return managerStatus.supply_manager?.available || false;
    } else if (selectedManager === 'infrastructure') {
      return managerStatus.infrastructure_manager?.available || false;
    }

    return true;
  };

  // マネージャーが利用不可の場合のメッセージを取得
  const getUnavailableMessage = () => {
    if (!managerStatus) return '';

    if (selectedManager === 'information') {
      return managerStatus.information_manager?.away_message || 'ただいま作業中で会話できません';
    } else if (selectedManager === 'supply') {
      return managerStatus.supply_manager?.away_message || 'ただいま作業中で会話できません';
    } else if (selectedManager === 'infrastructure') {
      return managerStatus.infrastructure_manager?.away_message || 'ただいま作業中で会話できません';
    }

    return 'ただいま作業中で会話できません';
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    // マネージャーの利用可能性をチェック
    if (!isManagerAvailable()) {
      alert(getUnavailableMessage());
      return;
    }

    let messageToSend: string;
    if (selectedManager === 'information' && selectedPerson === 'mayor') {
      messageToSend = `/mayor/${inputMessage}`;
    } else {
      messageToSend = `/${selectedManager}_manager/${inputMessage}`;
    }

    const currentMessage = inputMessage;
    setInputMessage(''); // 送信後すぐに入力欄をクリア
    setShouldAutoScroll(true);

    try {
      setIsLoading(true);
      const response = await api.sendMessage(messageToSend);
      setCurrentTime(response.data.current_time);
      await loadHistory();
    } catch (error) {
      console.error('メッセージ送信エラー:', error);
      // エラーの場合は入力内容を復元
      setInputMessage(currentMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    // IME変換中（日本語入力中）は送信しない
    if (e.key === 'Enter' && !e.shiftKey && !(e.nativeEvent as any).isComposing) {
      e.preventDefault();
      sendMessage();
    }
  };

  const getMessageDirection = (message: Message) => {
    // Playerの発言のみ右側、それ以外（管理班、ワーカー等）は左側に表示
    if (message.name && message.name.toLowerCase() === 'player') {
      return 'sent';
    } else {
      return 'received';
    }
  };

  const getPersonDisplayName = (personName: string) => {
    const nameMap: { [key: string]: string } = {
      'Player': 'Player',
      'supply_manager': '物資Manager',
      'information_manager': '情報Manager',
      'infrastructure_manager': '土木Manager',
      'mayor': '市長',
      'SUPPLY_MANAGER': '物資Manager',
      'INFORMATION_MANAGER': '情報Manager',
      'INFRASTRUCTURE_MANAGER': '土木Manager',
      'MAYOR': '市長',
      'ワーカーA': 'Worker A',
      'ワーカーB': 'Worker B',
      'ワーカーC': 'Worker C',
      '土木ワーカーA': '土木Worker A',
      '土木ワーカーB': '土木Worker B',
      '土木ワーカーC': '土木Worker C',
      'System': 'System',
      'SYSTEM': 'System'
    };
    return nameMap[personName] || personName;
  };

  const getMessageDirectionLabel = (message: Message, direction: string) => {
    if (direction === 'sent') {
      // Playerの発言：「→ 相手」
      const toName = message.to || (selectedManager === 'information' ? '情報Manager'
                                   : selectedManager === 'supply' ? '物資Manager'
                                   : selectedManager === 'mayor' ? '市長'
                                   : '土木Manager');
      return `→ ${getPersonDisplayName(toName)}`;
    } else {
      // それ以外：「from → to」
      const fromName = getPersonDisplayName(message.from || message.name || 'System');
      const toName = message.to ? getPersonDisplayName(message.to) : 'Player';
      return `${fromName} → ${toName}`;
    }
  };

  const getPersonsForChat = () => {
    if (selectedManager === 'information') {
      return [
        { id: 'information_manager', name: '情報Manager' },
        { id: 'mayor', name: '市長' }
      ];
    }
    return [];
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="chat-header-left">
          <h2>
            {selectedManager === 'information' ? '危機管理室'
             : selectedManager === 'supply' ? '物資管理班'
             : selectedManager === 'mayor' ? '市長との会話'
             : '建物・土木対策班'}
          </h2>
          {selectedManager === 'information' && (
            <div className="person-tabs">
              {getPersonsForChat().map((person) => (
                <button
                  key={person.id}
                  className={`person-tab ${selectedPerson === person.id ? 'active' : ''}`}
                  onClick={() => setSelectedPerson(person.id)}
                >
                  {person.name}
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="current-time">現在時刻: {currentTime}</span>
      </div>

      <div
        className="messages-container"
        onScroll={(e) => {
          const target = e.currentTarget;
          const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 100;
          setShouldAutoScroll(isAtBottom);
        }}
      >
        {messages.map((message, index) => {
          const direction = getMessageDirection(message);
          return (
            <div
              key={index}
              className={`message ${direction === 'sent' ? 'user-message' : 'assistant-message'}`}
            >
              <div className="message-header">
                <span className="message-direction">
                  {getMessageDirectionLabel(message, direction)}
                </span>
                <div className="message-meta">
                  {message.timestamp && (
                    <span className="message-time">{message.timestamp}</span>
                  )}
                  <span className="message-role">
                    {message.role === 'user' ? '👤' : message.role === 'assistant' ? '🤖' : '📋'}
                  </span>
                </div>
              </div>
              <div className="message-content">{message.content}</div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyDown={handleKeyPress}
          placeholder={!isManagerAvailable() ? getUnavailableMessage() : "メッセージを入力..."}
          disabled={!isManagerAvailable()}
          className="message-input"
        />
        <button
          onClick={sendMessage}
          disabled={isLoading || !inputMessage.trim() || !isManagerAvailable()}
          className="send-button"
          title={!isManagerAvailable() ? getUnavailableMessage() : ''}
        >
          {!isManagerAvailable() ? '作業中' : '送信'}
        </button>
      </div>
    </div>
  );
};

export default Chat;