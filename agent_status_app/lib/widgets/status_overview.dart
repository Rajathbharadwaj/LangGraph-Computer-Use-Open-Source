import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';

class StatusOverview extends StatelessWidget {
  const StatusOverview({super.key});

  Color _statusColor(BuildContext context, bool isRunning) {
    final scheme = Theme.of(context).colorScheme;
    return isRunning ? scheme.errorContainer : scheme.tertiaryContainer;
  }

  String _statusLabel(bool isRunning) => isRunning ? 'Running' : 'Idle';

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AgentController>();
    final status = controller.status;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Agent Status', style: Theme.of(context).textTheme.titleLarge),
                IconButton(
                  tooltip: 'Refresh',
                  onPressed: controller.refreshStatus,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: _statusColor(context, controller.isAgentRunning),
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: Text(
                    _statusLabel(controller.isAgentRunning),
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Thread: ${status?.threadId ?? '—'}'),
                      Text('Run ID: ${status?.runId ?? '—'}'),
                    ],
                  ),
                ),
              ],
            ),
            if (controller.lastError != null) ...[
              const SizedBox(height: 12),
              Text(
                controller.lastError!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
