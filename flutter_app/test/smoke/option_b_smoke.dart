// Manual smoke script (NOT part of `dart test`): drives DiagService over
// WsTransport against a live `python -m bridge --fake` (Option B, Mock ECU
// software loopback). Run with:
//
//   python3 -m bridge --fake --port 18770 &
//   dart run test/smoke/option_b_smoke.dart
//
// Exercises one request per capability and prints the raw bytes sent vs.
// the decoded result, for NFR-4 byte-accuracy spot-checking.

import 'package:flexdiag_app/services/diag_service.dart';
import 'package:flexdiag_app/transport/ws_transport.dart';

Future<void> main() async {
  final transport = WsTransport(host: '127.0.0.1', port: 18770);
  await transport.connect();
  final service = DiagService(transport);
  service.start();

  // Drain the unsolicited READY banner.
  final bannerSub = transport.lines.listen((line) {
    if (line.startsWith('0 ')) print('banner: $line');
  });
  await Future<void>.delayed(const Duration(milliseconds: 100));
  await bannerSub.cancel();

  print('--- SESSION 03 ---');
  print(await service.session(0x03));

  print('--- READDTC FF ---');
  final dtc = await service.readDtc();
  print(
      'mask=${dtc.availabilityMask} dtcs=${dtc.dtcs.map((d) => '${d.code}/${d.status}')}');

  print('--- SECURITY 01 ---');
  print(await service.securityUnlock(0x01));

  print('--- TP START / STOP ---');
  await service.testerPresent(true);
  await service.testerPresent(false);
  print('ok');

  print('--- CLEARDTC ---');
  print(await service.clearDtc());

  print('--- RAW 22 F1 90 ---');
  try {
    print(await service.raw(<int>[0x22, 0xF1, 0x90]));
  } on NrcException catch (e) {
    print('NRC: $e');
  }

  print('--- PING ---');
  await service.ping();
  print('pong ok');

  await service.dispose();
  await transport.dispose();
}
