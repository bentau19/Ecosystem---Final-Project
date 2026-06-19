package com.example.android.testing;

import android.content.Context;
import android.graphics.Typeface;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.text.InputType;
import android.text.TextUtils;
import android.text.format.Formatter;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.example.tausync_lib.implementations.management.TauSyncStream;
import com.example.tausync_lib.sdk.TauSync;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Manual + automated test bench for the TauSync protocol.
 *
 * <p>This activity is the Android (client) half of the test suite. The PC
 * (server) half is {@code android_test_server.py}. Each automated test is
 * paired with a server handler by its <b>meeting word</b> (channel name).
 *
 * <p><b>Manual Channels</b> let you open any number of meeting words at once;
 * each becomes a live two-way chat with the PC console (Send / Spam / live
 * incoming feed). <b>Run All Tests</b> runs the 18 automated tests and shows a
 * single clear PASS/FAIL banner at the top of the Automated Tests section.
 *
 * <pre>
 *   TEST CATALOGUE  (word → protocol feature)
 *   ─ Group A: core data I/O ────────────────────────────────────────
 *    1  test_msg                 line-delimited text echo
 *    2  test_bin                 25 KB binary round-trip, SHA-256
 *    3  test_empty_msg           empty-line echo (zero-length payload)
 *    4  test_unicode             multi-byte UTF-8 round-trip
 *    5  test_large_bin           1 MB binary round-trip, SHA-256
 *   ─ Group B: stream control ───────────────────────────────────────
 *    6  test_burst               100 rapid sequential lines
 *    7  test_concurrent_a/b      two channels at once, no cross-talk
 *    8  test_stream_close        server closes, client detects EOF
 *   ─ Group C: bidirectionality & multiplexing ──────────────────────
 *    9  test_bidir               read AND write simultaneously
 *    10 test_multi_a/b           two managers on one socket (newManager)
 *   ─ Group D: channel lifecycle ────────────────────────────────────
 *    11 test_reuse               open → close → reopen same word
 *    12 test_pw_alpha/beta       getPeerWaitingWords() discovery queue
 *   ─ Group E: data edge cases ──────────────────────────────────────
 *    13 test_long_line           500 KB single line (readLine growth)
 *    14 test_small_frames        200 KB in 100-byte frames (reassembly)
 *    15 test_raw_stream          getInputStream()/getOutputStream()
 *   ─ Group F: file transfer ────────────────────────────────────────
 *    16 test_file_pc_to_android  20 MB PC→Android, SHA-256
 *    17 test_file_android_to_pc  20 MB Android→PC, SHA-256
 *   ─ Group G: failure & recovery ───────────────────────────────────
 *    18 test_peer_close          server closes before sending; EOF
 *   ─ Group H: bugfix validation ────────────────────────────────────
 *    19 test_large_write         5 MB in one write() — auto-chunking splits into ≤64 KB frames
 *    20 test_cid_00…09           10 simultaneous channels — unique IDs, no cross-talk
 *    21 test_conc_close          both sides close at once; next channel still works
 * </pre>
 *
 * <h3>How to add your own test</h3>
 * <ol>
 *   <li>Pick a unique meeting word, e.g. {@code "test_myfeature"}.</li>
 *   <li>Add a {@code runMyFeatureTest()} method below following the same
 *       structure as the others (connect, exercise, {@code recordResult}, close).</li>
 *   <li>Call it from {@link #onRunAllTestsButtonClicked()}.</li>
 *   <li>Add the matching {@code serve_my_feature()} handler on the PC in
 *       {@code android_test_server.py} using the same word.</li>
 * </ol>
 */
public class TestTauSyncActivity extends AppCompatActivity {

    private static final int LONG_LINE_LENGTH = 500_000;
    private static final long ANDROID_FILE_SIZE = 20L * 1024 * 1024;
    private static final int LARGE_WRITE_SIZE = 5 * 1024 * 1024;  // 5 MB — sent by PC in one write()
    private static final int CONCURRENT_ID_COUNT = 10;             // simultaneous channels for ID-race test
    private static final int COLOR_PASS = 0xFF1B7F32;
    private static final int COLOR_FAIL = 0xFFC62828;
    private static final int COLOR_NEUTRAL = 0xFF555555;

    private TauSync tauSync;
    private final ExecutorService backgroundExecutor = Executors.newCachedThreadPool();
    private final Map<String, ManualChannel> manualChannels = new ConcurrentHashMap<>();
    private final Map<String, Boolean> testResults = new LinkedHashMap<>();

    private EditText ipAddressInput;
    private EditText meetingWordInput;
    private Button connectButton;
    private Button openChannelButton;
    private Button runAllTestsButton;
    private TextView statusLabel;
    private TextView summaryLabel;
    private LinearLayout manualChannelsContainer;
    private TextView logView;
    private ScrollView logScrollView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildLayout());
        setInitialControlState();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        backgroundExecutor.shutdownNow();
        closeAllManualChannels();
        disposeTauSyncQuietly();
    }

    // ── Layout ───────────────────────────────────────────────────────────

    private View buildLayout() {
        ScrollView root = new ScrollView(this);
        LinearLayout column = newVerticalColumn(16);

        addHeader(column);
        addConnectionSection(column);
        addManualTestSection(column);
        addAutomatedTestSection(column);
        addLogSection(column);

        root.addView(column);
        return root;
    }

    private void addHeader(LinearLayout parent) {
        TextView title = new TextView(this);
        title.setText("TauSync Test");
        title.setTextSize(24);

        TextView localIp = new TextView(this);
        localIp.setText("Local IP: " + resolveLocalIpAddress());
        localIp.setTextSize(12);

        parent.addView(title);
        parent.addView(localIp);
    }

    private void addConnectionSection(LinearLayout parent) {
        parent.addView(newSectionTitle("Connection"));

        ipAddressInput = newEditText("Server IP", "192.168.1.60");
        parent.addView(ipAddressInput);

        connectButton = new Button(this);
        connectButton.setText("Connect");
        connectButton.setOnClickListener(v -> onConnectButtonClicked());
        parent.addView(connectButton);

        statusLabel = new TextView(this);
        statusLabel.setText("Status: Disconnected");
        parent.addView(statusLabel);
    }

    private void addManualTestSection(LinearLayout parent) {
        parent.addView(newSectionTitle("Manual Channels"));

        TextView help = new TextView(this);
        help.setText("Open one or more channels by meeting word. Each is a live two-way "
                + "chat with the PC console. Open the same word on the PC to talk to it.");
        help.setTextSize(12);
        parent.addView(help);

        meetingWordInput = newEditText("Meeting Word", "main");
        parent.addView(meetingWordInput);

        openChannelButton = new Button(this);
        openChannelButton.setText("Open Channel");
        openChannelButton.setOnClickListener(v -> onOpenChannelButtonClicked());
        parent.addView(openChannelButton);

        manualChannelsContainer = new LinearLayout(this);
        manualChannelsContainer.setOrientation(LinearLayout.VERTICAL);
        parent.addView(manualChannelsContainer);
    }

    private void addAutomatedTestSection(LinearLayout parent) {
        parent.addView(newSectionTitle("Automated Tests"));

        runAllTestsButton = new Button(this);
        runAllTestsButton.setText("Run All Tests");
        runAllTestsButton.setOnClickListener(v -> onRunAllTestsButtonClicked());
        parent.addView(runAllTestsButton);

        summaryLabel = new TextView(this);
        summaryLabel.setTextSize(16);
        summaryLabel.setTypeface(Typeface.DEFAULT_BOLD);
        summaryLabel.setText("No run yet");
        summaryLabel.setTextColor(COLOR_NEUTRAL);
        summaryLabel.setPadding(0, dpToPixels(6), 0, dpToPixels(6));
        parent.addView(summaryLabel);
    }

    private void addLogSection(LinearLayout parent) {
        parent.addView(newSectionTitle("Log"));

        logScrollView = new ScrollView(this);
        logScrollView.setMinimumHeight(300);

        logView = new TextView(this);
        logView.setTextSize(11);
        logView.setTypeface(Typeface.MONOSPACE);
        logScrollView.addView(logView);

        parent.addView(logScrollView);
    }

    // ── Connection actions ────────────────────────────────────────────────

    private void onConnectButtonClicked() {
        if (tauSync != null) {
            disconnect();
        } else {
            connectToServer(ipAddressInput.getText().toString().trim());
        }
    }

    private void connectToServer(String serverIp) {
        updateStatus("Connecting...");
        appendLog("Connecting to " + serverIp + "...");
        setConnectingState();

        backgroundExecutor.execute(() -> {
            try {
                TauSync newTauSync = new TauSync();
                newTauSync.connectTo(serverIp);
                runOnUiThread(() -> {
                    tauSync = newTauSync;
                    updateStatus("Connected to " + serverIp);
                    appendLog("Connected!");
                    setConnectedState();
                });
            } catch (Exception exception) {
                String rootCauseMessage = extractRootCauseMessage(exception);
                runOnUiThread(() -> {
                    updateStatus("Failed: " + rootCauseMessage);
                    appendLog("Connection failed: " + rootCauseMessage);
                    setDisconnectedState();
                });
            }
        });
    }

    private void disconnect() {
        backgroundExecutor.execute(() -> {
            closeAllManualChannels();
            disposeTauSyncQuietly();
            runOnUiThread(() -> {
                tauSync = null;
                updateStatus("Disconnected");
                appendLog("Disconnected");
                setDisconnectedState();
            });
        });
    }

    // ── Manual channels ───────────────────────────────────────────────────

    private void onOpenChannelButtonClicked() {
        if (tauSync == null) return;
        String word = meetingWordInput.getText().toString().trim();
        if (word.isEmpty()) {
            appendLog("Enter a meeting word first");
            return;
        }
        if (manualChannels.containsKey(word)) {
            appendLog("Channel '" + word + "' is already open");
            return;
        }
        appendLog("Opening manual channel '" + word + "'...");

        backgroundExecutor.execute(() -> {
            try {
                TauSyncStream stream = tauSync.connect(word);
                runOnUiThread(() -> addManualChannel(word, stream));
            } catch (Exception exception) {
                String rootCauseMessage = extractRootCauseMessage(exception);
                runOnUiThread(() -> appendLog("Open channel failed: " + rootCauseMessage));
            }
        });
    }

    private void addManualChannel(String word, TauSyncStream stream) {
        LinearLayout card = newVerticalColumn(8);
        card.setBackgroundColor(0x11000000);

        TextView title = new TextView(this);
        title.setText("Channel: " + word + "  (ID=" + stream.getLocalId() + ")");
        title.setTypeface(Typeface.DEFAULT_BOLD);
        card.addView(title);

        TextView incomingView = new TextView(this);
        incomingView.setTextSize(11);
        incomingView.setTypeface(Typeface.MONOSPACE);
        ScrollView incomingScroll = new ScrollView(this);
        incomingScroll.addView(incomingView);
        card.addView(incomingScroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dpToPixels(120)));

        EditText messageInput = newEditText("Message", "Hello from Android!");
        card.addView(messageInput);

        EditText spamCountInput = newEditText("N", "50");
        spamCountInput.setInputType(InputType.TYPE_CLASS_NUMBER);

        Button sendButton = new Button(this);
        sendButton.setText("Send");
        Button spamButton = new Button(this);
        spamButton.setText("Spam");
        Button closeButton = new Button(this);
        closeButton.setText("Close");

        LinearLayout buttonRow = newHorizontalRow();
        buttonRow.addView(sendButton, newRowParams());
        buttonRow.addView(spamCountInput, newRowParams());
        buttonRow.addView(spamButton, newRowParams());
        buttonRow.addView(closeButton, newRowParams());
        card.addView(buttonRow);

        manualChannelsContainer.addView(card);

        ManualChannel channel = new ManualChannel(word, stream, incomingView, incomingScroll, card);
        manualChannels.put(word, channel);

        sendButton.setOnClickListener(v -> channel.send(messageInput.getText().toString()));
        spamButton.setOnClickListener(v -> channel.spam(
                parsePositiveInt(spamCountInput.getText().toString(), 50),
                messageInput.getText().toString()));
        closeButton.setOnClickListener(v -> closeManualChannel(channel));

        channel.startReader();
        appendLog("Manual channel '" + word + "' opened (ID=" + stream.getLocalId() + ")");
    }

    private void closeManualChannel(ManualChannel channel) {
        channel.closed = true;
        backgroundExecutor.execute(() -> {
            try {
                channel.stream.close();
            } catch (Exception ignored) {
            }
        });
        manualChannels.remove(channel.word);
        manualChannelsContainer.removeView(channel.card);
        appendLog("Manual channel '" + channel.word + "' closed");
    }

    private void closeAllManualChannels() {
        for (ManualChannel channel : manualChannels.values()) {
            channel.closed = true;
            try {
                channel.stream.close();
            } catch (Exception ignored) {
            }
        }
        manualChannels.clear();
        runOnUiThread(() -> manualChannelsContainer.removeAllViews());
    }

    /**
     * A single open manual channel: holds its stream and the views that show
     * incoming lines. An auto-reader thread continuously displays whatever the
     * PC sends, so the channel behaves like a live chat window.
     */
    private final class ManualChannel {
        /** Keep the incoming view bounded so append() stays cheap under heavy spam. */
        private static final int MAX_INCOMING_CHARS = 20_000;
        private static final int TRIM_TO_CHARS = 15_000;

        final String word;
        final TauSyncStream stream;
        final TextView incomingView;
        final ScrollView incomingScroll;
        final View card;
        volatile boolean closed;

        private final StringBuilder pendingIncoming = new StringBuilder();
        private boolean flushScheduled;

        ManualChannel(String word, TauSyncStream stream, TextView incomingView,
                      ScrollView incomingScroll, View card) {
            this.word = word;
            this.stream = stream;
            this.incomingView = incomingView;
            this.incomingScroll = incomingScroll;
            this.card = card;
        }

        void startReader() {
            backgroundExecutor.execute(() -> {
                try {
                    while (!closed) {
                        String line = stream.readLine();
                        if (line == null) break;
                        appendIncoming("peer: " + line);
                    }
                } catch (Exception exception) {
                    if (!closed) appendIncoming("[reader stopped: " + exception.getMessage() + "]");
                }
                appendIncoming("[channel closed]");
            });
        }

        void send(String message) {
            appendIncoming("me:   " + message);
            backgroundExecutor.execute(() -> {
                try {
                    stream.writeString(message + "\n");
                } catch (Exception exception) {
                    appendIncoming("[send error: " + exception.getMessage() + "]");
                }
            });
        }

        void spam(int count, String message) {
            appendIncoming("[spam: sending " + count + " lines of \"" + message + "\" + index]");
            backgroundExecutor.execute(() -> {
                long start = System.currentTimeMillis();
                try {
                    for (int i = 0; i < count; i++) {
                        stream.writeString(message + i + "\n");
                    }
                    long elapsed = System.currentTimeMillis() - start;
                    appendIncoming("[spam: sent " + count + " lines in " + elapsed + "ms]");
                } catch (Exception exception) {
                    appendIncoming("[spam error: " + exception.getMessage() + "]");
                }
            });
        }

        /**
         * Queues an incoming line and coalesces bursts: while a flush is already
         * pending, further lines pile into one batch instead of posting a UI update
         * (append + relayout + scroll) per line. Keeps the chat responsive under spam.
         */
        void appendIncoming(String text) {
            synchronized (pendingIncoming) {
                pendingIncoming.append(text).append('\n');
                if (flushScheduled) return;
                flushScheduled = true;
            }
            runOnUiThread(this::flushIncoming);
        }

        private void flushIncoming() {
            String batch;
            synchronized (pendingIncoming) {
                batch = pendingIncoming.toString();
                pendingIncoming.setLength(0);
                flushScheduled = false;
            }
            incomingView.append(batch);

            if (incomingView.length() > MAX_INCOMING_CHARS) {
                CharSequence text = incomingView.getText();
                incomingView.setText(text.subSequence(text.length() - TRIM_TO_CHARS, text.length()));
            }
            incomingScroll.post(() -> incomingScroll.fullScroll(View.FOCUS_DOWN));
        }
    }

    // ── Automated tests ──────────────────────────────────────────────────

    private void onRunAllTestsButtonClicked() {
        if (tauSync == null) return;
        runAllTestsButton.setEnabled(false);
        runAllTestsButton.setText("Running...");
        testResults.clear();
        summaryLabel.setText("Running...");
        summaryLabel.setTextColor(COLOR_NEUTRAL);

        backgroundExecutor.execute(() -> {
            runMessageEchoTest();
            runBinaryRoundTripTest(25_600, "test_bin", "2");
            runEmptyMessageTest();
            runUnicodeRoundTripTest();
            runBinaryRoundTripTest(1_048_576, "test_large_bin", "5");
            runRapidBurstTest();
            runConcurrentChannelsTest();
            runStreamCloseTest();
            runBidirectionalTest();
            runMultiManagerTest();
            runChannelReuseTest();
            runPeerWaitingWordsTest();
            runLongLineTest();
            runSmallFramesTest();
            runRawStreamTest();
            runFilePcToAndroidTest();
            runFileAndroidToPcTest();
            runPeerCloseTest();
            runLargeWriteTest();
            runConcurrentIdsTest();
            runConcurrentCloseTest();
            runOnUiThread(this::publishSummary);
        });
    }

    /** Records a test verdict for the final summary and logs it. */
    private void recordResult(String testId, boolean passed, long elapsedMs, String detail) {
        testResults.put(testId, passed);
        String suffix = (detail == null || detail.isEmpty()) ? "" : "  " + detail;
        appendLog("[" + testId + "] " + verdict(passed) + " (" + elapsedMs + "ms)" + suffix);
    }

    /** Shows the single clear PASS/FAIL banner once every test has run. */
    private void publishSummary() {
        int total = testResults.size();
        int passedCount = 0;
        List<String> failed = new ArrayList<>();
        for (Map.Entry<String, Boolean> entry : testResults.entrySet()) {
            if (entry.getValue()) {
                passedCount++;
            } else {
                failed.add(entry.getKey());
            }
        }

        boolean allPassed = total > 0 && passedCount == total;
        String summary = allPassed
                ? ("✔  ALL " + total + " TESTS PASSED")
                : ("✘  " + passedCount + " / " + total + " PASSED   —   FAILED: "
                        + TextUtils.join(", ", failed));

        summaryLabel.setText(summary);
        summaryLabel.setTextColor(allPassed ? COLOR_PASS : COLOR_FAIL);

        appendLog("========================================");
        appendLog(summary);
        appendLog("========================================");

        runAllTestsButton.setEnabled(true);
        runAllTestsButton.setText("Run All Tests");
    }

    // ── Test 1: Message echo ─────────────────────────────────────────────

    private void runMessageEchoTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 1] Message Echo: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_msg");
            String sentMessage = "Hello from Android";

            stream.writeString(sentMessage + "\n");
            String reply = stream.readLine();
            stream.close();

            boolean passed = sentMessage.equals(reply);
            recordResult("Test 1", passed, elapsed(startTime),
                    passed ? "" : "expected=" + sentMessage + " got=" + reply);
        } catch (Exception exception) {
            recordResult("Test 1", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 2 / 5: Binary round-trip (parameterized) ────────────────────

    private void runBinaryRoundTripTest(int expectedSize, String channelName, String testNumber) {
        long startTime = System.currentTimeMillis();
        appendLog("[Test " + testNumber + "] Binary (" + formatByteSize(expectedSize)
                + "): opening channel '" + channelName + "'...");

        try {
            TauSyncStream stream = tauSync.connect(channelName);

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size header");
            int dataSize = Integer.parseInt(sizeLine.trim());

            byte[] data = stream.readExactly(dataSize);
            String localSha = computeSha256Hex(data);
            appendLog("[Test " + testNumber + "] Received " + data.length
                    + " bytes, SHA=" + localSha.substring(0, 16) + "...");

            stream.write(data);

            String serverVerdict = stream.readLine();
            stream.close();

            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            recordResult("Test " + testNumber, passed, elapsed(startTime), null);
        } catch (Exception exception) {
            recordResult("Test " + testNumber, false, elapsed(startTime),
                    "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 3: Empty message ────────────────────────────────────────────

    private void runEmptyMessageTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 3] Empty Message: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_empty_msg");

            stream.writeString("\n");
            String reply = stream.readLine();
            stream.close();

            boolean passed = "".equals(reply);
            recordResult("Test 3", passed, elapsed(startTime),
                    passed ? "" : "expected='' got='" + reply + "'");
        } catch (Exception exception) {
            recordResult("Test 3", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 4: Unicode round-trip ───────────────────────────────────────

    private void runUnicodeRoundTripTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 4] Unicode: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_unicode");

            String unicodePayload = stream.readLine();
            if (unicodePayload == null) throw new Exception("EOF before unicode payload");
            appendLog("[Test 4] Received: " + unicodePayload);

            stream.writeString(unicodePayload + "\n");

            String serverVerdict = stream.readLine();
            stream.close();

            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            recordResult("Test 4", passed, elapsed(startTime), null);
        } catch (Exception exception) {
            recordResult("Test 4", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 6: Rapid burst ──────────────────────────────────────────────

    private void runRapidBurstTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 6] Rapid Burst: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_burst");

            String countLine = stream.readLine();
            if (countLine == null) throw new Exception("EOF before count header");
            int expectedCount = Integer.parseInt(countLine.trim());
            appendLog("[Test 6] Expecting " + expectedCount + " messages...");

            int receivedCount = 0;
            for (int i = 0; i < expectedCount; i++) {
                String line = stream.readLine();
                if (line == null) break;
                receivedCount++;
            }

            stream.writeString(receivedCount + "\n");

            String serverVerdict = stream.readLine();
            stream.close();

            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            recordResult("Test 6", passed, elapsed(startTime),
                    "received=" + receivedCount + "/" + expectedCount);
        } catch (Exception exception) {
            recordResult("Test 6", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 7: Concurrent channels ──────────────────────────────────────

    private void runConcurrentChannelsTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 7] Concurrent Channels: opening A and B in parallel...");

        AtomicBoolean channelAPassed = new AtomicBoolean(false);
        AtomicBoolean channelBPassed = new AtomicBoolean(false);
        CountDownLatch bothDone = new CountDownLatch(2);

        backgroundExecutor.execute(() -> {
            channelAPassed.set(runSingleChannelEcho(tauSync, "test_concurrent_a", "7a", "concurrent_A"));
            bothDone.countDown();
        });
        backgroundExecutor.execute(() -> {
            channelBPassed.set(runSingleChannelEcho(tauSync, "test_concurrent_b", "7b", "concurrent_B"));
            bothDone.countDown();
        });

        try {
            bothDone.await(30, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }

        boolean passed = channelAPassed.get() && channelBPassed.get();
        recordResult("Test 7", passed, elapsed(startTime), null);
    }

    private boolean runSingleChannelEcho(TauSync manager, String channelName, String label, String payload) {
        try {
            TauSyncStream stream = manager.connect(channelName);
            stream.writeString(payload + "\n");
            String reply = stream.readLine();
            stream.close();

            boolean passed = payload.equals(reply);
            appendLog("  [" + label + "] " + verdict(passed)
                    + (passed ? "" : "  expected=" + payload + " got=" + reply));
            return passed;
        } catch (Exception exception) {
            appendLog("  [" + label + "] FAIL: " + exception.getMessage());
            return false;
        }
    }

    // ── Test 8: Stream close / EOF detection ─────────────────────────────

    private void runStreamCloseTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 8] Stream Close: opening channel...");

        try {
            TauSyncStream stream = tauSync.connect("test_stream_close");

            byte[] data = stream.readAll();
            String content = new String(data, StandardCharsets.UTF_8);
            stream.close();

            boolean passed = "CLOSE_TEST_DATA".equals(content);
            recordResult("Test 8", passed, elapsed(startTime),
                    passed ? "EOF detected correctly"
                            : "expected='CLOSE_TEST_DATA' got='" + content + "'");
        } catch (Exception exception) {
            recordResult("Test 8", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 9: Bidirectional (read and write at once) ───────────────────

    private void runBidirectionalTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 9] Bidirectional: read and write simultaneously...");
        final int messageCount = 50;

        try {
            TauSyncStream stream = tauSync.connect("test_bidir");
            AtomicReference<Exception> writeError = new AtomicReference<>();

            Thread writer = new Thread(() -> {
                try {
                    for (int i = 0; i < messageCount; i++) {
                        stream.writeString(String.format(Locale.US, "from_android_%03d\n", i));
                    }
                } catch (Exception exception) {
                    writeError.set(exception);
                }
            });
            writer.start();

            boolean allMatched = true;
            for (int i = 0; i < messageCount; i++) {
                String expected = String.format(Locale.US, "from_pc_%03d", i);
                if (!expected.equals(stream.readLine())) allMatched = false;
            }
            writer.join(30_000);
            stream.close();

            boolean passed = allMatched && writeError.get() == null;
            recordResult("Test 9", passed, elapsed(startTime), "exchanged " + messageCount + " each way");
        } catch (Exception exception) {
            recordResult("Test 9", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 10: Multiple managers on one socket ─────────────────────────

    private void runMultiManagerTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 10] Multi-Manager: two managers, one socket...");

        try {
            TauSync managerB = tauSync.newManager();
            AtomicBoolean channelAPassed = new AtomicBoolean(false);
            AtomicBoolean channelBPassed = new AtomicBoolean(false);
            CountDownLatch bothDone = new CountDownLatch(2);

            backgroundExecutor.execute(() -> {
                channelAPassed.set(runSingleChannelEcho(tauSync, "test_multi_a", "10a", "multi_A"));
                bothDone.countDown();
            });
            backgroundExecutor.execute(() -> {
                channelBPassed.set(runSingleChannelEcho(managerB, "test_multi_b", "10b", "multi_B"));
                bothDone.countDown();
            });

            bothDone.await(30, TimeUnit.SECONDS);

            boolean passed = channelAPassed.get() && channelBPassed.get();
            recordResult("Test 10", passed, elapsed(startTime), null);
        } catch (Exception exception) {
            recordResult("Test 10", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 11: Channel reuse (open → close → reopen) ───────────────────

    private void runChannelReuseTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 11] Channel Reuse: pairing twice on same word...");

        try {
            boolean allPassed = true;
            for (int round = 0; round < 2; round++) {
                TauSyncStream stream = tauSync.connect("test_reuse");
                String payload = "round_" + round;
                stream.writeString(payload + "\n");
                String reply = stream.readLine();
                stream.close();
                if (!payload.equals(reply)) allPassed = false;
                appendLog("  [reuse round " + round + "] " + verdict(payload.equals(reply)));
            }

            recordResult("Test 11", allPassed, elapsed(startTime), null);
        } catch (Exception exception) {
            recordResult("Test 11", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 12: getPeerWaitingWords discovery queue ─────────────────────

    private void runPeerWaitingWordsTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 12] Peer Waiting Words: firing two pending REQs...");

        final AtomicReference<String> alphaVerdict = new AtomicReference<>(null);
        final AtomicReference<Exception> failure = new AtomicReference<>();
        CountDownLatch bothPaired = new CountDownLatch(2);

        backgroundExecutor.execute(() -> {
            try {
                TauSyncStream stream = tauSync.connect("test_pw_alpha", 60);
                alphaVerdict.set(stream.readLine());
                stream.close();
            } catch (Exception exception) {
                failure.set(exception);
            } finally {
                bothPaired.countDown();
            }
        });
        backgroundExecutor.execute(() -> {
            try {
                TauSyncStream stream = tauSync.connect("test_pw_beta", 60);
                stream.readLine();
                stream.close();
            } catch (Exception exception) {
                failure.set(exception);
            } finally {
                bothPaired.countDown();
            }
        });

        try {
            bothPaired.await(70, TimeUnit.SECONDS);
            boolean passed = "PASS".equals(alphaVerdict.get());
            recordResult("Test 12", passed, elapsed(startTime),
                    failure.get() == null ? "" : "err=" + failure.get().getMessage());
        } catch (InterruptedException exception) {
            recordResult("Test 12", false, elapsed(startTime), "interrupted");
        }
    }

    // ── Test 13: Long single line ────────────────────────────────────────

    private void runLongLineTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 13] Long Line: reading " + LONG_LINE_LENGTH + "-char line...");

        try {
            TauSyncStream stream = tauSync.connect("test_long_line");

            String line = stream.readLine();
            boolean passed = line != null && line.length() == LONG_LINE_LENGTH && isAllChar(line, 'A');
            stream.writeString(passed ? "PASS\n" : "FAIL\n");
            stream.close();

            recordResult("Test 13", passed, elapsed(startTime),
                    "got " + (line == null ? "null" : line.length() + " chars"));
        } catch (Exception exception) {
            recordResult("Test 13", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 14: Small-frame reassembly ──────────────────────────────────

    private void runSmallFramesTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 14] Small Frames: reassembling tiny frames...");

        try {
            TauSyncStream stream = tauSync.connect("test_small_frames");

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size header");
            int dataSize = Integer.parseInt(sizeLine.trim());

            byte[] data = stream.readExactly(dataSize);
            stream.write(data);

            String serverVerdict = stream.readLine();
            stream.close();

            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            recordResult("Test 14", passed, elapsed(startTime), "reassembled " + dataSize + " bytes");
        } catch (Exception exception) {
            recordResult("Test 14", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 15: Raw InputStream/OutputStream adapters ───────────────────

    private void runRawStreamTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 15] Raw Stream: getInputStream/getOutputStream...");

        try {
            TauSyncStream stream = tauSync.connect("test_raw_stream");
            OutputStream out = stream.getOutputStream();
            InputStream in = stream.getInputStream();

            String payload = "raw_hello";
            out.write((payload + "\n").getBytes(StandardCharsets.UTF_8));
            out.flush();

            String reply = readLineFromRaw(in);
            stream.close();

            boolean passed = payload.equals(reply);
            recordResult("Test 15", passed, elapsed(startTime),
                    passed ? "" : "expected=" + payload + " got=" + reply);
        } catch (Exception exception) {
            recordResult("Test 15", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 16: File transfer PC → Android ──────────────────────────────

    private void runFilePcToAndroidTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 16] File PC->Android: receiving file...");

        try {
            TauSyncStream stream = tauSync.connect("test_file_pc_to_android");

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size header");
            long size = Long.parseLong(sizeLine.trim());
            String expectedSha = stream.readLine();

            File dest = new File(getCacheDir(), "tausync_recv_from_pc.bin");
            stream.readToFile(dest.getAbsolutePath(), size);
            String actualSha = computeSha256OfFile(dest);

            boolean passed = expectedSha != null && expectedSha.equals(actualSha);
            stream.writeString(passed ? "PASS\n" : "FAIL\n");
            stream.close();

            recordResult("Test 16", passed, elapsed(startTime), size + " bytes");
        } catch (Exception exception) {
            recordResult("Test 16", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 17: File transfer Android → PC ──────────────────────────────

    private void runFileAndroidToPcTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 17] File Android->PC: sending file...");
        File source = null;

        try {
            TauSyncStream stream = tauSync.connect("test_file_android_to_pc");

            source = new File(getCacheDir(), "tausync_send_to_pc.bin");
            createRandomFile(source, ANDROID_FILE_SIZE);
            String sha = computeSha256OfFile(source);

            stream.writeString(source.length() + "\n");
            stream.writeString(sha + "\n");
            stream.writeFile(source.getAbsolutePath());

            String serverVerdict = stream.readLine();
            stream.close();

            boolean passed = serverVerdict != null && serverVerdict.trim().equals("PASS");
            recordResult("Test 17", passed, elapsed(startTime), ANDROID_FILE_SIZE + " bytes");
        } catch (Exception exception) {
            recordResult("Test 17", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        } finally {
            if (source != null) source.delete();
        }
    }

    // ── Test 18: Peer closes before sending ──────────────────────────────

    private void runPeerCloseTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 18] Peer Close: expecting immediate EOF...");

        try {
            TauSyncStream stream = tauSync.connect("test_peer_close");

            String line = stream.readLine();
            stream.close();

            boolean passed = (line == null);
            recordResult("Test 18", passed, elapsed(startTime),
                    passed ? "EOF detected" : "expected null got='" + line + "'");
        } catch (Exception exception) {
            recordResult("Test 18", false, elapsed(startTime), "ERROR: " + exception.getMessage());
        }
    }

    // ── Test 19: Large write — auto-chunking ────────────────────────────

    private void runLargeWriteTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 19] Large Write (auto-chunk): PC sends " + LARGE_WRITE_SIZE / (1024 * 1024) + " MB in one write()...");
        try {
            TauSyncStream stream = tauSync.connect("test_large_write");

            String sizeLine = stream.readLine();
            if (sizeLine == null) throw new Exception("EOF before size header");
            int size = Integer.parseInt(sizeLine.trim());

            String expectedSha = stream.readLine();
            if (expectedSha == null) throw new Exception("EOF before SHA header");

            byte[] data = stream.readExactly(size);
            String actualSha = computeSha256Hex(data);

            boolean passed = expectedSha.trim().equals(actualSha);
            stream.writeString(passed ? "PASS\n" : "FAIL\n");
            stream.close();

            recordResult("Test 19", passed, elapsed(startTime),
                    size + " bytes received from a single PC write()");
        } catch (Exception e) {
            recordResult("Test 19", false, elapsed(startTime), "ERROR: " + e.getMessage());
        }
    }

    // ── Test 20: Concurrent channels — ID uniqueness ─────────────────────

    private void runConcurrentIdsTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 20] Concurrent IDs: opening " + CONCURRENT_ID_COUNT + " channels simultaneously...");

        AtomicBoolean allPassed = new AtomicBoolean(true);
        CountDownLatch allDone = new CountDownLatch(CONCURRENT_ID_COUNT);

        for (int i = 0; i < CONCURRENT_ID_COUNT; i++) {
            final int index = i;
            final String word = String.format(Locale.US, "test_cid_%02d", i);
            final String payload = String.format(Locale.US, "payload_%02d", i);
            backgroundExecutor.execute(() -> {
                try {
                    TauSyncStream stream = tauSync.connect(word);
                    stream.writeString(payload + "\n");
                    String verdict = stream.readLine();
                    stream.close();
                    if (!"PASS".equals(verdict)) {
                        allPassed.set(false);
                        appendLog("  [cid_" + String.format(Locale.US, "%02d", index)
                                + "] FAIL: verdict=" + verdict);
                    }
                } catch (Exception e) {
                    allPassed.set(false);
                    appendLog("  [cid_" + String.format(Locale.US, "%02d", index)
                            + "] ERROR: " + e.getMessage());
                } finally {
                    allDone.countDown();
                }
            });
        }

        try {
            allDone.await(30, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {}

        recordResult("Test 20", allPassed.get(), elapsed(startTime),
                CONCURRENT_ID_COUNT + " concurrent channels, no cross-talk");
    }

    // ── Test 21: Concurrent close — no double-FIN corruption ─────────────

    private void runConcurrentCloseTest() {
        long startTime = System.currentTimeMillis();
        appendLog("[Test 21] Concurrent Close: simultaneous close, then verify next channel...");
        try {
            // Signal PC to close too, then close our end — both sides close at the same time.
            TauSyncStream stream = tauSync.connect("test_conc_close");
            stream.writeString("ready\n");
            stream.close();

            // If double-FIN corrupted the ID/routing state the echo below will fail.
            TauSyncStream verify = tauSync.connect("test_conc_close_verify");
            String payload = "verify_ok";
            verify.writeString(payload + "\n");
            String reply = verify.readLine();
            verify.close();

            boolean passed = payload.equals(reply);
            recordResult("Test 21", passed, elapsed(startTime),
                    passed ? "no corruption after concurrent close"
                           : "expected=" + payload + " got=" + reply);
        } catch (Exception e) {
            recordResult("Test 21", false, elapsed(startTime), "ERROR: " + e.getMessage());
        }
    }

    // ── UI state management ──────────────────────────────────────────────

    private void setInitialControlState() {
        openChannelButton.setEnabled(false);
        runAllTestsButton.setEnabled(false);
    }

    private void setConnectedState() {
        connectButton.setText("Disconnect");
        connectButton.setEnabled(true);
        ipAddressInput.setEnabled(false);
        openChannelButton.setEnabled(true);
        meetingWordInput.setEnabled(true);
        runAllTestsButton.setEnabled(true);
    }

    private void setDisconnectedState() {
        connectButton.setText("Connect");
        connectButton.setEnabled(true);
        ipAddressInput.setEnabled(true);
        openChannelButton.setEnabled(false);
        runAllTestsButton.setEnabled(false);
        closeAllManualChannels();
    }

    private void setConnectingState() {
        connectButton.setEnabled(false);
        ipAddressInput.setEnabled(false);
    }

    private void updateStatus(String status) {
        statusLabel.setText("Status: " + status);
    }

    private void appendLog(String message) {
        String timestamp = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(new Date());
        String entry = "[" + timestamp + "] " + message + "\n";
        runOnUiThread(() -> {
            logView.append(entry);
            logScrollView.post(() -> logScrollView.fullScroll(View.FOCUS_DOWN));
        });
    }

    // ── Utilities ────────────────────────────────────────────────────────

    private String resolveLocalIpAddress() {
        try {
            WifiManager wifiManager = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
            int ipInt = wifiManager.getConnectionInfo().getIpAddress();
            return (ipInt == 0) ? "Disconnected" : Formatter.formatIpAddress(ipInt);
        } catch (Exception exception) {
            return "Unknown";
        }
    }

    /** Reads one '\n'-terminated line directly from a raw InputStream. */
    private static String readLineFromRaw(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        boolean sawAnyByte = false;
        int b;
        while ((b = in.read()) >= 0) {
            sawAnyByte = true;
            if (b == '\n') break;
            buffer.write(b);
        }
        if (!sawAnyByte) return null;
        return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
    }

    private static boolean isAllChar(String text, char expected) {
        for (int i = 0; i < text.length(); i++) {
            if (text.charAt(i) != expected) return false;
        }
        return true;
    }

    private static int parsePositiveInt(String text, int fallback) {
        try {
            int value = Integer.parseInt(text.trim());
            return value > 0 ? value : fallback;
        } catch (NumberFormatException exception) {
            return fallback;
        }
    }

    private static String computeSha256Hex(byte[] data) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
            return toHex(digest);
        } catch (Exception exception) {
            return "error";
        }
    }

    private static String computeSha256OfFile(File file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            try (FileInputStream input = new FileInputStream(file)) {
                int n;
                while ((n = input.read(buffer)) > 0) {
                    digest.update(buffer, 0, n);
                }
            }
            return toHex(digest.digest());
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IOException(exception);
        }
    }

    private static void createRandomFile(File file, long size) throws IOException {
        Random random = new Random();
        byte[] buffer = new byte[65536];
        long remaining = size;
        try (FileOutputStream output = new FileOutputStream(file)) {
            while (remaining > 0) {
                int n = (int) Math.min(buffer.length, remaining);
                random.nextBytes(buffer);
                output.write(buffer, 0, n);
                remaining -= n;
            }
        }
    }

    private static String toHex(byte[] bytes) {
        StringBuilder hexString = new StringBuilder();
        for (byte b : bytes) {
            hexString.append(String.format("%02x", b));
        }
        return hexString.toString();
    }

    private static String verdict(boolean passed) {
        return passed ? "PASS" : "FAIL";
    }

    private static long elapsed(long startTime) {
        return System.currentTimeMillis() - startTime;
    }

    private static String formatByteSize(int bytes) {
        if (bytes >= 1_048_576) return (bytes / 1_048_576) + " MB";
        if (bytes >= 1_024) return (bytes / 1_024) + " KB";
        return bytes + " B";
    }

    private static String extractRootCauseMessage(Exception exception) {
        Throwable cause = exception;
        while (cause.getCause() != null) {
            cause = cause.getCause();
        }
        return cause.getClass().getSimpleName() + ": " + cause.getMessage();
    }

    private void disposeTauSyncQuietly() {
        try {
            if (tauSync != null) tauSync.dispose();
        } catch (Exception ignored) {
        }
    }

    // ── View factory helpers ─────────────────────────────────────────────

    private LinearLayout newVerticalColumn(int paddingDp) {
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int paddingPixels = dpToPixels(paddingDp);
        column.setPadding(paddingPixels, paddingPixels, paddingPixels, paddingPixels);
        return column;
    }

    private LinearLayout newHorizontalRow() {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER);
        return row;
    }

    private EditText newEditText(String hint, String defaultValue) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setText(defaultValue);
        editText.setSingleLine(true);
        return editText;
    }

    private TextView newSectionTitle(String title) {
        TextView textView = new TextView(this);
        textView.setText(title);
        textView.setTextSize(18);
        textView.setPadding(0, dpToPixels(12), 0, dpToPixels(4));
        return textView;
    }

    private LinearLayout.LayoutParams newRowParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.weight = 1;
        params.setMargins(dpToPixels(4), 0, dpToPixels(4), 0);
        return params;
    }

    private int dpToPixels(int dp) {
        return (int) (dp * getResources().getDisplayMetrics().density);
    }
}
