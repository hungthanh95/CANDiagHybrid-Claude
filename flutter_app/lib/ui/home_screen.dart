// Top-level navigation (docs/03-TECHNICAL-DETAIL.md §7): connect, session,
// read-DTC, clear-DTC, security, tester-present, and the log view.
//
// Wires AppState to each screen -- screens never construct WsTransport
// directly.

import 'package:flutter/material.dart';

import '../state/app_state.dart';
import 'clear_dtc_screen.dart';
import 'connect_screen.dart';
import 'log_view.dart';
import 'read_dtc_screen.dart';
import 'security_screen.dart';
import 'session_screen.dart';
import 'tester_present_screen.dart';

/// Top-level screen: bottom navigation between the FlexDiag screens.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.appState});

  final AppState appState;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _index = 0;

  @override
  Widget build(BuildContext context) {
    final state = widget.appState;

    return ListenableBuilder(
      listenable: state,
      builder: (context, _) {
        // Rebuilt on every AppState change, so each screen always sees the
        // latest state -- a stale cached widget instance would not rebuild
        // when only its constructor args' referenced object mutates.
        final screens = <Widget>[
          ConnectScreen(appState: state),
          SessionScreen(appState: state),
          ReadDtcScreen(appState: state),
          ClearDtcScreen(appState: state),
          SecurityScreen(appState: state),
          TesterPresentScreen(appState: state),
          LogView(appState: state),
        ];
        return Scaffold(
          appBar: AppBar(title: const Text('FlexDiag')),
          body: screens[_index],
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (index) => setState(() => _index = index),
            destinations: const [
              NavigationDestination(icon: Icon(Icons.link), label: 'Connect'),
              NavigationDestination(
                icon: Icon(Icons.play_arrow),
                label: 'Session',
              ),
              NavigationDestination(
                icon: Icon(Icons.warning),
                label: 'Read DTC',
              ),
              NavigationDestination(
                icon: Icon(Icons.cleaning_services),
                label: 'Clear DTC',
              ),
              NavigationDestination(icon: Icon(Icons.lock), label: 'Security'),
              NavigationDestination(
                icon: Icon(Icons.timer),
                label: 'Tester Present',
              ),
              NavigationDestination(icon: Icon(Icons.list), label: 'Log'),
            ],
          ),
        );
      },
    );
  }
}
