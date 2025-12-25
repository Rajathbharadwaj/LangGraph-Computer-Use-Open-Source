import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';

class AgentLogPanel extends StatelessWidget {
  const AgentLogPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AgentController>();
    final formatter = DateFormat('HH:mm:ss');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Live Output', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Container(
              constraints: const BoxConstraints(minHeight: 120),
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surfaceVariant,
                borderRadius: BorderRadius.circular(12),
              ),
              child: controller.streamingBuffer.isEmpty
                  ? Text(
                      controller.isAgentRunning
                          ? 'Waiting for tokens…'
                          : 'No live tokens yet. Start the agent to stream updates.',
                    )
                  : MarkdownBody(data: controller.streamingBuffer),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Event Log', style: Theme.of(context).textTheme.titleMedium),
                Text('${controller.events.length} events'),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 220,
              child: ListView.separated(
                itemCount: controller.events.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, index) {
                  final event = controller.events[index];
                  final payloadSnippet = event.payload.toString();
                  return ListTile(
                    dense: true,
                    visualDensity: VisualDensity.compact,
                    title: Text(event.type),
                    subtitle: Text(
                      payloadSnippet.length > 120
                          ? '${payloadSnippet.substring(0, 120)}…'
                          : payloadSnippet,
                    ),
                    trailing: Text(formatter.format(event.timestamp)),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
