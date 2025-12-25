import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/agent_models.dart';
import '../services/agent_service.dart';
import '../utils/preferences.dart';
import '../utils/environment_presets.dart';

class AgentController extends ChangeNotifier {
  AgentController() {
    _init();
  }

  AgentConfig _config = AgentConfig.fromJson({});
  AgentService? _service;

  bool get isConfigReady => _isConfigReady;
  bool _isConfigReady = false;

  bool get isConnectingWs => _isConnectingWs;
  bool _isConnectingWs = false;

  bool get isWebSocketConnected => _channel != null;

  AgentStatus? get status => _status;
  AgentStatus? _status;

  List<AgentThread> get threads => List.unmodifiable(_threads);
  final List<AgentThread> _threads = [];

  List<AgentMessage> get selectedMessages => List.unmodifiable(_selectedMessages);
  final List<AgentMessage> _selectedMessages = [];

  AgentThread? get selectedThread => _selectedThread;
  AgentThread? _selectedThread;

  List<AgentEvent> get events => List.unmodifiable(_events);
  final List<AgentEvent> _events = [];

  String get streamingBuffer => _streamingBuffer;
  String _streamingBuffer = '';

  String? _lastError;
  String? get lastError => _lastError;

  bool get isAgentRunning => status?.isRunning ?? false;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _channelSubscription;

  Future<void> _init() async {
    _config = await Preferences.loadConfig();
    _rebuildService();
    _isConfigReady = true;
    notifyListeners();
    await refreshStatus();
    await loadThreads();
  }

  AgentConfig get config => _config;

  Future<void> updateConfig(AgentConfig config, {bool persist = true}) async {
    _config = config;
    _rebuildService();
    if (persist) {
      await Preferences.saveConfig(config);
    }
    notifyListeners();
  }

  Future<void> applyEnvironmentPreset(EnvironmentPreset preset) async {
    final updated = _config.copyWith(
      backendBaseUrl: preset.backendBaseUrl,
      webSocketBaseUrl: preset.webSocketBaseUrl,
    );
    await updateConfig(updated);
  }

  void _rebuildService() {
    _service = AgentService(
      backendBaseUrl: _config.backendBaseUrl,
      bearerToken: _config.bearerToken,
    );
  }

  Future<void> refreshStatus() async {
    if (_service == null || _config.bearerToken.isEmpty) {
      return;
    }
    try {
      _status = await _service!.fetchStatus();
      notifyListeners();
    } catch (err) {
      _lastError = 'Unable to fetch status: $err';
      notifyListeners();
    }
  }

  Future<void> loadThreads() async {
    if (_service == null || _config.bearerToken.isEmpty) {
      return;
    }
    try {
      _threads
        ..clear()
        ..addAll(await _service!.fetchThreads());
      notifyListeners();
    } catch (err) {
      _lastError = 'Unable to load threads: $err';
      notifyListeners();
    }
  }

  Future<void> selectThread(AgentThread thread) async {
    _selectedThread = thread;
    notifyListeners();
    await loadMessagesForThread(thread.threadId);
  }

  Future<void> loadMessagesForThread(String threadId) async {
    if (_service == null) {
      return;
    }
    try {
      _selectedMessages
        ..clear()
        ..addAll(await _service!.fetchMessages(threadId));
      notifyListeners();
    } catch (err) {
      _lastError = 'Unable to fetch thread messages: $err';
      notifyListeners();
    }
  }

  Future<void> runAgent(String task) async {
    if (_service == null) {
      throw Exception('Configure backend URL + token before running the agent.');
    }
    if (task.isEmpty) {
      throw Exception('Task cannot be empty.');
    }
    final userId = _config.userId;
    if (userId.isEmpty) {
      throw Exception('User ID is required to run the agent.');
    }
    final threadId = _selectedThread?.threadId ?? status?.threadId;
    try {
      final response = await _service!.runAgent(
        userId: userId,
        task: task,
        threadId: threadId,
      );
      _events.insert(0, AgentEvent.fromPayload(response));
      _streamingBuffer = '';
      notifyListeners();
    } catch (err) {
      _lastError = 'Unable to start agent: $err';
      notifyListeners();
      rethrow;
    }
  }

  Future<void> createThread(String title) async {
    if (_service == null || _config.bearerToken.isEmpty) {
      return;
    }
    try {
      final response = await _service!.createNewThread(title: title);
      _events.insert(0, AgentEvent.fromPayload(response));
      await loadThreads();
      notifyListeners();
    } catch (err) {
      _lastError = 'Unable to create thread: $err';
      notifyListeners();
    }
  }

  Future<void> connectWebSocket() async {
    if (_config.userId.isEmpty) {
      throw Exception('Enter a user ID before connecting to the WebSocket.');
    }
    final channelUrl = _buildWebSocketUrl();
    _isConnectingWs = true;
    notifyListeners();
    try {
      await _channelSubscription?.cancel();
      await _channel?.sink.close();
      _channel = WebSocketChannel.connect(Uri.parse(channelUrl));
      _channelSubscription = _channel!.stream.listen(
        _handleSocketPayload,
        onDone: () {
          _channel = null;
          _isConnectingWs = false;
          notifyListeners();
        },
        onError: (error, _) {
          _lastError = 'WebSocket error: $error';
          _channel = null;
          _isConnectingWs = false;
          notifyListeners();
        },
      );
    } catch (err) {
      _lastError = 'Unable to connect: $err';
      _channel = null;
      await _channelSubscription?.cancel();
      _channelSubscription = null;
      _isConnectingWs = false;
      notifyListeners();
      rethrow;
    }
    _isConnectingWs = false;
    notifyListeners();
  }

  Future<void> disconnectWebSocket() async {
    await _channelSubscription?.cancel();
    _channelSubscription = null;
    await _channel?.sink.close();
    _channel = null;
    notifyListeners();
  }

  String _buildWebSocketUrl() {
    final base = _config.webSocketBaseUrl;
    final normalized = base.endsWith('/') ? base : '$base/';
    return '$normalized${_config.userId}';
  }

  void _handleSocketPayload(dynamic raw) {
    Map<String, dynamic>? payload;
    if (raw is String) {
      payload = jsonDecode(raw) as Map<String, dynamic>;
    } else if (raw is List<int>) {
      payload = jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
    } else if (raw is Map<String, dynamic>) {
      payload = raw;
    }
    if (payload == null) {
      return;
    }
    final event = AgentEvent.fromPayload(payload);
    _events.insert(0, event);
    if (_events.length > 200) {
      _events.removeLast();
    }

    switch (event.type) {
      case 'CONNECTED':
        break;
      case 'AGENT_STARTED':
        _status = AgentStatus(
          isRunning: true,
          threadId: payload['thread_id'] as String? ?? payload['threadId'] as String?,
          runId: null,
        );
        _streamingBuffer = '';
        break;
      case 'AGENT_TOKEN':
        final tokenPayload = payload['token'];
        final token = tokenPayload is String ? tokenPayload : tokenPayload?.toString() ?? '';
        _streamingBuffer += token;
        break;
      case 'AGENT_COMPLETED':
      case 'AGENT_CANCELLED':
        _status = AgentStatus(
          isRunning: false,
          threadId: (payload['thread_id'] as String?) ?? status?.threadId,
          runId: status?.runId,
        );
        break;
      case 'AGENT_ERROR':
        _lastError = payload['error'] as String?;
        _status = AgentStatus(isRunning: false, threadId: status?.threadId, runId: status?.runId);
        break;
      case 'THREAD_RECREATED':
        final newThreadId = payload['new_thread_id'] as String?;
        if (newThreadId != null) {
          _status = AgentStatus(isRunning: false, threadId: newThreadId, runId: null);
        }
        break;
      default:
        break;
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _channelSubscription?.cancel();
    _channel?.sink.close();
    super.dispose();
  }
}
