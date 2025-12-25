import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';

class MessageViewer extends StatelessWidget {
  const MessageViewer({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AgentController>();
    final formatter = DateFormat('MMM d, HH:mm');
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
                  controller.selectedThread == null
                      ? 'Thread Messages'
                      : 'Messages · ${controller.selectedThread!.title}',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                if (controller.selectedThread != null)
                  IconButton(
                    onPressed: () => controller.loadMessagesForThread(controller.selectedThread!.threadId),
                    icon: const Icon(Icons.refresh),
                    tooltip: 'Reload messages',
                  ),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 320,
              child: controller.selectedMessages.isEmpty
                  ? const Center(child: Text('Select a thread to see its history.'))
                  : ListView.builder(
                      itemCount: controller.selectedMessages.length,
                      itemBuilder: (context, index) {
                        final message = controller.selectedMessages[index];
                        final isUser = message.role.toLowerCase().contains('user');
                        return Align(
                          alignment: isUser ? Alignment.centerLeft : Alignment.centerRight,
                          child: Container(
                            margin: const EdgeInsets.only(bottom: 12),
                            padding: const EdgeInsets.all(12),
                            constraints: const BoxConstraints(maxWidth: 500),
                            decoration: BoxDecoration(
                              color: isUser
                                  ? Theme.of(context).colorScheme.secondaryContainer
                                  : Theme.of(context).colorScheme.primaryContainer,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  isUser ? 'You' : 'Agent',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                                const SizedBox(height: 4),
                                MarkdownBody(data: message.content),
                                if (message.timestamp != null)
                                  Align(
                                    alignment: Alignment.bottomRight,
                                    child: Text(
                                      formatter.format(message.timestamp!),
                                      style: Theme.of(context).textTheme.labelSmall,
                                    ),
                                  ),
                              ],
                            ),
                          ),
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
