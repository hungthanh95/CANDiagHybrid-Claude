// Shared widget-test helper: wraps a screen in a MaterialApp/Scaffold with
// a ListenableBuilder rebuilding on AppState changes
// (docs/03-TECHNICAL-DETAIL.md §7).

import 'package:flexdiag_app/state/app_state.dart';
import 'package:flutter/material.dart';

/// Wraps [builder]'s result in `MaterialApp(home: Scaffold(body: ...))`,
/// rebuilding whenever [state] notifies.
Widget wrapScreen(AppState state, Widget Function(BuildContext) builder) {
  return MaterialApp(
    home: Scaffold(
      body: ListenableBuilder(
        listenable: state,
        builder: (context, _) => builder(context),
      ),
    ),
  );
}
