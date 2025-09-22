export interface Message {
  role: string;
  name?: string;
  content: string;
}

export interface ManagerStatus {
  name: string;
  available: boolean;
  in_conversation: boolean;
  memory: {
    csv_data: string[];
    conversation_count: number;
    inventory?: Record<string, number>;
    deliveries?: any[];
  };
}

export interface ManagerDebugData {
  name: string;
  class: string;
  status: {
    available: boolean;
    in_conversation: boolean;
    away_reason?: string;
  };
  csv_files: Record<string, {
    shape: [number, number];
    columns: string[];
    sample_data: any[];
    dtypes: Record<string, string>;
  }>;
  knowledge_files: Record<string, string>;
  memory: {
    conversation_history_count: number;
    conversation_sample: Message[];
    inventory?: Record<string, number>;
    deliveries?: any[];
  };
  workers: Array<{
    type: string;
    available: boolean;
  }>;
}

export interface SystemInfo {
  time_manager: {
    current_time: string;
    start_time?: string;
    speed_multiplier?: number;
  };
  inf_provider: {
    scheduled_tasks_count: number;
    simulation_time?: string;
  };
  global_conversation_history_count: number;
}