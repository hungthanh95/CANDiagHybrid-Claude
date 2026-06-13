// Security screen (docs/03-TECHNICAL-DETAIL.md §7): a single seed/key
// unlock action for a chosen odd level, showing `OK SEC <level>`,
// `NRC <sid> <nrc>` (e.g. `NRC 27 35` invalidKey), or `ERR <code> <text>`
// (e.g. tool-side `ERR 500 keygen_fail`) -- "NRC ≠ ERR" (CLAUDE.md rule):
// these are rendered with distinct labels/colors, never collapsed into one
// generic "error".
//
// Depends only on AppState. Never auto-triggers -- the operator explicitly
// taps Unlock (RUNBOOK §4 human-gate for any `0x27` run against a real ECU).

import 'package:flutter/material.dart';

import '../codec/nrc.dart';
import '../state/app_state.dart';

/// Security access screen: single unlock action for a chosen odd level.
class SecurityScreen extends StatefulWidget {
  const SecurityScreen({super.key, required this.appState});

  final AppState appState;

  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  // Default: 01, a common first (odd/request) security level.
  final TextEditingController _levelController = TextEditingController(
    text: '01',
  );

  @override
  void dispose() {
    _levelController.dispose();
    super.dispose();
  }

  String _hex2(int v) => v.toRadixString(16).toUpperCase().padLeft(2, '0');

  @override
  Widget build(BuildContext context) {
    final state = widget.appState;
    final connected = state.status == ConnectionStatus.connected;
    final result = state.lastSecurityResult;

    Widget? resultWidget;
    if (result is SecuritySuccess) {
      resultWidget = Text(
        'OK SEC ${_hex2(result.level)}',
        style: const TextStyle(
          color: Colors.green,
          fontWeight: FontWeight.bold,
        ),
      );
    } else if (result is SecurityNrc) {
      final name = nrcName(result.nrc);
      resultWidget = Text(
        'NRC ${_hex2(result.sid)} ${_hex2(result.nrc)} ($name)',
        style: const TextStyle(
          color: Colors.orange,
          fontWeight: FontWeight.bold,
        ),
      );
    } else if (result is SecurityErr) {
      resultWidget = Text(
        'ERR ${result.code} ${result.text}',
        style: const TextStyle(color: Colors.red, fontWeight: FontWeight.bold),
      );
    }

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          TextField(
            controller: _levelController,
            decoration: const InputDecoration(
              labelText: 'Security level (hex, odd, e.g. 01)',
            ),
          ),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: connected
                ? () {
                    final level = int.tryParse(
                      _levelController.text,
                      radix: 16,
                    );
                    if (level == null) return;
                    state.securityUnlock(level);
                  }
                : null,
            child: const Text('Unlock'),
          ),
          const SizedBox(height: 16),
          ?resultWidget,
        ],
      ),
    );
  }
}
