# TauSync Integration Test Guide

## Overview

This suite validates the TauSync protocol end-to-end between a Windows PC
(Python server) and an Android device (Java client). The PC is the server;
the Android app connects and drives **21 automated tests** plus an
interactive **manual mode**.

The two halves are paired by **meeting word** (the channel name). Each test on
the Android side has a matching handler on the PC side using the same word, so
the two files stay in lock-step:

| Side | File |
|------|------|
| PC (server) | `TauSync\windows\tau_sync_tests\tests\cursor_test\android_test_server.py` |
| Android (client) | `android/app/src/main/java/com/example/android/testing/TestTauSyncActivity.java` |

---

## PC Side — Start the Test Console (GUI)

Run from the project root:

```
python TauSync\windows\tau_sync_tests\tests\cursor_test\android_test_server.py
```

A **GUI window** opens ("TauSync PC Test Console") — no command-line needed. It
is the TauSync **server**. The status line shows `Waiting for Android client to
connect…`; once the Android app connects it:

- **arms all 18 automated test channels** in the background (one thread each),
  so the phone's **Run All Tests** works immediately, and
- **enables the manual playground** — open as many channels as you like.

Re-tap **Run All Tests** on the phone after pressing **Re-arm Automated Tests**
on the console to run the whole suite again.

---

## Android Side — Run the Test Activity

### Option A: Android Studio (recommended)

1. Open the project in Android Studio.
2. Open `TestTauSyncActivity.java`.
3. Right-click anywhere in the editor → **Run 'TestTauSyncActivity'**.
4. Select your device or emulator in the device dropdown and confirm.

### Option B: Edit Run Configuration

1. Click the run configuration dropdown (top toolbar) → **Edit Configurations**.
2. Click **+** → **Android App**.
3. Set the module to `app`.
4. Under **Launch**, choose **Specified Activity** and enter:
   `com.example.android.testing.TestTauSyncActivity`
5. Save and click **Run**.

---

## Connecting the Two Sides

1. Make sure the PC and Android device are on the **same Wi-Fi network**.
2. The PC server prints its IP, or find it with `ipconfig` (Wi-Fi adapter).
3. In the Android app, enter the PC's IP address in the **Server IP** field.
4. Tap **Connect**.

---

## Hybrid (Bluetooth) Mode — Pairing over Bluetooth (Phase 4)

Hybrid mode connects over **Bluetooth** first (always-on link for control + small payloads) and
brings **Wi-Fi** up lazily only for large payloads. The Wi-Fi IP is discovered over Bluetooth, so you
never type it. Phase 4 also removes the need to type the PC's Bluetooth MAC — the phone finds the PC
through the OS pairing chooser.

### PC side
1. Start the test console and click **"Hybrid (Bluetooth) Server"** (mutually exclusive with
   "Wi-Fi Server" — the transport is a process-wide singleton).
2. Selecting this mode automatically starts a **BLE beacon** advertising the TauSync service UUID, so a
   first-time phone can discover this PC. Advertising stops once the phone connects. (No-op on PCs
   whose Bluetooth radio lacks BLE peripheral support — see the fallback below.)

### Android side — first launch (no saved device)
1. Leave the **Bluetooth MAC** field **blank**.
2. Tap **"Connect (Hybrid BT)"**. The OS-native chooser appears showing **only the TauSync PC**
   (filtered by the service UUID), not every nearby Bluetooth device.
3. Tap the PC → confirm the system pairing prompt. The app **bonds** the device, **saves** its MAC,
   then connects. The discovered Wi-Fi IP auto-fills the IP field.

### Android side — later launches
- The saved device is reused automatically — **no chooser appears**. Just tap **"Connect (Hybrid BT)"**.

### Bond lost / re-pairing
- If you unpair the PC from Android's system Bluetooth settings, the next connect detects the missing
  bond, clears the saved address, and **re-opens the chooser automatically** so you can re-pair.

### Manual override / fallback
- Type the PC's Bluetooth MAC (`AA:BB:CC:DD:EE:FF`) into the field to **skip discovery** and connect
  directly. This is the fallback when the PC's radio has no BLE peripheral support (the chooser would
  show nothing), or for explicit control.

### Running the hybrid tests
Once connected, tap **"Run Hybrid Tests (Phase 3)"** to run the H1–H7 suite over the paired link
(BLE pairing is the precondition for this run). H6 is slow (~65 s); H7 is semi-manual (disrupt
Bluetooth during the announced 30 s drop window).

---

## Running the Automated Tests

Tap **Run All Tests**. The app runs all 21 tests sequentially and logs
`PASS`/`FAIL` with timing for each in the **Log** section at the bottom.

When the run finishes, a single **clear banner** appears above the log:

- **`✔ ALL 21 TESTS PASSED`** in green — everything is fine, or
- **`✘ 18 / 21 PASSED — FAILED: Test 5, Test 12, …`** in red — listing exactly
  which tests failed so you can scroll the log to those entries.

This banner is the at-a-glance regression gate: green means a code change broke
nothing; red names what to investigate.

### Group A — Core data I/O
| # | Channel | What it verifies |
|---|---------|-----------------|
| 1 | `test_msg` | Line-delimited text echo round-trip (UTF-8) |
| 2 | `test_bin` | 25 KB binary round-trip with SHA-256 integrity check |
| 3 | `test_empty_msg` | Empty `\n` line echo — zero-length payload handling |
| 4 | `test_unicode` | Multi-byte UTF-8 round-trip (Hebrew + Chinese + emoji) |
| 5 | `test_large_bin` | 1 MB binary round-trip with SHA-256 integrity check |

### Group B — Stream control
| # | Channel | What it verifies |
|---|---------|-----------------|
| 6 | `test_burst` | 100 rapid sequential lines — no frame loss under burst |
| 7 | `test_concurrent_a/b` | Two channels open at once on one socket, no cross-talk |
| 8 | `test_stream_close` | Server sends then closes — client detects EOF via `readAll()` |

### Group C — Bidirectionality & multiplexing
| # | Channel | What it verifies |
|---|---------|-----------------|
| 9 | `test_bidir` | Both sides read AND write 50 messages at once — true full-duplex |
| 10 | `test_multi_a/b` | Two `TauSync` managers (`newManager()`) multiplexed on one socket |

### Group D — Channel lifecycle
| # | Channel | What it verifies |
|---|---------|-----------------|
| 11 | `test_reuse` | Open → close → reopen same word — ID recycling & re-registration |
| 12 | `test_pw_alpha/beta` | `getPeerWaitingWords()` reports the peer's pending discovery REQs |

### Group E — Data edge cases
| # | Channel | What it verifies |
|---|---------|-----------------|
| 13 | `test_long_line` | 500 KB single line — `readLine()` buffer growth under the 1 MB cap |
| 14 | `test_small_frames` | 200 KB sent in 100-byte frames — fragment reassembly integrity |
| 15 | `test_raw_stream` | `getInputStream()`/`getOutputStream()` raw `java.io` adapters |

### Group F — File transfer
| # | Channel | What it verifies |
|---|---------|-----------------|
| 16 | `test_file_pc_to_android` | 20 MB file PC→Android via `write_file`/`readToFile`, SHA-256 |
| 17 | `test_file_android_to_pc` | 20 MB file Android→PC via `writeFile`/`read_to_file`, SHA-256 |

### Group G — Failure & recovery
| # | Channel | What it verifies |
|---|---------|-----------------|
| 18 | `test_peer_close` | Server closes before sending — client `readLine()` returns `null` (EOF) |

### Group H — Bugfix validation
| # | Channel | What it verifies |
|---|---------|-----------------|
| 19 | `test_large_write` | PC sends 5 MB in **one** `write()` call — auto-chunking splits into ≤64 KB frames, SHA-256 verified end-to-end |
| 20 | `test_cid_00`…`test_cid_09` | 10 channels opened simultaneously — each receives its own unique payload with no cross-talk (ID reservation race fix) |
| 21 | `test_conc_close` + `test_conc_close_verify` | Both sides close a channel at the same time — the next channel on the same socket still works (close TOCTOU fix) |

> **Note on Test 12 (timing-sensitive):** the PC polls `get_peer_waiting_words()`
> for up to 45 s while the Android side holds two pending `connect()` calls open.
> It is the one test whose result depends on timing; if the device is very slow
> to reach it, give it a re-run on its own.

---

## Manual Testing (both sides, multi-channel)

The manual playground is now **symmetric** — whatever you can do on the phone
you can do on the PC console — and supports **multiple channels at once**.

A manual channel is just a meeting word that **both sides open**. Once paired it
is a **live two-way chat**: each side auto-reads and displays whatever the other
sends. Push your own data with **Send** or **Spam ×N**. Open as many words as you
want — each becomes its own card (phone) / tab (PC).

### On the phone
1. Enter a meeting word (default: `main`) and tap **Open Channel** — a card
   appears for it. Repeat with other words to open several channels.
2. Each card has its own **incoming feed**, **Send**, **Spam** (with count), and
   **Close**. Incoming lines from the PC appear live as `peer: …`.

### On the PC console
1. Type a word in **Manual channel word** and click **Open Channel** — a tab
   opens for it.
2. Each tab has a live feed, **Send**, **Spam ×N**, **Close Channel**, and an
   **Echo back received** checkbox (on by default). With echo on, the PC bounces
   every received line straight back — so the phone's send-then-see and spam
   round-trips work with zero PC interaction. Turn echo off for free-form chat.

### Test it as hard as you want
- Open the **same word** on both sides, then spam from phone *and* PC at once to
  stress full-duplex throughput.
- Open **many different words** simultaneously to exercise multiplexing by hand.
- Paste huge / Unicode / binary-ish messages into the message box to probe edge
  cases interactively, outside the fixed automated payloads.

---

## How to Add Your Own Test

The suite is designed to grow. To add a case:

1. **Pick a unique meeting word**, e.g. `test_myfeature`.
2. **PC side** (`android_test_server.py`): add a `serve_my_feature(tau)`
   function that opens the channel with `tau.connect("test_myfeature")`,
   exercises whatever you want, and (optionally) ends with a `send_verdict()`
   line. Register it in `serve_all_tests()` with a `run_test_on_thread(...)`.
3. **Android side** (`TestTauSyncActivity.java`): add a `runMyFeatureTest()`
   method following the same structure as the others (connect → exercise →
   verdict → close) and call it from `onRunAllTestsButtonClicked()`.

Handler order does not matter — each PC handler blocks in `connect()` until the
Android side opens the same word, so only the **words** need to match.

Both source files carry the same catalogue and these instructions in their
header comments, so they are discoverable from the code itself.
