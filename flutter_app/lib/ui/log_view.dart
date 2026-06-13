// Log view (docs/03-TECHNICAL-DETAIL.md §7): running list of sent/received
// protocol lines and status messages. NRC (`NRC <sid> <nrc>`, ECU negative
// response) and ERR (`ERR <code> <text>`, protocol/tool error) entries are
// styled distinctly -- "NRC ≠ ERR" (CLAUDE.md rule) -- not collapsed into one
// generic "error" style.
//
// Depends only on AppState.

import 'package:flutter/material.dart';

import '../state/app_state.dart';
import '../state/log_entry.dart';

/// Running log of protocol lines and status messages.
class LogView extends StatelessWidget {
  const LogView({super.key, required this.appState});

  final AppState appState;

  Color? _color(LogDirection direction) {
    switch (direction) {
      case LogDirection.sent:
        return Colors.blue;
      case LogDirection.recv:
        return Colors.black;
      case LogDirection.info:
        return Colors.grey;
      case LogDirection.nrc:
        return Colors.orange;
      case LogDirection.err:
        return Colors.red;
    }
  }

  String _prefix(LogDirection direction) {
    switch (direction) {
      case LogDirection.sent:
        return '> ';
      case LogDirection.recv:
        return '< ';
      case LogDirection.info:
        return '* ';
      case LogDirection.nrc:
        return '! ';
      case LogDirection.err:
        return '! ';
    }
  }

  @override
  Widget build(BuildContext context) {
    final entries = appState.log;

    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: entries.length,
      itemBuilder: (context, index) {
        final entry = entries[index];
        return Text(
          '${_prefix(entry.direction)}${entry.text}',
          style: TextStyle(
            color: _color(entry.direction),
            fontFamily: 'monospace',
          ),
        );
      },
    );
  }
}
