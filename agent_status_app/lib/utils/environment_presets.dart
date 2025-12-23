import '../models/agent_models.dart';

class EnvironmentPreset {
  const EnvironmentPreset({
    required this.id,
    required this.label,
    required this.backendBaseUrl,
    required this.webSocketBaseUrl,
    this.description,
  });

  final String id;
  final String label;
  final String backendBaseUrl;
  final String webSocketBaseUrl;
  final String? description;
}

const environmentPresets = <EnvironmentPreset>[
  EnvironmentPreset(
    id: 'production',
    label: 'Cloud Run (Production)',
    backendBaseUrl: kProductionBackendUrl,
    webSocketBaseUrl: kProductionWebSocketUrl,
    description: 'Matches the cua-frontend deployment URLs defined in DEPLOYMENT_READY.md.',
  ),
  EnvironmentPreset(
    id: 'local',
    label: 'Local Development',
    backendBaseUrl: kLocalBackendUrl,
    webSocketBaseUrl: kLocalWebSocketUrl,
    description: 'Use when running backend_websocket_server.py on your workstation.',
  ),
];

EnvironmentPreset? presetForConfig(AgentConfig config) {
  for (final preset in environmentPresets) {
    if (preset.backendBaseUrl == config.backendBaseUrl &&
        preset.webSocketBaseUrl == config.webSocketBaseUrl) {
      return preset;
    }
  }
  return null;
}
