import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';
import '../models/agent_models.dart';

class ThreadList extends StatelessWidget {
  const ThreadList({super.key});

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
                Text('Threads', style: Theme.of(context).textTheme.titleLarge),
                Wrap(
                  spacing: 12,
                  children: [
                    IconButton(
                      tooltip: 'Refresh',
                      onPressed: controller.loadThreads,
                      icon: const Icon(Icons.refresh),
                    ),
                    IconButton(
                      tooltip: 'New thread',
                      onPressed: () async {
                        final title = await _promptForTitle(context);
                        if (title != null && title.isNotEmpty) {
                          await controller.createThread(title);
                        }
                      },
                      icon: const Icon(Icons.add_comment),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 260,
              child: controller.threads.isEmpty
                  ? const Center(child: Text('No threads yet.'))
                  : ListView.builder(
                      itemCount: controller.threads.length,
                      itemBuilder: (context, index) {
                        final thread = controller.threads[index];
                        final isSelected = controller.selectedThread?.threadId == thread.threadId;
                        return Card(
                          color: isSelected
                              ? Theme.of(context).colorScheme.primaryContainer
                              : null,
                          child: ListTile(
                            dense: true,
                            title: Text(thread.title),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (thread.lastMessage?.isNotEmpty ?? false)
                                  Text(
                                    thread.lastMessage!,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                const SizedBox(height: 4),
                                Text(
                                  _formatThreadMeta(thread, formatter),
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                            onTap: () => controller.selectThread(thread),
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

  static String _formatThreadMeta(AgentThread thread, DateFormat formatter) {
    final created = thread.createdAt != null ? formatter.format(thread.createdAt!) : 'Unknown';
    final updated = thread.updatedAt != null ? formatter.format(thread.updatedAt!) : 'Unknown';
    return 'Created: $created · Updated: $updated';
  }

  Future<String?> _promptForTitle(BuildContext context) async {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('New thread title'),
          content: TextField(
            controller: controller,
            decoration: const InputDecoration(hintText: 'What should we talk about?'),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(controller.text.trim()),
              child: const Text('Create'),
            ),
          ],
        );
      },
    );
  }
}
