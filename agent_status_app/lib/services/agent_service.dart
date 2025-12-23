import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/agent_models.dart';

class AgentService {
  AgentService({
    required this.backendBaseUrl,
    required this.bearerToken,
  });

  final String backendBaseUrl;
  final String bearerToken;

  Uri _buildUri(String path, {Map<String, dynamic>? query}) {
    final normalizedBase = backendBaseUrl.endsWith('/')
        ? backendBaseUrl.substring(0, backendBaseUrl.length - 1)
        : backendBaseUrl;
    final uri = Uri.parse('$normalizedBase$path');
    if (query == null || query.isEmpty) {
      return uri;
    }
    return uri.replace(queryParameters: {
      ...uri.queryParameters,
      ...query.map((key, value) => MapEntry(key, value?.toString() ?? '')),
    });
  }

  Map<String, String> _headers() {
    final headers = {
      'Content-Type': 'application/json',
    };
    if (bearerToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $bearerToken';
    }
    return headers;
  }

  Future<AgentStatus> fetchStatus() async {
    final uri = _buildUri('/api/agent/status');
    final response = await http.get(uri, headers: _headers());
    if (response.statusCode >= 400) {
      throw Exception('Status request failed: ${response.body}');
    }
    return AgentStatus.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<AgentThread>> fetchThreads() async {
    final uri = _buildUri('/api/agent/threads/list');
    final response = await http.get(uri, headers: _headers());
    if (response.statusCode >= 400) {
      throw Exception('Thread list failed: ${response.body}');
    }
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final threadsJson = decoded['threads'] as List<dynamic>? ?? <dynamic>[];
    return threadsJson
        .whereType<Map<String, dynamic>>()
        .map(AgentThread.fromJson)
        .toList();
  }

  Future<List<AgentMessage>> fetchMessages(String threadId) async {
    final uri = _buildUri('/api/agent/threads/$threadId/messages');
    final response = await http.get(uri, headers: _headers());
    if (response.statusCode >= 400) {
      throw Exception('Message fetch failed: ${response.body}');
    }
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final messagesJson = decoded['messages'] as List<dynamic>? ?? <dynamic>[];
    return messagesJson
        .whereType<Map<String, dynamic>>()
        .map(AgentMessage.fromJson)
        .toList();
  }

  Future<Map<String, dynamic>> fetchThreadState(String threadId) async {
    final uri = _buildUri('/api/agent/state/$threadId');
    final response = await http.get(uri, headers: _headers());
    if (response.statusCode >= 400) {
      throw Exception('State fetch failed: ${response.body}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> runAgent({
    required String userId,
    required String task,
    String? threadId,
  }) async {
    final uri = _buildUri('/api/agent/run');
    final payload = {
      'user_id': userId,
      'task': task,
      if (threadId != null && threadId.isNotEmpty) 'thread_id': threadId,
    };
    final response = await http.post(
      uri,
      headers: _headers(),
      body: jsonEncode(payload),
    );
    if (response.statusCode >= 400) {
      throw Exception('Agent run failed: ${response.body}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> createNewThread({required String title}) async {
    final uri = _buildUri('/api/agent/threads/new');
    final response = await http.post(
      uri,
      headers: _headers(),
      body: jsonEncode({'title': title}),
    );
    if (response.statusCode >= 400) {
      throw Exception('Thread creation failed: ${response.body}');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
