// Clear DTC screen (docs/03-TECHNICAL-DETAIL.md §7): single `CLEARDTC`
// button, show result (`RSP` bytes, or `NRC`/`ERR` rendered distinctly).
//
// Depends only on AppState.

import 'package:flutter/material.dart';

import '../protocol/codec.dart';
import '../state/app_state.dart';
import '../state/log_entry.dart';

/// Clear DTC screen.
class ClearDtcScreen extends StatelessWidget {
  const ClearDtcScreen({super.key, required this.appState});

  final AppState appState;

  /// The most recent NRC/ERR log entry since the last `CLEARDTC` request, if
  /// any.
  LogEntry? _lastNegative() {
    for (final entry in appState.log.reversed) {
      if (entry.direction == LogDirection.nrc ||
          entry.direction == LogDirection.err) {
        return entry;
      }
      if (entry.direction == LogDirection.sent) {
        return null;
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final connected = appState.status == ConnectionStatus.connected;
    final negative = _lastNegative();

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ElevatedButton(
            onPressed: connected ? () => appState.clearDtc() : null,
            child: const Text('Clear DTCs'),
          ),
          const SizedBox(height: 16),
          if (appState.lastClearDtcResult != null)
            Text('RSP ${bytesToHex(appState.lastClearDtcResult!)}'),
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
