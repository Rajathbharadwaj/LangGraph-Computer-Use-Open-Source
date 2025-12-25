import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';
import '../models/agent_models.dart';
import '../utils/environment_presets.dart';

class ConfigPanel extends StatefulWidget {
  const ConfigPanel({super.key});

  @override
  State<ConfigPanel> createState() => _ConfigPanelState();
}

class _ConfigPanelState extends State<ConfigPanel> {
  late final TextEditingController _backendController;
  late final TextEditingController _wsController;
  late final TextEditingController _userIdController;
  late final TextEditingController _tokenController;
  String? _configSignature;

  @override
  void initState() {
    super.initState();
    final config = context.read<AgentController>().config;
    _backendController = TextEditingController(text: config.backendBaseUrl);
    _wsController = TextEditingController(text: config.webSocketBaseUrl);
    _userIdController = TextEditingController(text: config.userId);
    _tokenController = TextEditingController(text: config.bearerToken);
  }

  @override
  void dispose() {
    _backendController.dispose();
    _wsController.dispose();
    _userIdController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AgentController>();
    final preset = presetForConfig(controller.config);
    final presetValue = preset?.id ?? 'custom';
    _syncControllers(controller.config);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Connection Settings',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                Wrap(
                  spacing: 12,
                  children: [
                    ElevatedButton.icon(
                      onPressed: controller.isConnectingWs
                          ? null
                          : controller.isWebSocketConnected
                              ? controller.disconnectWebSocket
                              : () async {
                                  try {
                                    await controller.connectWebSocket();
                                  } catch (_) {}
                                },
                      icon: Icon(
                        controller.isWebSocketConnected ? Icons.link_off : Icons.wifi,
                      ),
                      label: Text(
                        controller.isWebSocketConnected ? 'Disconnect WS' : 'Connect WS',
                      ),
                    ),
                    FilledButton.icon(
                      onPressed: () async {
                        final updated = AgentConfig(
                          backendBaseUrl: _backendController.text.trim(),
                          webSocketBaseUrl: _wsController.text.trim(),
                          userId: _userIdController.text.trim(),
                          bearerToken: _tokenController.text.trim(),
                        );
                        await controller.updateConfig(updated);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Configuration saved')),
                          );
                        }
                      },
                      icon: const Icon(Icons.save_alt),
                      label: const Text('Save'),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              value: presetValue,
              decoration: const InputDecoration(
                labelText: 'Environment Preset',
                border: OutlineInputBorder(),
              ),
              items: [
                const DropdownMenuItem(
                  value: 'custom',
                  child: Text('Custom (manual)'),
                ),
                ...environmentPresets.map(
                  (env) => DropdownMenuItem(
                    value: env.id,
                    child: Text(env.label),
                  ),
                ),
              ],
              onChanged: (value) async {
                if (value == null || value == 'custom') {
                  return;
                }
                final selected = environmentPresets.firstWhere(
                  (env) => env.id == value,
                  orElse: () => environmentPresets.first,
                );
                await controller.applyEnvironmentPreset(selected);
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Switched to ${selected.label} endpoints')),
                  );
                }
              },
            ),
            const SizedBox(height: 8),
            Text(
              preset?.description ?? 'Using custom endpoints (update the fields below).',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            _buildTextField('Backend URL', _backendController),
            const SizedBox(height: 12),
            _buildTextField('WebSocket URL', _wsController),
            const SizedBox(height: 12),
            _buildTextField('User ID', _userIdController),
            const SizedBox(height: 12),
            _buildTextField('Bearer Token', _tokenController, obscure: true),
          ],
        ),
      ),
    );
  }

  Widget _buildTextField(String label, TextEditingController controller, {bool obscure = false}) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      decoration: InputDecoration(
        labelText: label,
        border: const OutlineInputBorder(),
      ),
    );
  }

  void _syncControllers(AgentConfig config) {
    final signature = config.toString();
    if (signature == _configSignature) {
      return;
    }
    _backendController.text = config.backendBaseUrl;
    _wsController.text = config.webSocketBaseUrl;
    _userIdController.text = config.userId;
    _tokenController.text = config.bearerToken;
    _configSignature = signature;
  }
}
