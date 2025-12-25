import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../controllers/agent_controller.dart';

class TaskRunner extends StatefulWidget {
  const TaskRunner({super.key});

  @override
  State<TaskRunner> createState() => _TaskRunnerState();
}

class _TaskRunnerState extends State<TaskRunner> {
  final _taskController = TextEditingController();
  bool _isSubmitting = false;

  @override
  void dispose() {
    _taskController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.watch<AgentController>();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Start a new task', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            TextField(
              controller: _taskController,
              maxLines: 4,
              decoration: const InputDecoration(
                hintText: 'Describe what the agent should do…',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                FilledButton.icon(
                  onPressed: _isSubmitting
                      ? null
                      : () async {
                          final task = _taskController.text.trim();
                          if (task.isEmpty) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Enter a task first.')),
                            );
                            return;
                          }
                          setState(() => _isSubmitting = true);
                          try {
                            await controller.runAgent(task);
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Agent started!')),
                              );
                            }
                          } catch (err) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('Unable to run agent: $err')),
                              );
                            }
                          } finally {
                            if (mounted) {
                              setState(() => _isSubmitting = false);
                            }
                          }
                        },
                  icon: const Icon(Icons.play_arrow),
                  label: Text(_isSubmitting ? 'Starting…' : 'Start Agent'),
                ),
              ],
            )
          ],
        ),
      ),
    );
  }
}
