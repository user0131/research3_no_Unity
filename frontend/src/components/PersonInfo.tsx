import React, { useState, useEffect } from 'react';
import './PersonInfo.css';

interface CsvFile {
  name: string;
  rows: number;
  columns: string[];
}

interface PersonInfoData {
  person: string;
  knowledge: string;
  csv_files: CsvFile[];
  available: boolean;
}

interface PersonInfoProps {
  person: string;
}

const PersonInfo: React.FC<PersonInfoProps> = ({ person }) => {
  const [personInfo, setPersonInfo] = useState<PersonInfoData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [expandedCsvs, setExpandedCsvs] = useState<Record<string, boolean>>({});

  useEffect(() => { // 1秒ごとに更新
    fetchPersonInfo();
    const interval = setInterval(fetchPersonInfo, 1000);
    return () => clearInterval(interval);
  }, [person]);

  const fetchPersonInfo = async () => {
    try {
      setIsLoading(true);
      const response = await fetch(`http://localhost:5000/api/person/info?person=${person}`);
      const data = await response.json();
      setPersonInfo(data);
    } catch (error) {
      console.error('Failed to fetch person info:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleCsv = (csvName: string) => {
    setExpandedCsvs(prev => ({
      ...prev,
      [csvName]: !prev[csvName]
    }));
  };

  const getPersonDisplayName = (personName: string) => {
    const nameMap: { [key: string]: string } = {
      'Player': 'Player',
      'supply_manager': '物資Manager',
      'information_manager': '情報Manager',
      'infrastructure_manager': '土木Manager',
      'ワーカーA': 'Worker A',
      'ワーカーB': 'Worker B',
      'ワーカーC': 'Worker C',
      '土木ワーカーA': '土木Worker A',
      '土木ワーカーB': '土木Worker B',
      '土木ワーカーC': '土木Worker C',
      'System': 'System'
    };
    return nameMap[personName] || personName;
  };

  if (isLoading && !personInfo) {
    return (
      <div className="person-info">
        <div className="loading">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="person-info">
      <h3>{getPersonDisplayName(person)}</h3>

      {personInfo && (
        <>
          <div className="csv-section">
            <h4>保有CSVファイル ▼</h4>
            <div className="csv-list">
              {personInfo.csv_files && personInfo.csv_files.length > 0 ? (
                personInfo.csv_files.map((csv, index) => (
                  <div key={index} className="csv-item">
                    <div
                      className="csv-header"
                      onClick={() => toggleCsv(csv.name)}
                    >
                      <div className="csv-name">{csv.name}</div>
                      <div className="csv-summary">
                        {csv.rows}行 × {csv.columns.length}列
                      </div>
                    </div>
                    {expandedCsvs[csv.name] && (
                      <div className="csv-details">
                        <div className="csv-columns">
                          <strong>カラム:</strong>
                          <div className="columns-list">
                            {csv.columns.join(', ')}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div className="csv-empty">CSVファイルがありません</div>
              )}
            </div>
          </div>

          <div className="knowledge-section">
            <h4>知っている知識 ▼</h4>
            <div className="knowledge-item">
              <div className="knowledge-header">
                <span className="knowledge-filename">
                  {person === 'supply_manager' ? 'knowledge_supply.txt' :
                   person === 'information_manager' ? 'knowledge_information.txt' :
                   person === 'infrastructure_manager' ? 'knowledge_infrastructure.txt' :
                   'knowledge.txt'}
                </span>
              </div>
              <div className="knowledge-content">
                {personInfo.knowledge ? (
                  <pre>{personInfo.knowledge}</pre>
                ) : (
                  <div className="knowledge-empty">知識ファイルが空です</div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default PersonInfo;