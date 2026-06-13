// Tester present screen (docs/03-TECHNICAL-DETAIL.md §7): on/off toggle for
// periodic `TP START`/`TP STOP`, resolves on `OK TP`.
//
// Depends only on AppState.

import 'package:flutter/material.dart';

import '../state/app_state.dart';

/// Tester present on/off toggle screen.
class TesterPresentScreen extends StatelessWidget {
  const TesterPresentScreen({super.key, required this.appState});

  final AppState appState;

  @override
  Widget build(BuildContext context) {
    final connected = appState.status == ConnectionStatus.connected;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Switch(
                value: appState.tpEnabled,
                onChanged: connected
                    ? (value) => appState.setTesterPresent(value)
                    : null,
              ),
              const SizedBox(width: 8),
              Text(
                appState.tpEnabled
                    ? 'Tester present: ON'
                    : 'Tester present: OFF',
              ),
            ],
          ),
          const SizedBox(height: 16),
          if (appState.log.any((e) => e.text.contains('OK TP')))
            const Text('OK TP'),
        ],
      ),
    );
  }
}
