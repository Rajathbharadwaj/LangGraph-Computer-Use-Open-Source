import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/agent_models.dart';

class Preferences {
  static const _configKey = 'agent_config';

  static Future<AgentConfig> loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_configKey);
    if (raw == null) {
      return AgentConfig.fromJson({});
    }
    return AgentConfig.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

  static Future<void> saveConfig(AgentConfig config) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_configKey, jsonEncode(config.toJson()));
  }

  static Future<void> clearConfig() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_configKey);
  }
}
