// Session control screen (docs/03-TECHNICAL-DETAIL.md §7): send
// `SESSION <hex>`, show the `RSP` (or `NRC`/`ERR`, rendered distinctly).
//
// Depends only on AppState.

import 'package:flutter/material.dart';

import '../protocol/codec.dart';
import '../state/app_state.dart';
import '../state/log_entry.dart';

/// Diagnostic session control screen.
class SessionScreen extends StatefulWidget {
  const SessionScreen({super.key, required this.appState});

  final AppState appState;

  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> {
  // Default: 03 = extended diagnostic session (a common first step).
  final TextEditingController _sessionController = TextEditingController(
    text: '03',
  );

  @override
  void dispose() {
    _sessionController.dispose();
    super.dispose();
  }

  /// The most recent NRC/ERR log entry, if any -- shown alongside
  /// [AppState.lastSessionResult] so a negative response is visible too.
  LogEntry? _lastNegative(AppState state) {
    for (final entry in state.log.reversed) {
      if (entry.direction == LogDirection.nrc ||
          entry.direction == LogDirection.err) {
        return entry;
      }
      if (entry.direction == LogDirection.sent) {
        // Stop at the most recent sent line -- don't show a stale
        // NRC/ERR from a previous request.
        return null;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.appState;
    final connected = state.status == ConnectionStatus.connected;
    final negative = _lastNegative(state);

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _sessionController,
            decoration: const InputDecoration(
              labelText: 'Session id (hex, e.g. 03)',
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: connected
                ? () {
                    final id = int.tryParse(_sessionController.text, radix: 16);
                    if (id == null) return;
                    state.session(id);
                  }
                : null,
            child: const Text('Send'),
          ),
          const SizedBox(height: 16),
          if (state.lastSessionResult != null)
            Text('RSP ${bytesToHex(state.lastSessionResult!)}'),
          if (negative != null)
            Text(
              negative.text,
              style: TextStyle(
                color: negative.direction == LogDirection.nrc
                    ? Colors.orange
                    : Colors.red,
                fontWeight: FontWeight.bold,
              ),
            ),
        ],
      ),
    );
  }
}
