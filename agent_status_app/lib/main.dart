import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'controllers/agent_controller.dart';
import 'widgets/agent_log_panel.dart';
import 'widgets/config_panel.dart';
import 'widgets/message_viewer.dart';
import 'widgets/status_overview.dart';
import 'widgets/task_runner.dart';
import 'widgets/thread_list.dart';

void main() {
  runApp(const AgentStatusApp());
}

class AgentStatusApp extends StatelessWidget {
  const AgentStatusApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AgentController(),
      child: MaterialApp(
        title: 'Agent Status',
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF4E8DF2)),
        ),
        home: const AgentStatusHomePage(),
      ),
    );
  }
}

class AgentStatusHomePage extends StatelessWidget {
  const AgentStatusHomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Agent Control Center'),
        actions: [
          IconButton(
            tooltip: 'Refresh Threads',
            onPressed: () => context.read<AgentController>().loadThreads(),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: SafeArea(
        child: Consumer<AgentController>(
          builder: (context, controller, _) {
            if (!controller.isConfigReady) {
              return const Center(child: CircularProgressIndicator());
            }
            return LayoutBuilder(
              builder: (context, constraints) {
                final isWide = constraints.maxWidth > 900;
                final children = <Widget>[
                  const ConfigPanel(),
                  const SizedBox(height: 16),
                  if (isWide)
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Expanded(child: StatusOverview()),
                        SizedBox(width: 16),
                        Expanded(child: TaskRunner()),
                      ],
                    )
                  else ...const [
                      StatusOverview(),
                      SizedBox(height: 16),
                      TaskRunner(),
                    ],
                  const SizedBox(height: 16),
                  if (isWide)
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Expanded(child: ThreadList()),
                        SizedBox(width: 16),
                        Expanded(child: MessageViewer()),
                      ],
                    )
                  else ...const [
                      ThreadList(),
                      SizedBox(height: 16),
                      MessageViewer(),
                    ],
                  const SizedBox(height: 16),
                  const AgentLogPanel(),
                ];

                return Align(
                  alignment: Alignment.topCenter,
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 1200),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: children,
                      ),
                    ),
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }
}
