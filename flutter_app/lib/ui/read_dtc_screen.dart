// Read DTC screen (docs/03-TECHNICAL-DETAIL.md §7): `READDTC`, decoded DTC
// list (code + status flags via lib/codec/dtc.dart -- not raw bytes,
// "no CDD assumptions" rule still holds: decoding happens client-side).
//
// Depends only on AppState.

import 'package:flutter/material.dart';

import '../state/app_state.dart';

/// Read DTC screen: shows decoded DTC codes and status masks.
class ReadDtcScreen extends StatelessWidget {
  const ReadDtcScreen({super.key, required this.appState});

  final AppState appState;

  @override
  Widget build(BuildContext context) {
    final connected = appState.status == ConnectionStatus.connected;
    final result = appState.lastDtcResult;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ElevatedButton(
            onPressed: connected ? () => appState.readDtc() : null,
            child: const Text('Read DTCs'),
          ),
          const SizedBox(height: 16),
          if (result != null)
            Text('Availability mask: ${_hex2(result.availabilityMask)}'),
          const SizedBox(height: 8),
          if (result != null)
            Expanded(
              child: result.dtcs.isEmpty
                  ? const Text('No DTCs reported')
                  : ListView.builder(
                      itemCount: result.dtcs.length,
                      itemBuilder: (context, index) {
                        final dtc = result.dtcs[index];
                        return ListTile(
                          title: Text(dtc.code),
                          subtitle: Text('status: ${_hex2(dtc.status)}'),
                        );
                      },
                    ),
            ),
        ],
      ),
    );
  }
}

String _hex2(int v) => v.toRadixString(16).toUpperCase().padLeft(2, '0');
