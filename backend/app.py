from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from threading import Lock
from pathlib import Path

from src.chat import ChatWithMemory

load_dotenv()

app = Flask(__name__)
CORS(app)

# グローバル変数として災害対応チャットシステムを保持
chat_instance = None
chat_lock = Lock()

def get_chat_instance():
    global chat_instance
    with chat_lock:
        if chat_instance is None:
            chat_instance = ChatWithMemory()
        return chat_instance

def _add_csv_to_knowledge(csv_file_path: Path, knowledge_file_path: str):
    """CSV情報を知識ファイルに追加"""
    try:
        import pandas as pd

        # CSVファイルを読み込んでヘッダー情報を取得
        df = pd.read_csv(csv_file_path)
        filename = csv_file_path.name
        columns = df.columns.tolist()

        # カラム説明を読み込み（設定ファイルから）
        column_descriptions = {}
        csv_description = "(説明なし)"
        desc_file_path = Path(f"config/column_descriptions/{filename.replace('.csv', '.json')}")
        if desc_file_path.exists():
            import json
            with open(desc_file_path, 'r', encoding='utf-8') as f:
                desc_data = json.load(f)
                csv_description = desc_data.get("description", "(説明なし)")
                column_descriptions = desc_data.get("columns", {})
        else:
            # フォールバック: データの内容から推測
            for col in columns:
                sample_values = df[col].dropna().head(3).tolist()
                if sample_values:
                    column_descriptions[col] = f"例: {', '.join(map(str, sample_values))}"

        # 知識ファイルに追加
        knowledge_path = Path(knowledge_file_path)
        current = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""

        # CSV情報の作成
        columns_str = ", ".join(columns)
        column_desc_lines = []
        for col in columns:
            col_desc = column_descriptions.get(col, "")
            column_desc_lines.append(f"- {col}: {col_desc}")
        column_desc_text = f"\nカラム説明:\n" + "\n".join(column_desc_lines)

        # CSV情報セクションがない場合は作成
        if "# CSV情報" not in current:
            current += "\n\n# CSV情報\n\n## 保有CSV"

        new_entry = f"\n\n### 【{filename}】\n説明: {csv_description}\n現状のカラム: {columns_str}{column_desc_text}"
        knowledge_path.write_text(current + new_entry, encoding="utf-8")

        print(f"CSV情報を{knowledge_file_path}に追加: {filename}")

    except Exception as e:
        print(f"CSV知識追加エラー ({csv_file_path}): {e}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """ヘルスチェックエンドポイント"""
    return jsonify({"status": "ok"})

@app.route('/api/chat/start', methods=['POST'])
def start_chat():
    """チャットセッションを開始"""
    try:
        chat = get_chat_instance()
        current_time = chat.time_manager.get_current_time()
        return jsonify({
            "status": "started",
            "current_time": current_time,
            "message": f"災害対応訓練開始 - 現在時刻: {current_time}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/send', methods=['POST'])
def send_message():
    """メッセージを送信"""
    try:
        chat = get_chat_instance()
        data = request.json
        user_message = data.get('message', '')

        if not user_message:
            return jsonify({"error": "メッセージが空です"}), 400

        response = chat.send_message(user_message)
        current_time = chat.time_manager.get_current_time()

        return jsonify({
            "response": response,
            "current_time": current_time
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/history', methods=['GET'])
def get_history():
    """会話履歴を取得"""
    try:
        chat = get_chat_instance()
        manager_type = request.args.get('manager_type', 'all')
        person = request.args.get('person', None)  # 特定の人物の会話履歴

        # 特定の人物の会話履歴を取得
        if person:
            person_history = chat.get_person_history(person)
            return jsonify({
                "history": person_history,
                "manager_type": manager_type,
                "person": person
            })

        # マネージャータイプ別の履歴を取得
        history = chat.get_conversation_history(manager_type)
        return jsonify({
            "history": history,
            "manager_type": manager_type
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/person-histories', methods=['GET'])
def get_all_person_histories():
    """全ての人物の会話履歴を取得"""
    try:
        chat = get_chat_instance()
        all_histories = chat.get_all_person_histories()
        return jsonify(all_histories)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/time/current', methods=['GET'])
def get_current_time():
    """現在のシミュレーション時刻を取得"""
    try:
        chat = get_chat_instance()
        current_time = chat.time_manager.get_current_time()
        return jsonify({"current_time": current_time})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/time/speed', methods=['POST'])
def set_time_speed():
    """シミュレーション時間の速度を変更"""
    try:
        chat = get_chat_instance()
        data = request.json
        speed = data.get('speed', 1.0)

        if speed < 0.1 or speed > 10.0:
            return jsonify({"error": "速度は0.1から10.0の間で指定してください"}), 400

        chat.time_manager.speed_multiplier = float(speed)
        return jsonify({
            "status": "success",
            "speed_multiplier": chat.time_manager.speed_multiplier,
            "current_time": chat.time_manager.get_current_time()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/managers/status', methods=['GET'])
def get_managers_status():
    """各マネージャーのステータスを取得"""
    try:
        chat = get_chat_instance()

        # 各マネージャーの状態を取得
        info_status = {
            "name": "情報管理班",
            "available": not chat.info_manager.away_from_desk,
            "in_conversation": chat.info_manager.in_conversation,
            "memory": {
                "csv_data": list(chat.info_manager.csv_manager.csv_data.keys()) if hasattr(chat.info_manager, 'csv_manager') else [],
                "conversation_count": len(chat.info_conversation_history)
            }
        }

        supply_status = {
            "name": "物資管理班",
            "available": not chat.supply_manager.away_from_desk,
            "in_conversation": chat.supply_manager.in_conversation,
            "memory": {
                "csv_data": list(chat.supply_manager.csv_manager.csv_data.keys()) if hasattr(chat.supply_manager, 'csv_manager') else [],
                "conversation_count": len(chat.supply_conversation_history),
                "inventory": chat.supply_manager.inventory if hasattr(chat.supply_manager, 'inventory') else {}
            }
        }

        return jsonify({
            "information_manager": info_status,
            "supply_manager": supply_status
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/manager-data', methods=['GET'])
def get_manager_debug_data():
    """開発者ツール：各マネージャーが保有するデータの詳細を取得"""
    try:
        chat = get_chat_instance()
        manager_type = request.args.get('manager_type', 'all')

        debug_data = {}

        # 情報管理班のデータ
        if manager_type in ['all', 'information']:
            info_data = {
                "name": "情報管理班",
                "class": "InformationManager",
                "status": {
                    "available": not getattr(chat.info_manager, 'away_from_desk', False),
                    "in_conversation": getattr(chat.info_manager, 'in_conversation', False),
                    "away_reason": getattr(chat.info_manager, 'away_reason', None)
                },
                "csv_files": {},
                "memory": {
                    "conversation_history_count": len(getattr(chat, 'info_conversation_history', [])),
                    "conversation_sample": getattr(chat, 'info_conversation_history', [])[-3:] if getattr(chat, 'info_conversation_history', []) else []
                },
                "workers": []
            }

            # CSVデータの詳細 - 直接ファイルから読み込み
            try:
                import pandas as pd
                from pathlib import Path

                csv_path = Path("csv/information")
                if csv_path.exists():
                    for csv_file in csv_path.glob("*.csv"):
                        try:
                            df = pd.read_csv(csv_file)
                            # NaN値を空文字列に変換(⭐️これがないとnullは表示できないためおかしくなる)
                            df = df.fillna('')
                            info_data["csv_files"][csv_file.name] = {
                                "shape": df.shape,
                                "columns": df.columns.tolist(),
                                "sample_data": df.to_dict('records'),
                                "dtypes": df.dtypes.astype(str).to_dict()
                            }
                        except Exception as file_error:
                            print(f"Error reading {csv_file}: {file_error}")
            except Exception as csv_error:
                print(f"CSV data error for info_manager: {csv_error}")

            # 知識ファイルの読み込み
            try:
                from pathlib import Path

                knowledge_files = {}
                knowledge_path = Path("src/knowledge")

                # 情報管理班専用knowledge
                info_knowledge_path = knowledge_path / "knowledge_information.txt"
                if info_knowledge_path.exists():
                    with open(info_knowledge_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            knowledge_files["knowledge_information.txt"] = content

                info_data["knowledge_files"] = knowledge_files
            except Exception as knowledge_error:
                print(f"Knowledge file error for info_manager: {knowledge_error}")
                info_data["knowledge_files"] = {}

            # Workerの情報
            try:
                if hasattr(chat.info_manager, 'workers'):
                    for worker in chat.info_manager.workers:
                        worker_info = {
                            "type": type(worker).__name__,
                            "available": worker.is_available() if hasattr(worker, 'is_available') else True
                        }
                        info_data["workers"].append(worker_info)
            except Exception as worker_error:
                print(f"Worker data error for info_manager: {worker_error}")

            debug_data["information_manager"] = info_data

        # 物資管理班のデータ
        if manager_type in ['all', 'supply']:
            supply_data = {
                "name": "物資管理班",
                "class": "SupplyManager",
                "status": {
                    "available": not getattr(chat.supply_manager, 'away_from_desk', False),
                    "in_conversation": getattr(chat.supply_manager, 'in_conversation', False),
                    "away_reason": getattr(chat.supply_manager, 'away_reason', None)
                },
                "csv_files": {},
                "inventory": getattr(chat.supply_manager, 'inventory', {}),
                "memory": {
                    "conversation_history_count": len(getattr(chat, 'supply_conversation_history', [])),
                    "conversation_sample": getattr(chat, 'supply_conversation_history', [])[-3:] if getattr(chat, 'supply_conversation_history', []) else [],
                    "deliveries": getattr(chat.supply_manager, 'deliveries', [])
                },
                "workers": []
            }

            # CSVデータの詳細 - 直接ファイルから読み込み
            try:
                import pandas as pd
                from pathlib import Path

                csv_path = Path("csv/supply")
                if csv_path.exists():
                    for csv_file in csv_path.glob("*.csv"):
                        try:
                            df = pd.read_csv(csv_file)
                            # NaN値を空文字列に変換
                            df = df.fillna('')
                            supply_data["csv_files"][csv_file.name] = {
                                "shape": df.shape,
                                "columns": df.columns.tolist(),
                                "sample_data": df.to_dict('records'),
                                "dtypes": df.dtypes.astype(str).to_dict()
                            }
                        except Exception as file_error:
                            print(f"Error reading {csv_file}: {file_error}")
            except Exception as csv_error:
                print(f"CSV data error for supply_manager: {csv_error}")

            # 知識ファイルの読み込み
            try:
                from pathlib import Path

                knowledge_files = {}
                knowledge_path = Path("src/knowledge")

                # 物資管理班専用knowledge
                supply_knowledge_path = knowledge_path / "knowledge_supply.txt"
                if supply_knowledge_path.exists():
                    with open(supply_knowledge_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            knowledge_files["knowledge_supply.txt"] = content

                supply_data["knowledge_files"] = knowledge_files
            except Exception as knowledge_error:
                print(f"Knowledge file error for supply_manager: {knowledge_error}")
                supply_data["knowledge_files"] = {}

            # Workerの情報
            try:
                if hasattr(chat.supply_manager, 'workers'):
                    for worker in chat.supply_manager.workers:
                        worker_info = {
                            "type": type(worker).__name__,
                            "available": worker.is_available() if hasattr(worker, 'is_available') else True
                        }
                        supply_data["workers"].append(worker_info)
            except Exception as worker_error:
                print(f"Worker data error for supply_manager: {worker_error}")

            debug_data["supply_manager"] = supply_data

        return jsonify(debug_data)
    except Exception as e:
        import traceback
        print(f"Manager debug data error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route('/api/debug/system-info', methods=['GET'])
def get_system_debug_info():
    """開発者ツール：システム全体の情報を取得"""
    try:
        chat = get_chat_instance()

        system_info = {
            "time_manager": {
                "current_time": chat.time_manager.get_current_time(),
                "start_time": chat.time_manager.start_time if hasattr(chat.time_manager, 'start_time') else None,
                "speed_multiplier": chat.time_manager.speed_multiplier if hasattr(chat.time_manager, 'speed_multiplier') else 1.0
            },
            "inf_provider": {
                "scheduled_tasks_count": len(chat.inf_provider.scheduled_infos) if hasattr(chat.inf_provider, 'scheduled_infos') else 0,
                "simulation_time": chat.inf_provider.simulation_time if hasattr(chat.inf_provider, 'simulation_time') else None
            },
            "global_conversation_history_count": len(chat.conversation_history)
        }

        return jsonify(system_info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/person/info', methods=['GET'])
def get_person_info():
    """人物の知識とCSV情報を取得"""
    try:
        person = request.args.get('person', None)
        if not person:
            return jsonify({"error": "person parameter is required"}), 400

        chat = get_chat_instance()
        person_info = {
            "person": person,
            "knowledge": "",
            "csv_files": [],
            "available": True
        }

        # Manager別の情報取得
        if person == "information_manager":
            manager = chat.info_manager
            # 知識情報
            person_info["knowledge"] = manager.get_knowledge()
            # CSV情報
            csv_files = []
            csv_path = Path("./csv/information")
            if csv_path.exists():
                for csv_file in csv_path.glob("*.csv"):
                    try:
                        import pandas as pd
                        df = pd.read_csv(csv_file)
                        csv_files.append({
                            "name": csv_file.name,
                            "rows": len(df),
                            "columns": df.columns.tolist()
                        })
                    except:
                        csv_files.append({
                            "name": csv_file.name,
                            "rows": 0,
                            "columns": []
                        })
            person_info["csv_files"] = csv_files
            person_info["available"] = not manager.away_until_time

        elif person == "supply_manager":
            manager = chat.supply_manager
            # 知識情報
            person_info["knowledge"] = manager.get_knowledge()
            # CSV情報
            csv_files = []
            csv_path = Path("./csv/supply")
            if csv_path.exists():
                for csv_file in csv_path.glob("*.csv"):
                    try:
                        import pandas as pd
                        df = pd.read_csv(csv_file)
                        csv_files.append({
                            "name": csv_file.name,
                            "rows": len(df),
                            "columns": df.columns.tolist()
                        })
                    except:
                        csv_files.append({
                            "name": csv_file.name,
                            "rows": 0,
                            "columns": []
                        })
            person_info["csv_files"] = csv_files
            person_info["available"] = not manager.away_until_time

        elif person.startswith("ワーカー"):
            # Workerの場合、supply_managerから情報取得
            worker_name = person
            workers = chat.supply_manager.workers
            worker = None
            for w in workers:
                if w.worker_name == worker_name:
                    worker = w
                    break

            if worker:
                person_info["knowledge"] = f"担当タスク: {worker.current_task or '待機中'}"
                person_info["available"] = worker.available
            else:
                person_info["knowledge"] = "Worker情報が見つかりません"

        elif person == "Player":
            person_info["knowledge"] = "災害対応訓練参加者として、情報管理班と物資管理班と連携して対応を行う"
            person_info["available"] = True

        else:
            person_info["knowledge"] = "情報が利用できません"

        return jsonify(person_info)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/reset', methods=['POST'])
def reset_system():
    """システムを完全初期化（CSV、会話履歴、記憶をすべてリセット）"""
    global chat_instance
    try:
        import shutil
        from pathlib import Path

        with chat_lock:
            # 既存のチャットインスタンスを削除
            chat_instance = None

            # CSVファイルの初期化
            init_data_path = Path("config/init_data")
            csv_path = Path("csv")

            # csvディレクトリをクリア
            if csv_path.exists():
                shutil.rmtree(csv_path)

            # csvディレクトリを再作成
            csv_path.mkdir(exist_ok=True)
            (csv_path / "supply").mkdir(exist_ok=True)
            (csv_path / "information").mkdir(exist_ok=True)

            # 知識ファイルを初期化
            knowledge_path = Path("src/knowledge")
            knowledge_path.mkdir(exist_ok=True)

            # 知識ファイルを空にして初期化
            (knowledge_path / "knowledge_information.txt").write_text("", encoding="utf-8")
            (knowledge_path / "knowledge_supply.txt").write_text("", encoding="utf-8")

            # 初期データファイルをコピーし、知識ファイルにCSV情報を追加
            if init_data_path.exists():
                for file in init_data_path.glob("*.csv"):
                    if "物資" in file.name:
                        shutil.copy2(file, csv_path / "supply" / file.name)
                        # 物資管理班の知識ファイルにCSV情報を追加
                        _add_csv_to_knowledge(file, "src/knowledge/knowledge_supply.txt")
                    else:
                        shutil.copy2(file, csv_path / "information" / file.name)
                        # 情報管理班の知識ファイルにCSV情報を追加
                        _add_csv_to_knowledge(file, "src/knowledge/knowledge_information.txt")

        # 新しいチャットインスタンスを作成
        new_chat = get_chat_instance()

        return jsonify({
            "status": "success",
            "message": "システムが完全に初期化されました",
            "current_time": new_chat.time_manager.get_current_time(),
            "reset_items": [
                "会話履歴",
                "マネージャー記憶",
                "CSVデータ（初期状態に復元）",
                "時間設定"
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)