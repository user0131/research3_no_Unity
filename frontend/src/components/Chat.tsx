import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import { Message } from '../types';
import './Chat.css';

interface ChatProps {
  selectedManager: 'information' | 'supply';
}

const Chat: React.FC<ChatProps> = ({ selectedManager }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState('');
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

    return () => clearInterval(timeInterval);
  }, [selectedManager]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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
      const response = await api.getHistory(selectedManager);
      setMessages(response.data.history || []);
    } catch (error) {
      console.error('履歴取得エラー:', error);
    }
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const messageToSend = `/${selectedManager}_manager/${inputMessage}`;
    setIsLoading(true);

    try {
      const response = await api.sendMessage(messageToSend);
      setCurrentTime(response.data.current_time);
      await loadHistory();
    } catch (error) {
      console.error('メッセージ送信エラー:', error);
    } finally {
      setIsLoading(false);
      setInputMessage('');
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
      'SUPPLY_MANAGER': '物資Manager',
      'INFORMATION_MANAGER': '情報Manager',
      'ワーカーA': 'Worker A',
      'ワーカーB': 'Worker B',
      'ワーカーC': 'Worker C',
      'System': 'System',
      'SYSTEM': 'System'
    };
    return nameMap[personName] || personName;
  };

  const getMessageDirectionLabel = (message: Message, direction: string) => {
    if (direction === 'sent') {
      // Playerの発言：「→ 相手」
      const toName = message.to || (selectedManager === 'information' ? '情報Manager' : '物資Manager');
      return `→ ${getPersonDisplayName(toName)}`;
    } else {
      // それ以外：「from → to」
      const fromName = getPersonDisplayName(message.from || message.name || 'System');
      const toName = message.to ? getPersonDisplayName(message.to) : 'Player';
      return `${fromName} → ${toName}`;
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>
          {selectedManager === 'information' ? '情報管理班' : '物資管理班'}
        </h2>
        <span className="current-time">現在時刻: {currentTime}</span>
      </div>

      <div className="messages-container">
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
          placeholder="メッセージを入力..."
          disabled={isLoading}
          className="message-input"
        />
        <button
          onClick={sendMessage}
          disabled={isLoading || !inputMessage.trim()}
          className="send-button"
        >
          送信
        </button>
      </div>
    </div>
  );
};

export default Chat;