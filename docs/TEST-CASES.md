# TEST CASES — FlexDiag Use-Case Catalog

The complete list of FlexDiag **use cases** and how each is exercised. This is
the manual/automated test plan: every row names the scenario, how to run it,
the expected result, the automated test that proves it, and the requirement it
satisfies.

> **Topology legend.** All cases below run on the **software loopback** (Mock
> ECU via `bridge --fake` / `FakeVectorCom`) — no Vector hardware. Real-tool
> verification (CANoe/CANalyzer + VN1610) is tracked separately in
> `docs/STATUS.md` §2; the §3 convention is *✅ = mock-loopback verified*.
>
> **Run the whole suite:** `pytest -q` (from the repo root, venv active).
> **Run the capability matrix only:** `python -m tests.cap_matrix`.

---

## How to read this catalog

| Column | Meaning |
|--------|---------|
| **ID** | Stable use-case id (`UC-<area>-<n>`). |
| **Use case** | The operator-visible scenario. |
| **Steps / how to run** | REPL command(s) or the test entry point. |
| **Expected** | The observable result. |
| **Automated test** | The `pytest` test (file::function) that asserts it. |
| **Req** | The requirement from `docs/02-SYSTEM-REQUIREMENTS.md`. |

---

## 1. Capability use cases (the v1 feature set)

End-to-end through the terminal → bridge → Mock ECU. Bundled `.flex` scripts
in `tests/flex/` drive these; `tests/test_flex_capabilities_b.py` runs them.

| ID | Use case | Steps / how to run | Expected | Automated test | Req |
|----|----------|--------------------|----------|----------------|-----|
| UC-CAP-1 | Read DTC by status mask | `readdtc FF` | `RSP 59 02 FF …`, decoded `P01234 (0x2F)`, `P05678 (0x08)` | `test_flex_capabilities_b.py::test_cap_readdtc_b` | FR-1/FR-2 |
| UC-CAP-2 | Clear DTC | `cleardtc` | `RSP 54` | `test_flex_capabilities_b.py::test_cap_clear_dtc_b` | FR-3 |
| UC-CAP-3 | Periodic Tester Present on/off | `tp on` then `tp off` | `OK TP` for both | `test_flex_capabilities_b.py::test_cap_tester_present_b` | FR-4 |
| UC-CAP-4 | Security Access full unlock | `sec 01` | `OK SEC 01` (seed→key in one action) | `test_flex_capabilities_b.py::test_cap_security_b` | FR-5 |
| UC-CAP-5 | Diagnostic Session Control | `session 03` | `RSP 50 03 00 32 01 F4` | `test_flex_capabilities_b.py::test_cap_session_b` | FR-6 |
| UC-CAP-6 | Capability pass/fail matrix | `python -m tests.cap_matrix` | All five capabilities `PASS` | `tests/cap_matrix.py` | FR-1,3,4,5,6 |
| UC-CAP-7 | Run a `.flex` script file | `python -m terminal script <f.flex>` | Exit `0` on pass, `1` on failure | runner: `terminal/script.py` (all `cap_*_b` above) | FR-19 |

> *Tester Present note:* the mock/terminal path verifies TP start/stop
> round-trips. The *periodic* `3E 80` emission is the Vector tool's job and is
> only fully verifiable on real hardware (`docs/STATUS.md` §2).

---

## 2. Mock-ECU behaviour (UDS responder semantics)

The Mock ECU is a pure UDS state machine (`mock_ecu/uds.py`). These cases pin
its responses so the offline loopback is meaningful. The responder collectively
satisfies **FR-20** (responds to `0x10`/`0x14`/`0x19 02`/`0x27`/`0x3E`).

| ID | Use case | Expected | Automated test | Req |
|----|----------|----------|----------------|-----|
| UC-MOCK-1 | Session control positive | `50 <sub> 00 32 01 F4` | `test_mock_uds.py::test_session_control_positive_response` | FR-6 |
| UC-MOCK-2 | Tester Present positive | `7E 00` | `test_mock_uds.py::test_tester_present_positive` | FR-4 |
| UC-MOCK-3 | Tester Present suppress-positive | no response when bit 0x80 set | `test_mock_uds.py::test_tester_present_suppress_positive` | FR-4 |
| UC-MOCK-4 | Read DTC default mask `FF` | both DTCs returned | `test_mock_uds.py::test_read_dtc_default_mask_ff` | FR-1 |
| UC-MOCK-5 | Read DTC mask `0F` | both DTCs pass filter | `test_mock_uds.py::test_read_dtc_mask_0f_both_pass` | FR-1 |
| UC-MOCK-6 | Read DTC mask `20` | only first DTC passes | `test_mock_uds.py::test_read_dtc_mask_20_only_first_passes` | FR-1 |
| UC-MOCK-7 | Read DTC mask `40` | no DTC passes (empty list) | `test_mock_uds.py::test_read_dtc_mask_40_neither_passes` | FR-1 |
| UC-MOCK-8 | Configurable DTC table | `dtcs` field drives `0x19 02` output | `test_mock_uds.py` (UC-MOCK-4..7) | FR-21 |
| UC-MOCK-9 | Clear DTC | `54` | `test_mock_uds.py::test_clear_dtc` | FR-3 |
| UC-MOCK-10 | Security seed request (odd level) | `67 <lvl> <SEED…>` | `test_mock_uds.py::test_security_seed_request` | FR-5/FR-22 |
| UC-MOCK-11 | Wrong key then correct key | `7F 27 35` then `67 <lvl>` (unlocked) | `test_mock_uds.py::test_security_wrong_key_then_correct_key` | FR-5/FR-22 |
| UC-MOCK-12 | Unknown SID | `7F <sid> 11` (serviceNotSupported) | `test_mock_uds.py::test_unknown_sid_returns_service_not_supported` | FR-5 |
| UC-MOCK-13 | Single-shot NRC injection (FR-23) | next request returns injected `7F <sid> <nrc>` once | `test_mock_uds.py::test_inject_next_nrc_consumed_once` | FR-23 |

---

## 3. Negative / error-path use cases

What happens when things go wrong — these are first-class use cases, not
afterthoughts. Driven through the bridge (`tests/test_bridge_negatives.py`).

| ID | Use case | Expected | Automated test | Req |
|----|----------|----------|----------------|-----|
| UC-NEG-1 | Response-pending then final (`0x78`) | `7F … 78` emitted, then real response delivered | `test_bridge_negatives.py::test_pending_0x78_then_final` | FR-23 |
| UC-NEG-2 | Security invalid key (`0x35`) | `NRC 27 35 (invalidKey)` | `test_bridge_negatives.py::test_security_invalid_key_via_injected_nrc` | FR-5/FR-23 |
| UC-NEG-3 | Security access denied (`0x33`) | `NRC 27 33 (securityAccessDenied)` | `test_bridge_negatives.py::test_security_access_denied_via_injected_nrc` | FR-5/FR-23 |
| UC-NEG-4 | Transport drop mid-request | in-flight request fails immediately | `test_bridge_negatives.py::test_transport_drop_mid_request` | FR-16 |
| UC-NEG-5 | Graceful `BYE` close | server closes cleanly, no error | `test_bridge_negatives.py::test_bye_clean_close` | FR-18 |

### 3a. Malformed-input / argument-validation cases (`test_bridge_unit.py`)

All rows below satisfy **NFR-5** (a malformed client line yields a protocol
error response — never a crash of the bridge or CAPL node).

| ID | Use case | Expected | Automated test |
|----|----------|----------|----------------|
| UC-NEG-6 | Unknown verb | `ERR 400` | `test_unknown_verb_err_400` |
| UC-NEG-7 | Single garbage token | `ERR` bad args | `test_malformed_single_token_bad_args` |
| UC-NEG-8 | Multi-token garbage | unknown verb error | `test_multi_token_garbage_is_unknown_verb` |
| UC-NEG-9 | `raw` with bad hex | bad-args error | `test_raw_bad_hex_is_bad_args` |
| UC-NEG-10 | `raw` with no data | bad-args error | `test_raw_no_data_is_bad_args` |
| UC-NEG-11 | `session` out of range | bad-args error | `test_session_out_of_range_is_bad_args` |
| UC-NEG-12 | `readdtc` bad mask | bad-args error | `test_readdtc_bad_mask_is_bad_args` |
| UC-NEG-13 | `readdtc` too many args | bad-args error | `test_readdtc_too_many_args_is_bad_args` |
| UC-NEG-14 | `cleardtc` with args | bad-args error | `test_cleardtc_with_args_is_bad_args` |
| UC-NEG-15 | `security` bad level | bad-args error | `test_security_bad_level_is_bad_args` |
| UC-NEG-16 | `tp` bad argument | bad-args error | `test_tp_bad_arg_is_bad_args` |

---

## 4. Bridge request/response use cases (`test_bridge_unit.py`)

Proves the bridge produces the correct **raw UDS request bytes** for each verb
and encodes responses correctly — the contract between protocol and ECU.

| ID | Use case | Expected | Automated test | Req |
|----|----------|----------|----------------|-----|
| UC-BR-1 | `raw` → exact wire bytes | request bytes == hex sent | `test_raw_request_bytes_match_wire_hex` | FR-24/NFR-4 |
| UC-BR-2 | `readdtc` → `19 02 <mask>` | correct request framing | `test_readdtc_request_bytes_are_19_02_mask` | FR-1 |
| UC-BR-3 | `cleardtc` → `14 FF FF FF` | correct request framing | `test_cleardtc_request_bytes_are_14_ff_ff_ff` | FR-3 |
| UC-BR-4 | `session` → `10 <sub>` | correct request framing | `test_session_request_bytes_are_10_sub` | FR-6 |
| UC-BR-5 | Dispatch each verb | correct positive response | `test_dispatch_{raw,readdtc,cleardtc,session,security_full_unlock,tp_start,tp_stop}` | FR-1,3,5,6 |
| UC-BR-6 | Encode positive `RSP` | `RSP <bytes>` line | `test_encode_response_positive_rsp` | FR-24 |
| UC-BR-7 | Encode `NRC` | `NRC <sid> <code>` (short data → 0) | `test_encode_response_negative_nrc*` | FR-24 |
| UC-BR-8 | Encode `OK TP` / `OK SEC` | correct ack + derived odd level | `test_encode_response_ok_tp_*`, `test_encode_response_ok_sec_*` | FR-4/FR-5 |
| UC-BR-9 | Encode `ERR` (keygen/timeout) | `ERR <code> <text>` | `test_encode_response_err_*` | FR-24 |
| UC-BR-10 | `--fake` loopback mode | `FakeVectorCom`→Mock ECU serves all verbs | this whole file + `test_flex_capabilities_b.py` | FR-24 |

---

## 5. Protocol codec use cases

Pure parser/encoder tests — no transport. One protocol parser per language
(`protocol/`).

### 5a. Wire codec (`test_protocol_wire.py`)

| ID | Use case | Automated test |
|----|----------|----------------|
| UC-WIRE-1 | Hex ↔ bytes round-trip (case, whitespace, empty) | `test_hex_to_bytes_*`, `test_bytes_to_hex_basic` |
| UC-WIRE-2 | Reject bad hex (odd length, non-hex, `0x` prefix) | `test_hex_to_bytes_*_raises` |
| UC-WIRE-3 | Command round-trip (HELLO/SESSION/READDTC/CLEARDTC/SECURITY/TP/RAW/PING/BYE) | `test_command_round_trip_*` |
| UC-WIRE-4 | Response round-trip (READY/RSP/NRC/OK-TP/OK-SEC/ERR/EVT/PONG) | `test_response_round_trip_*` |
| UC-WIRE-5 | Reject malformed lines (empty, non-numeric seq, over-length) | `test_parse_*_raises`, `test_*_line_too_long_raises` |
| UC-WIRE-6 | Reject wrong-direction verb (client verb in response, server verb in command) | `test_parse_response_client_verb_rejected`, `test_parse_command_server_verb_rejected` |
| UC-WIRE-7 | Seq allocator starts at 1 and increments | `test_seq_allocator_starts_at_one_and_increments` |

### 5b. DTC decode (`test_protocol_dtc.py`)

| ID | Use case | Automated test |
|----|----------|----------------|
| UC-DTC-1 | Letter prefix decode (P/C/B/U) | `test_decode_dtc_letter_{p,c,b,u}` |
| UC-DTC-2 | Canonical decode (`00 12 34`→`P01234`, `00 56 78`→`P05678`) | `test_decode_dtc_canonical_example`, `_second_canonical_example` |
| UC-DTC-3 | Parse `19 02` payload (canonical, empty list, max length) | `test_parse_read_dtc_payload_{canonical,empty_dtc_list,max_length}` |
| UC-DTC-4 | Reject malformed payload (truncated, wrong leading byte, bad length) | `test_parse_read_dtc_payload_{truncated*,wrong_leading_byte,wrong_length_*}` |

### 5c. NRC names (`test_protocol_nrc.py`)

| ID | Use case | Automated test |
|----|----------|----------------|
| UC-NRC-1 | Known NRC → name (invalidKey/responsePending/securityAccessDenied) | `test_nrc_name_*` |
| UC-NRC-2 | Unknown NRC → `unknown_XX` | `test_nrc_name_unknown_returns_unknown_xx` |

---

## 6. Terminal reliability use cases (`test_terminal_reconnect.py`)

| ID | Use case | Expected | Automated test | Req |
|----|----------|----------|----------------|-----|
| UC-REL-1 | In-flight request fails immediately on drop | no waiting for timeout | `test_inflight_request_fails_immediately_on_drop` | FR-16 |
| UC-REL-2 | Bounded reconnect recovers | session resumes transparently | `test_bounded_reconnect_recovers` | FR-16 |
| UC-REL-3 | Bounded reconnect exhausts cleanly | ends disconnected, no hang/crash | `test_bounded_reconnect_exhausts_cleanly` | FR-16 |
| UC-REL-4 | Per-request timeout (no response) | raises transport error after timeout | `test_per_request_timeout_no_response` | FR-16 |

---

## 7. Manual / human-gated use cases (NOT automated)

These require hardware or a display and are verified by the operator — see
`docs/RUNBOOK.md` §4. They are **not** covered by `pytest` and remain ⬜ in
`docs/STATUS.md` §2 until run.

| ID | Use case | How to verify | Req |
|----|----------|---------------|-----|
| UC-MAN-1 | All capabilities live on **CANoe** | Run §1 commands with `bridge` (no `--fake`) against CANoe + VN1610 | NFR-1 |
| UC-MAN-2 | All capabilities live on **CANalyzer** | Same, against CANalyzer | NFR-1 |
| UC-MAN-3 | Real seed-key unlock | Attach DLL (matched bitness), `sec <lvl>` against real ECU | FR-5 |
| UC-MAN-4 | Periodic `3E 80` on the bus | `tp on`, observe trace; `tp off`, observe it stops | FR-4 |
| UC-MAN-5 | Auto-detect / channel bring-up | Follow `docs/05` §4 on a fresh machine | FR-15 |
| UC-MAN-6 | Flutter UI parity | `flutter run`, drive each capability from the UI | FR-17 |
| UC-MAN-7 | Latency / throughput | Measure on real bus (deferred — no test this pass) | NFR-3/NFR-9 |

---

## 8. Coverage summary

| Area | Use cases | Automated? |
|------|-----------|------------|
| Capabilities (§1) | 7 | ✅ pytest + cap_matrix |
| Mock-ECU semantics (§2) | 13 | ✅ pytest |
| Negative / error paths (§3) | 16 | ✅ pytest |
| Bridge request/response (§4) | 10 | ✅ pytest |
| Protocol codecs (§5) | ~17 | ✅ pytest |
| Terminal reliability (§6) | 4 | ✅ pytest |
| Manual / hardware (§7) | 7 | ⬜ human-gated |

> The automated rows above correspond to the green `pytest -q` suite. Keep this
> catalog in sync when tests are added or use cases change; `docs/STATUS.md` §3
> tracks requirement-level coverage and is the source of truth for status.
