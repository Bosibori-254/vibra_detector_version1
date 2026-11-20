export interface Alarm {
  alarm_id: string;
  node_id: string;
  segment: string;
  priority: 'advisory' | 'warning' | 'critical';
  state: string;
  cause: string;
  message: string;
  created_at: string;
  acknowledgement_count?: number;
}

export interface ActionAudit {
  action_id: string;
  timestamp: string;
  target: string;
  action_type: string;
  result: string;
  reason: string;
  before: number | null;
  after: number | null;
  operator: string;
}

export interface DeviceInfo {
  protocol: string;
  online: boolean;
  vfd_speed_rpm?: number;
  vibration_index?: number;
  [key: string]: unknown;
}

export interface Overview {
  site: string;
  segments: Array<{ id: string; status: string; nodes: string[] }>;
  devices: Record<string, DeviceInfo>;
  kill_switch: boolean;
}

export interface AlertEvent {
  type: string;
  verb?: string;
  alarm?: Alarm;
  audit?: ActionAudit;
  diagnosis?: { cause: string; confidence: number };
  [key: string]: unknown;
}
