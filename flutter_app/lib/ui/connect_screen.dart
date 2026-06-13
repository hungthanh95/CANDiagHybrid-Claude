// Connect screen (docs/03-TECHNICAL-DETAIL.md §7): enter the bridge WS
// host/port, connect/disconnect, and show the `READY` banner (tool/transport
// per docs/03 §1.1).
//
// Depends only on AppState -- never constructs WsTransport directly.

import 'package:flutter/material.dart';

import '../state/app_state.dart';

/// Connect/disconnect screen.
class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.appState});

  final AppState appState;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  // Defaults per CLAUDE.md §5: WS 127.0.0.1:8770.
  final TextEditingController _hostController = TextEditingController(
    text: '127.0.0.1',
  );
  final TextEditingController _portController = TextEditingController(
    text: '8770',
  );

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  String _statusLabel(ConnectionStatus status) {
    switch (status) {
      case ConnectionStatus.disconnected:
        return 'Disconnected';
      case ConnectionStatus.connecting:
        return 'Connecting';
      case ConnectionStatus.connected:
        return 'Connected';
      case ConnectionStatus.error:
        return 'Error';
    }
  }

  Color _statusColor(ConnectionStatus status) {
    switch (status) {
      case ConnectionStatus.disconnected:
        return Colors.grey;
      case ConnectionStatus.connecting:
        return Colors.orange;
      case ConnectionStatus.connected:
        return Colors.green;
      case ConnectionStatus.error:
        return Colors.red;
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.appState;
    final connected =
        state.status == ConnectionStatus.connected ||
        state.status == ConnectionStatus.connecting;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Status: ${_statusLabel(state.status)}',
            style: TextStyle(
              color: _statusColor(state.status),
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _hostController,
            enabled: !connected,
            decoration: const InputDecoration(labelText: 'Host'),
          ),
          const SizedBox(height: 8),
          TextField(
            controller: _portController,
            enabled: !connected,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Port'),
          ),
          const SizedBox(height: 16),
          if (state.status == ConnectionStatus.connected ||
              state.status == ConnectionStatus.connecting)
            ElevatedButton(
              onPressed: () => state.disconnect(),
              child: const Text('Disconnect'),
            )
          else
            ElevatedButton(
              onPressed: () {
                final port = int.tryParse(_portController.text) ?? 8770;
                state.connect(_hostController.text, port);
              },
              child: const Text('Connect'),
            ),
          const SizedBox(height: 16),
          if (state.readyInfo != null)
            Text(
              'READY proto=${state.readyInfo!.proto} '
              'tool=${state.readyInfo!.tool} '
              'transport=${state.readyInfo!.transport}',
            ),
        ],
      ),
    );
  }
}
