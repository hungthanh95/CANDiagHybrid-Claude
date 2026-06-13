// FlexDiag operator client entry point (docs/03-TECHNICAL-DETAIL.md §7).
//
// Wires a single AppState (Option B / WsTransport by default) to HomeScreen.
// Screens depend only on AppState/DiagService/Transport -- this is the only
// place a concrete transport is selected.

import 'package:flutter/material.dart';

import 'state/app_state.dart';
import 'ui/home_screen.dart';

void main() {
  runApp(FlexDiagApp(appState: AppState()));
}

/// Root widget. [appState] defaults to a fresh [AppState] (Option B
/// [WsTransport]) in [main], but can be overridden for tests/demos.
class FlexDiagApp extends StatelessWidget {
  const FlexDiagApp({super.key, required this.appState});

  final AppState appState;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'FlexDiag',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: HomeScreen(appState: appState),
    );
  }
}
