import 'dart:convert';

const kProductionBackendUrl = 'https://backend-api-644185288504.us-central1.run.app';
const kProductionWebSocketUrl = 'wss://backend-api-644185288504.us-central1.run.app/ws/extension/';
const kLocalBackendUrl = 'http://localhost:8002';
const kLocalWebSocketUrl = 'ws://localhost:8001/ws/extension/';

class AgentConfig {
  AgentConfig({
    required this.backendBaseUrl,
    required this.webSocketBaseUrl,
    required this.userId,
    required this.bearerToken,
  });

  final String backendBaseUrl;
  final String webSocketBaseUrl;
  final String userId;
  final String bearerToken;

  AgentConfig copyWith({
    String? backendBaseUrl,
    String? webSocketBaseUrl,
    String? userId,
    String? bearerToken,
  }) {
    return AgentConfig(
      backendBaseUrl: backendBaseUrl ?? this.backendBaseUrl,
      webSocketBaseUrl: webSocketBaseUrl ?? this.webSocketBaseUrl,
      userId: userId ?? this.userId,
      bearerToken: bearerToken ?? this.bearerToken,
    );
  }

  Map<String, dynamic> toJson() => {
        'backendBaseUrl': backendBaseUrl,
        'webSocketBaseUrl': webSocketBaseUrl,
        'userId': userId,
        'bearerToken': bearerToken,
      };

  factory AgentConfig.fromJson(Map<String, dynamic> json) {
    return AgentConfig(
      backendBaseUrl: json['backendBaseUrl'] as String? ?? kProductionBackendUrl,
      webSocketBaseUrl:
          json['webSocketBaseUrl'] as String? ?? kProductionWebSocketUrl,
      userId: json['userId'] as String? ?? '',
      bearerToken: json['bearerToken'] as String? ?? '',
    );
  }

  @override
  String toString() => jsonEncode(toJson());
}

class AgentStatus {
  AgentStatus({
    required this.isRunning,
    this.threadId,
    this.runId,
  });

  final bool isRunning;
  final String? threadId;
  final String? runId;

  factory AgentStatus.fromJson(Map<String, dynamic> json) {
    return AgentStatus(
      isRunning: json['is_running'] as bool? ?? json['isRunning'] as bool? ?? false,
      threadId: json['thread_id'] as String? ?? json['threadId'] as String?,
      runId: json['run_id'] as String? ?? json['runId'] as String?,
    );
  }
}

class AgentThread {
  AgentThread({
    required this.threadId,
    required this.title,
    this.lastMessage,
    this.createdAt,
    this.updatedAt,
  });

  final String threadId;
  final String title;
  final String? lastMessage;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  factory AgentThread.fromJson(Map<String, dynamic> json) {
    DateTime? parseDate(String? raw) {
      if (raw == null || raw.isEmpty) {
        return null;
      }
      return DateTime.tryParse(raw);
    }

    return AgentThread(
      threadId: json['thread_id'] as String? ?? json['threadId'] as String? ?? '',
      title: json['title'] as String? ?? 'Untitled Thread',
      lastMessage: json['last_message'] as String? ?? json['lastMessage'] as String?,
      createdAt: parseDate(json['created_at'] as String?),
      updatedAt: parseDate(json['updated_at'] as String?),
    );
  }
}

class AgentMessage {
  AgentMessage({
    required this.role,
    required this.content,
    this.timestamp,
  });

  final String role;
  final String content;
  final DateTime? timestamp;

  factory AgentMessage.fromJson(Map<String, dynamic> json) {
    DateTime? parseTimestamp(String? raw) {
      if (raw == null || raw.isEmpty) {
        return null;
      }
      return DateTime.tryParse(raw);
    }

    return AgentMessage(
      role: json['role'] as String? ?? 'assistant',
      content: json['content'] as String? ?? '',
      timestamp: parseTimestamp(json['timestamp'] as String?),
    );
  }
}

class AgentEvent {
  AgentEvent({
    required this.type,
    required this.timestamp,
    required this.payload,
  });

  final String type;
  final DateTime timestamp;
  final Map<String, dynamic> payload;

  factory AgentEvent.fromPayload(Map<String, dynamic> payload) {
    return AgentEvent(
      type: payload['type'] as String? ?? 'UNKNOWN',
      timestamp: DateTime.now(),
      payload: payload,
    );
  }
}
