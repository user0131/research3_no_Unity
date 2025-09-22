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
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
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
        {messages.map((message, index) => (
          <div
            key={index}
            className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
          >
            <div className="message-header">
              <span className="message-role">{message.name || message.role}</span>
            </div>
            <div className="message-content">{message.content}</div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-container">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
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