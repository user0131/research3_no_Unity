import React, { useState, useEffect } from 'react';
import './PersonChat.css';

interface Message {
  role: string;
  name: string;
  content: string;
  from: string;
  to: string;
  timestamp?: string;
}

interface PersonChatProps {
  person: string;
}

const PersonChat: React.FC<PersonChatProps> = ({ person }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedMessages, setExpandedMessages] = useState<Record<number, boolean>>({});

  useEffect(() => {
    fetchPersonHistory();
    const interval = setInterval(fetchPersonHistory, 5000);
    return () => clearInterval(interval);
  }, [person]);

  const fetchPersonHistory = async () => {
    try {
      setIsLoading(true);
      const response = await fetch(`http://localhost:5000/api/chat/history?person=${person}`);
      const data = await response.json();
      setMessages(data.history || []);
    } catch (error) {
      console.error('Failed to fetch person history:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const getPersonDisplayName = (personName: string) => {
    const nameMap: { [key: string]: string } = {
      'Player': 'Player',
      'supply_manager': '物資Manager',
      'information_manager': '情報Manager',
      'ワーカーA': 'Worker A',
      'ワーカーB': 'Worker B',
      'ワーカーC': 'Worker C',
      'System': 'System'
    };
    return nameMap[personName] || personName;
  };

  const getMessageDirection = (msg: Message) => {
    if (msg.from === person) {
      return 'sent';
    } else if (msg.to === person) {
      return 'received';
    } else {
      return 'system';
    }
  };

  const toggleMessage = (index: number) => {
    setExpandedMessages(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  return (
    <div className="person-chat">
      <div className="person-chat-header">
        <h3>{getPersonDisplayName(person)}の会話履歴</h3>
        <p>送受信した全てのメッセージを表示</p>
      </div>

      <div className="person-messages">
        {isLoading && messages.length === 0 ? (
          <div className="loading">読み込み中...</div>
        ) : messages.length === 0 ? (
          <div className="no-messages">まだメッセージがありません</div>
        ) : (
          messages.map((msg, index) => {
            const direction = getMessageDirection(msg);
            const isExpanded = expandedMessages[index];
            const isSent = direction === 'sent';

            return (
              <div key={index} className={`message-item ${direction}`}>
                <div
                  className="message-header"
                  onClick={() => isSent && toggleMessage(index)}
                  style={{ cursor: isSent ? 'pointer' : 'default' }}
                >
                  <span className="message-direction">
                    {direction === 'sent' ? (
                      <>
                        {isExpanded ? '▼' : '▶'} → {getPersonDisplayName(msg.to)}
                      </>
                    ) : direction === 'received' ? (
                      `← ${getPersonDisplayName(msg.from)}`
                    ) : (
                      `${getPersonDisplayName(msg.from)} → ${getPersonDisplayName(msg.to)}`
                    )}
                  </span>
                  <div className="message-meta">
                    {msg.timestamp && (
                      <span className="message-time">{msg.timestamp}</span>
                    )}
                    <span className="message-role">
                      {msg.role === 'user' ? '👤' : msg.role === 'assistant' ? '🤖' : '📋'}
                    </span>
                  </div>
                </div>
                {(!isSent || isExpanded) && (
                  <div className="message-content">
                    {msg.content}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default PersonChat;